from unittest.mock import AsyncMock, patch

import pytest
from fastmcp import FastMCP
from pydantic import ValidationError

from agents_md_server.tools.auth_http_fetch import (
    _get_oauth2_token,
    _resolve_env,
    invalidate_oauth2_cache,
)
from agents_md_server.tools.auth_http_fetch import register as register_auth
from agents_md_server.tools.cost_estimator import CostEstimatorParams
from agents_md_server.tools.cost_estimator import register as register_cost
from agents_md_server.tools.http_fetch import register as register_http


def test_cost_estimator_params_validation():
    params = CostEstimatorParams(
        unit_price=0.15,
        unit_of_measure="1 Hour",
        quantity=730,
        label="VM D4s v5",
    )
    assert params.unit_price == 0.15
    assert params.quantity == 730

    with pytest.raises(ValidationError):
        CostEstimatorParams(
            unit_price=-1.0,
            unit_of_measure="1 Hour",
            quantity=100,
        )


@pytest.mark.asyncio
async def test_cost_estimator_tool():
    mcp = FastMCP("test")
    register_cost(mcp)

    tool = await mcp.get_tool("cost_estimator")
    result = tool.fn(
        unit_price=0.20,
        unit_of_measure="1 Hour",
        quantity=730,
        label="Linux VM",
    )
    assert "Linux VM" in result
    assert "146.0000" in result  # 0.20 * 730 = 146.0
    assert "1,752.0000" in result  # 146 * 12 = 1752.0


@pytest.mark.asyncio
async def test_http_fetch_ssrf_block():
    mcp = FastMCP("test")
    register_http(mcp)
    tool = await mcp.get_tool("http_fetch")

    # Localhost should be blocked by SSRF policy
    res = await tool.fn(url="http://localhost:8080/secret")
    assert "error" in res
    assert "SSRF" in res["error"]
    assert res["status_code"] == 400


def test_resolve_env(monkeypatch):
    monkeypatch.setenv("TEST_API_KEY", "super-secret-token")
    assert _resolve_env("TEST_API_KEY", "env_key") == "super-secret-token"

    with pytest.raises(ValueError, match="is required"):
        _resolve_env(None, "env_key")

    with pytest.raises(ValueError, match="not set"):
        _resolve_env("NON_EXISTENT_VAR_12345", "env_key")


def test_resolve_env_rejects_raw_secrets():
    """Verify that models passing raw secrets instead of variable names receive guidance."""
    with pytest.raises(ValueError, match="expects the NAME of an environment variable"):
        _resolve_env("Bearer dapi1234567890abcdef", "env_key")

    with pytest.raises(ValueError, match="expects the NAME of an environment variable"):
        _resolve_env("sk-proj-1234567890abcdef1234567890", "env_key")

    with pytest.raises(ValueError, match="expects the NAME of an environment variable"):
        _resolve_env("dapi_super_long_secret_key_that_is_clearly_not_a_var", "env_key")


@pytest.mark.asyncio
async def test_auth_http_fetch_custom_header_prefix(monkeypatch):
    """Test custom header_name and header_prefix support."""
    monkeypatch.setenv("CUSTOM_KEY", "my-secret-key-123")
    mcp = FastMCP("test")
    register_auth(mcp)
    tool = await mcp.get_tool("auth_http_fetch")

    with patch(
        "agents_md_server.tools.auth_http_fetch.execute_http_request", new_callable=AsyncMock
    ) as mock_req:
        mock_req.return_value = {"status": "ok"}

        # Custom header name (e.g. api-key) and prefix ("")
        await tool.fn(
            url="https://api.example.com/data",
            auth_type="bearer",
            env_key="CUSTOM_KEY",
            header_name="api-key",
            header_prefix="",
        )
        assert mock_req.call_args.kwargs["headers"]["api-key"] == "my-secret-key-123"

        # Custom prefix (e.g. "Token ")
        await tool.fn(
            url="https://api.example.com/data",
            auth_type="bearer",
            env_key="CUSTOM_KEY",
            header_prefix="Token ",
        )
        assert mock_req.call_args.kwargs["headers"]["Authorization"] == "Token my-secret-key-123"


@pytest.mark.asyncio
async def test_auth_http_fetch_template_header_substitution(monkeypatch):
    """Test __ENV__ substring substitution in extra_headers."""
    monkeypatch.setenv("DEEPL_KEY", "deepl-key-value")
    mcp = FastMCP("test")
    register_auth(mcp)
    tool = await mcp.get_tool("auth_http_fetch")

    with patch(
        "agents_md_server.tools.auth_http_fetch.execute_http_request", new_callable=AsyncMock
    ) as mock_req:
        mock_req.return_value = {"status": "ok"}

        await tool.fn(
            url="https://api.example.com/translate",
            auth_type="api_key_header",
            env_key="DEEPL_KEY",
            extra_headers={"Authorization": "DeepL-Auth-Key __ENV__"},
        )
        assert (
            mock_req.call_args.kwargs["headers"]["Authorization"]
            == "DeepL-Auth-Key deepl-key-value"
        )


@pytest.mark.asyncio
async def test_oauth2_token_caching():
    invalidate_oauth2_cache()

    mock_response = {
        "access_token": "mock-token-abc",
        "expires_in": 3600,
    }

    with patch(
        "agents_md_server.tools.auth_http_fetch.execute_http_request", new_callable=AsyncMock
    ) as mock_req:
        mock_req.return_value = mock_response

        # First fetch: should make network request
        token1, err1 = await _get_oauth2_token(
            token_url="https://auth.example.com/token",
            client_id="my-client-id",
            client_secret="my-secret",
        )
        assert token1 == "mock-token-abc"
        assert err1 is None
        assert mock_req.call_count == 1

        # Second fetch: should hit cache without calling network
        token2, err2 = await _get_oauth2_token(
            token_url="https://auth.example.com/token",
            client_id="my-client-id",
            client_secret="my-secret",
        )
        assert token2 == "mock-token-abc"
        assert err2 is None
        assert mock_req.call_count == 1  # Still 1, verified cache hit!

        # Invalidate cache and verify refetch
        invalidate_oauth2_cache("https://auth.example.com/token", "my-client-id")
        token3, err3 = await _get_oauth2_token(
            token_url="https://auth.example.com/token",
            client_id="my-client-id",
            client_secret="my-secret",
        )
        assert token3 == "mock-token-abc"
        assert err3 is None
        assert mock_req.call_count == 2
