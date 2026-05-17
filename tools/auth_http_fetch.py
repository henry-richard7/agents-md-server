"""
auth_http_fetch.py
Authenticated HTTP tool — supports all common auth types.
API keys are read from environment variables server-side.
The model never sees the actual credentials.
"""

import os
import httpx
import base64
from typing import Optional


def register(mcp):

    @mcp.tool
    async def auth_http_fetch(
        url: str,
        method: str = "GET",
        auth_type: str = "bearer",
        env_key: str = None,
        env_client_id: str = None,
        env_client_secret: str = None,
        env_username: str = None,
        env_password: str = None,
        token_url: str = None,
        token_body: dict = None,
        query_params: dict = None,
        body: dict = None,
        extra_headers: dict = None,
    ) -> dict:
        """Make an authenticated HTTP request. Credentials are read from
        environment variables server-side — never pass actual keys or secrets.

        auth_type options:
          - "bearer"      : Authorization: Bearer <token>
                            Set env_key to the env var name holding the token.
                            Example: env_key="OPENAI_API_KEY"

          - "api_key_header" : Custom header API key.
                            Set env_key to the env var name holding the key.
                            Set extra_headers={"X-API-Key": "__ENV__"} to indicate
                            which header to inject the key into.
                            Example: env_key="MY_SERVICE_API_KEY",
                                     extra_headers={"X-Api-Key": "__ENV__"}

          - "basic"       : Authorization: Basic base64(username:password)
                            Set env_username and env_password to env var names.
                            Example: env_username="MY_USER", env_password="MY_PASS"

          - "client_credentials" : OAuth2 client credentials flow.
                            Fetches a token from token_url first, then uses it.
                            Set env_client_id and env_client_secret to env var names.
                            Set token_url to the OAuth2 token endpoint.
                            Set token_body for any extra fields (e.g. scope).
                            Example: env_client_id="MY_CLIENT_ID",
                                     env_client_secret="MY_CLIENT_SECRET",
                                     token_url="https://auth.example.com/oauth/token",
                                     token_body={"scope": "read:data"}

          - "api_key_query" : API key passed as a query parameter.
                            Set env_key to the env var name holding the key.
                            Set query_params={"api_key": "__ENV__"} to indicate
                            which param to inject the key into.
                            Example: env_key="MY_API_KEY",
                                     query_params={"api_key": "__ENV__"}

        Args:
            url:               The API endpoint URL.
            method:            HTTP method (GET, POST, PUT, PATCH, DELETE).
            auth_type:         One of: bearer, api_key_header, basic,
                               client_credentials, api_key_query.
            env_key:           Name of the env var holding the API key or token.
            env_client_id:     Name of the env var holding the OAuth2 client ID.
            env_client_secret: Name of the env var holding the OAuth2 client secret.
            env_username:      Name of the env var holding the basic auth username.
            env_password:      Name of the env var holding the basic auth password.
            token_url:         OAuth2 token endpoint (for client_credentials only).
            token_body:        Extra fields for the OAuth2 token request body.
            query_params:      Query parameters dict. Use "__ENV__" as the value
                               to inject the API key (for api_key_query auth).
            body:              Request body as a dict (for POST/PUT/PATCH).
            extra_headers:     Additional headers. Use "__ENV__" as the value
                               to inject the API key (for api_key_header auth).
        """

        headers = {}
        params = query_params or {}

        # ── Resolve auth ───────────────────────────────────────────────────
        if auth_type == "bearer":
            token = _resolve_env(env_key, "env_key")
            headers["Authorization"] = f"Bearer {token}"

        elif auth_type == "api_key_header":
            key = _resolve_env(env_key, "env_key")
            # Replace __ENV__ placeholder in extra_headers with the actual key
            extra_headers = extra_headers or {}
            for header_name, header_value in extra_headers.items():
                if header_value == "__ENV__":
                    headers[header_name] = key
                else:
                    headers[header_name] = header_value

        elif auth_type == "basic":
            username = _resolve_env(env_username, "env_username")
            password = _resolve_env(env_password, "env_password")
            credentials = base64.b64encode(f"{username}:{password}".encode()).decode()
            headers["Authorization"] = f"Basic {credentials}"

        elif auth_type == "client_credentials":
            if not token_url:
                return {"error": "token_url is required for client_credentials auth"}
            client_id = _resolve_env(env_client_id, "env_client_id")
            client_secret = _resolve_env(env_client_secret, "env_client_secret")
            token = await _fetch_oauth2_token(
                token_url, client_id, client_secret, token_body or {}
            )
            if "error" in token:
                return token
            headers["Authorization"] = f"Bearer {token['access_token']}"

        elif auth_type == "api_key_query":
            key = _resolve_env(env_key, "env_key")
            # Replace __ENV__ placeholder in query_params with the actual key
            params = {k: (key if v == "__ENV__" else v) for k, v in params.items()}

        else:
            return {
                "error": f"Unknown auth_type: '{auth_type}'. "
                f"Use: bearer, api_key_header, basic, "
                f"client_credentials, api_key_query"
            }

        # ── Merge any remaining extra_headers ─────────────────────────────
        if extra_headers and auth_type != "api_key_header":
            headers.update(extra_headers)

        # ── Make the request ───────────────────────────────────────────────
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.request(
                method=method.upper(),
                url=url,
                params=params,
                json=body,
                headers=headers,
            )
            response.raise_for_status()
            try:
                return response.json()
            except ValueError:
                return {"text": response.text}


def _resolve_env(env_var_name: Optional[str], param_name: str) -> str:
    """Read a value from an environment variable by name."""
    if not env_var_name:
        raise ValueError(
            f"{param_name} is required but was not provided. "
            f"Pass the name of the environment variable holding the credential."
        )
    value = os.getenv(env_var_name)
    if not value:
        raise ValueError(
            f"Environment variable '{env_var_name}' is not set. "
            f"Add it to your .env file."
        )
    return value


async def _fetch_oauth2_token(
    token_url: str,
    client_id: str,
    client_secret: str,
    extra_body: dict,
) -> dict:
    """Fetch an OAuth2 token using the client credentials flow."""
    body = {
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret,
        **extra_body,
    }
    async with httpx.AsyncClient(timeout=30) as client:
        try:
            response = await client.post(token_url, data=body)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            return {
                "error": f"Token fetch failed: {e.response.status_code} {e.response.text}"
            }
        except Exception as e:
            return {"error": f"Token fetch failed: {str(e)}"}
