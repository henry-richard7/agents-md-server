from unittest.mock import AsyncMock, patch

import pytest
from fastmcp import FastMCP
from pydantic import ValidationError

from agents_md_server.tools.auth_http_fetch import (
    _OAUTH2_TOKEN_CACHE,
    _get_oauth2_token,
    _resolve_env,
)
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


@pytest.mark.asyncio
async def test_oauth2_token_caching():
    _OAUTH2_TOKEN_CACHE.clear()

    mock_response = {
        "access_token": "mock-token-abc",
        "expires_in": 3600,
    }

    with patch("agents_md_server.tools.auth_http_fetch.execute_http_request", new_callable=AsyncMock) as mock_req:
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
