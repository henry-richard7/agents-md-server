"""auth_http_fetch tool for MCP.

Authenticated HTTP tool supporting bearer, custom API key headers, basic auth,
OAuth2 client credentials, and query parameter tokens.
Credentials are read from server-side environment variables so models never see secrets.
"""

from __future__ import annotations

import asyncio
import base64
import logging
import os
import re
import time
from typing import Any, Literal

from fastmcp import Context, FastMCP

from agents_md_server.config import settings
from agents_md_server.http_client import execute_http_request

logger = logging.getLogger(__name__)

# In-memory OAuth2 token cache: cache_key -> (access_token, expire_timestamp)
_OAUTH2_TOKEN_CACHE: dict[str, tuple[str, float]] = {}
_OAUTH2_LOCK = asyncio.Lock()


def invalidate_oauth2_cache(token_url: str | None = None, client_id: str | None = None) -> None:
    """Evict a specific or all cached OAuth2 tokens."""
    if token_url and client_id:
        _OAUTH2_TOKEN_CACHE.pop(f"{token_url}::{client_id}", None)
    else:
        _OAUTH2_TOKEN_CACHE.clear()


def _resolve_env(env_var_name: str | None, param_name: str) -> str:
    """Read a credential safely from an environment variable."""
    if not env_var_name:
        raise ValueError(
            f"Parameter '{param_name}' is required for this authentication type. "
            f"Pass the name of the environment variable holding the credential."
        )

    raw = env_var_name.strip()

    # Guard against LLMs accidentally passing raw secrets/tokens instead of variable names
    known_token_prefixes = (
        "Bearer ",
        "sk-",
        "ghp_",
        "gho_",
        "dapi",
        "glpat-",
        "xoxb-",
        "xoxp-",
        "ya29.",
    )
    has_spaces = " " in raw
    looks_like_token = (
        any(raw.startswith(p) for p in known_token_prefixes)
        or has_spaces
        or (len(raw) > 32 and not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", raw))
    )

    if looks_like_token:
        preview = raw[:10] + "..." if len(raw) > 10 else raw
        raise ValueError(
            f"Parameter '{param_name}' expects the NAME of an environment variable (e.g. 'DATABRICKS_TOKEN', 'API_KEY'), "
            f"but received what looks like a raw secret value ('{preview}'). "
            "For security, do not pass secrets directly; pass the environment variable name configured in .env."
        )

    value = os.getenv(raw)
    if not value:
        # Fallback to reading directly from .env file if updated dynamically
        from dotenv import dotenv_values

        from agents_md_server.config import PROJECT_ROOT

        env_path = PROJECT_ROOT / ".env"
        if env_path.exists():
            env_vars = dotenv_values(env_path)
            value = env_vars.get(raw)
            if value:
                os.environ[raw] = value

    if not value:
        raise ValueError(
            f"Environment variable '{raw}' is not set or empty. "
            f"Please configure it in your server's .env file."
        )
    return value.strip()


async def _get_oauth2_token(
    token_url: str,
    client_id: str,
    client_secret: str,
    extra_body: dict[str, Any] | None = None,
) -> tuple[str | None, str | None]:
    """Fetch or reuse cached OAuth2 client credentials token with lock protection."""
    now = time.time()
    cache_key = f"{token_url}::{client_id}"

    async with _OAUTH2_LOCK:
        if cache_key in _OAUTH2_TOKEN_CACHE:
            cached_token, expire_at = _OAUTH2_TOKEN_CACHE[cache_key]
            if now < (expire_at - settings.oauth_token_buffer_seconds):
                logger.debug("Reusing cached OAuth2 token for %s", client_id)
                return cached_token, None

        payload = {
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
            **(extra_body or {}),
        }

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

        access_token = result.get("access_token") or result.get("token")
        if not access_token and isinstance(result.get("data"), dict):
            access_token = result["data"].get("access_token")

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
        http_method: str | None = None,
        auth_type: Literal[
            "bearer",
            "api_key_header",
            "basic",
            "client_credentials",
            "api_key_query",
        ] = "bearer",
        env_key: str | None = None,
        env_base_url: str | None = None,
        env_client_id: str | None = None,
        env_client_secret: str | None = None,
        env_username: str | None = None,
        env_password: str | None = None,
        header_name: str | None = None,
        header_prefix: str | None = None,
        scope: str | None = None,
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
          - "bearer"             : Authorization: Bearer <token> (requires env_key; header_name & header_prefix customizable)
          - "api_key_header"     : Custom header (e.g. X-API-Key, api-key, PRIVATE-TOKEN; supports header_name or '__ENV__' substitution)
          - "basic"              : Basic HTTP Auth (requires env_username and env_password)
          - "client_credentials" : OAuth2 flow (requires env_client_id, env_client_secret, token_url, optional scope)
          - "api_key_query"      : Query parameter (requires env_key; supports header_name for param name or '__ENV__' substitution)
        """
        headers: dict[str, str] = {}
        params: dict[str, Any] = dict(query_params or {})

        base_url: str | None = None
        try:
            if env_base_url:
                base_url = _resolve_env(env_base_url, "env_base_url")

            if auth_type == "bearer":
                token = _resolve_env(env_key, "env_key")
                h_name = header_name or "Authorization"
                prefix = header_prefix if header_prefix is not None else "Bearer "
                headers[h_name] = f"{prefix}{token}"

            elif auth_type == "api_key_header":
                key = _resolve_env(env_key, "env_key")
                resolved_headers = dict(extra_headers or {})

                has_template = any("__ENV__" in v for v in resolved_headers.values())
                if has_template:
                    for h_n, h_v in resolved_headers.items():
                        headers[h_n] = h_v.replace("__ENV__", key)
                else:
                    h_name = header_name or "X-API-Key"
                    prefix = header_prefix or ""
                    headers[h_name] = f"{prefix}{key}"
                    headers.update(resolved_headers)

            elif auth_type == "basic":
                username = _resolve_env(env_username, "env_username")
                password = _resolve_env(env_password, "env_password")
                encoded = base64.b64encode(f"{username}:{password}".encode()).decode("ascii")
                h_name = header_name or "Authorization"
                headers[h_name] = f"Basic {encoded}"

            elif auth_type == "client_credentials":
                if not token_url:
                    return {
                        "error": "token_url is required for client_credentials auth flow",
                        "status_code": 400,
                    }
                client_id = _resolve_env(env_client_id, "env_client_id")
                client_secret = _resolve_env(env_client_secret, "env_client_secret")
                req_body = dict(token_body or {})
                if scope and "scope" not in req_body:
                    req_body["scope"] = scope

                token, err = await _get_oauth2_token(token_url, client_id, client_secret, req_body)
                if err or not token:
                    return {"error": err or "Failed to obtain token", "status_code": 401}
                h_name = header_name or "Authorization"
                prefix = header_prefix if header_prefix is not None else "Bearer "
                headers[h_name] = f"{prefix}{token}"

            elif auth_type == "api_key_query":
                key = _resolve_env(env_key, "env_key")
                has_template = any(isinstance(v, str) and "__ENV__" in v for v in params.values())
                if has_template:
                    params = {
                        k: (
                            v.replace("__ENV__", key)
                            if isinstance(v, str) and "__ENV__" in v
                            else v
                        )
                        for k, v in params.items()
                    }
                else:
                    q_key = header_name or "api_key"
                    params[q_key] = key

            else:
                return {
                    "error": f"Unsupported auth_type: '{auth_type}'.",
                    "status_code": 400,
                }

        except ValueError as e:
            return {"error": str(e), "status_code": 400}

        # Merge any additional headers if not already set
        if extra_headers and auth_type not in ("api_key_header",):
            headers.update(extra_headers)

        effective_method = (http_method or method).upper()
        if ctx:
            await ctx.info(
                f"Executing authenticated HTTP {effective_method} to {url} ({auth_type})"
            )

        res = await execute_http_request(
            url=url,
            method=effective_method,
            params=params,
            json_body=body,
            headers=headers,
            base_url=base_url,
        )

        # Invalidate OAuth2 token cache on HTTP 401 to ensure stale/revoked tokens are refreshed
        if (
            isinstance(res, dict)
            and res.get("status_code") == 401
            and auth_type == "client_credentials"
            and token_url
            and env_client_id
        ):
            try:
                cid = _resolve_env(env_client_id, "env_client_id")
                invalidate_oauth2_cache(token_url, cid)
                logger.info("Evicted OAuth2 cached token following HTTP 401 response.")
            except ValueError:
                pass

        # Diagnostic assistance on 401/403 errors
        if isinstance(res, dict) and res.get("status_code") in (401, 403):
            used_var = env_key or (
                f"{env_client_id} / {env_client_secret}"
                if auth_type == "client_credentials"
                else env_username
            )
            if used_var:
                res["diagnostic"] = (
                    f"Authentication failed with HTTP {res.get('status_code')}. "
                    f"Verify that the credential in environment variable '{used_var}' is valid, unexpired, and properly set in .env."
                )

        return res
