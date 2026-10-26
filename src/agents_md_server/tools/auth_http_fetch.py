"""auth_http_fetch tool for MCP.

Authenticated HTTP tool supporting bearer, API key headers, basic auth,
OAuth2 client credentials, and query parameter tokens.
Credentials are read from server-side environment variables so models never see secrets.
"""

from __future__ import annotations

import base64
import logging
import os
import time
from typing import Any, Literal

from fastmcp import Context, FastMCP

from agents_md_server.config import settings
from agents_md_server.http_client import execute_http_request

logger = logging.getLogger(__name__)

# In-memory OAuth2 token cache: cache_key -> (access_token, expire_timestamp)
_OAUTH2_TOKEN_CACHE: dict[str, tuple[str, float]] = {}


def _resolve_env(env_var_name: str | None, param_name: str) -> str:
    """Read a credential safely from an environment variable."""
    if not env_var_name:
        raise ValueError(
            f"Parameter '{param_name}' is required for this authentication type. "
            f"Pass the name of the environment variable holding the credential."
        )
    value = os.getenv(env_var_name)
    if not value:
        raise ValueError(
            f"Environment variable '{env_var_name}' is not set or empty. "
            f"Please configure it in your server's .env file."
        )
    return value.strip()


async def _get_oauth2_token(
    token_url: str,
    client_id: str,
    client_secret: str,
    extra_body: dict[str, Any] | None = None,
) -> tuple[str | None, str | None]:
    """Fetch or reuse cached OAuth2 client credentials token.

    Returns:
        (access_token, error_message)
    """
    now = time.time()
    cache_key = f"{token_url}::{client_id}"

    if cache_key in _OAUTH2_TOKEN_CACHE:
        cached_token, expire_at = _OAUTH2_TOKEN_CACHE[cache_key]
        if now < (expire_at - settings.oauth_token_buffer_seconds):
            logger.debug("Reusing cached OAuth2 token for %s", client_id)
            return cached_token, None

    # Fetch new token
    payload = {
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret,
        **(extra_body or {}),
    }

    # Token endpoints typically expect form-urlencoded or json
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    result = await execute_http_request(
        url=token_url,
        method="POST",
        params=None,
        json_body=payload,
        headers=headers,
    )

    if "error" in result:
        return None, f"OAuth2 token request failed: {result['error']}"

    access_token = result.get("access_token")
    if not access_token:
        return None, f"Token endpoint response did not contain 'access_token': {result}"

    expires_in = float(result.get("expires_in", 3600))
    _OAUTH2_TOKEN_CACHE[cache_key] = (access_token, now + expires_in)
    logger.info("Successfully fetched and cached new OAuth2 token for client %s", client_id)
    return access_token, None


def register(mcp: FastMCP) -> None:
    """Register the auth_http_fetch tool with FastMCP."""

    @mcp.tool
    async def auth_http_fetch(
        url: str,
        method: str = "GET",
        auth_type: Literal[
            "bearer",
            "api_key_header",
            "basic",
            "client_credentials",
            "api_key_query",
        ] = "bearer",
        env_key: str | None = None,
        env_client_id: str | None = None,
        env_client_secret: str | None = None,
        env_username: str | None = None,
        env_password: str | None = None,
        token_url: str | None = None,
        token_body: dict[str, Any] | None = None,
        query_params: dict[str, Any] | None = None,
        body: dict[str, Any] | None = None,
        extra_headers: dict[str, str] | None = None,
        ctx: Context | None = None,
    ) -> dict[str, Any]:
        """Make an authenticated HTTP request using credentials stored in environment variables.

        Credentials are read from server-side environment variables — never pass actual secrets.

        auth_type options:
          - "bearer"             : Authorization: Bearer <token> (requires env_key)
          - "api_key_header"     : Custom header (requires env_key and extra_headers with '__ENV__' value)
          - "basic"              : Basic HTTP Auth (requires env_username and env_password)
          - "client_credentials" : OAuth2 flow (requires env_client_id, env_client_secret, token_url)
          - "api_key_query"      : Query parameter (requires env_key and query_params with '__ENV__' value)
        """
        headers: dict[str, str] = {}
        params: dict[str, Any] = dict(query_params or {})

        try:
            if auth_type == "bearer":
                token = _resolve_env(env_key, "env_key")
                headers["Authorization"] = f"Bearer {token}"

            elif auth_type == "api_key_header":
                key = _resolve_env(env_key, "env_key")
                resolved_headers = dict(extra_headers or {})
                if not any(v == "__ENV__" for v in resolved_headers.values()):
                    # Default to X-API-Key if placeholder was not specified
                    headers["X-API-Key"] = key
                for h_name, h_val in resolved_headers.items():
                    headers[h_name] = key if h_val == "__ENV__" else h_val

            elif auth_type == "basic":
                username = _resolve_env(env_username, "env_username")
                password = _resolve_env(env_password, "env_password")
                encoded = base64.b64encode(f"{username}:{password}".encode()).decode("ascii")
                headers["Authorization"] = f"Basic {encoded}"

            elif auth_type == "client_credentials":
                if not token_url:
                    return {"error": "token_url is required for client_credentials auth flow", "status_code": 400}
                client_id = _resolve_env(env_client_id, "env_client_id")
                client_secret = _resolve_env(env_client_secret, "env_client_secret")
                token, err = await _get_oauth2_token(token_url, client_id, client_secret, token_body)
                if err or not token:
                    return {"error": err or "Failed to obtain token", "status_code": 401}
                headers["Authorization"] = f"Bearer {token}"

            elif auth_type == "api_key_query":
                key = _resolve_env(env_key, "env_key")
                if not any(v == "__ENV__" for v in params.values()):
                    params["api_key"] = key
                else:
                    params = {k: (key if v == "__ENV__" else v) for k, v in params.items()}

            else:
                return {
                    "error": f"Unsupported auth_type: '{auth_type}'.",
                    "status_code": 400,
                }

        except ValueError as e:
            return {"error": str(e), "status_code": 400}

        # Merge any additional headers if not already set
        if extra_headers and auth_type != "api_key_header":
            headers.update(extra_headers)

        if ctx:
            await ctx.info(f"Executing authenticated HTTP {method.upper()} to {url} ({auth_type})")

        return await execute_http_request(
            url=url,
            method=method,
            params=params,
            json_body=body,
            headers=headers,
        )
