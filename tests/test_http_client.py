from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agents_md_server.config import settings
from agents_md_server.http_client import (
    HttpClientManager,
    SecurityError,
    execute_http_request,
    validate_url,
)


def test_validate_url_valid(monkeypatch):
    # Mock DNS lookup so test is instantaneous and does not require external network
    monkeypatch.setattr(
        "socket.getaddrinfo",
        lambda host, port: [(2, 1, 6, "", ("93.184.216.34", port))],
    )
    assert validate_url("https://example.com/api/test") == "https://example.com/api/test"
    assert validate_url("http://api.ipify.org?format=json") == "http://api.ipify.org?format=json"


def test_validate_url_invalid_scheme():
    with pytest.raises(ValueError, match="Invalid URL scheme"):
        validate_url("ftp://example.com/file")

    with pytest.raises(ValueError, match="Invalid URL scheme"):
        validate_url("file:///etc/passwd")


def test_validate_url_blocks_localhost():
    with pytest.raises(SecurityError, match="SSRF policy"):
        validate_url("http://localhost:8080", allow_private_networks=False)

    with pytest.raises(SecurityError, match="SSRF policy"):
        validate_url("http://127.0.0.1:8000/api", allow_private_networks=False)


def test_validate_url_blocks_cloud_metadata():
    with pytest.raises(SecurityError, match="cloud metadata"):
        validate_url("http://169.254.169.254/latest/meta-data")


def test_validate_url_private_network_toggle():
    # When allow_private_networks is True, local addresses are permitted
    url = "http://127.0.0.1:8000/api"
    assert validate_url(url, allow_private_networks=True) == url


@pytest.mark.asyncio
async def test_http_client_manager_lifecycle():
    client = HttpClientManager.get_client()
    assert client is not None
    assert not client.is_closed
    await HttpClientManager.close()
    assert HttpClientManager._client is None


def test_resolve_url_placeholders(monkeypatch):
    from agents_md_server.http_client import resolve_url_placeholders

    monkeypatch.setenv("MY_HOST", "dbc-1234.cloud.databricks.com")
    monkeypatch.setenv("MY_FULL_URL", "https://api.example.com")

    # ${VAR} syntax
    assert (
        resolve_url_placeholders("${MY_HOST}/api/2.0/jobs")
        == "https://dbc-1234.cloud.databricks.com/api/2.0/jobs"
    )
    assert (
        resolve_url_placeholders("https://${MY_HOST}/api/2.0/jobs")
        == "https://dbc-1234.cloud.databricks.com/api/2.0/jobs"
    )

    # {VAR} uppercase syntax
    assert resolve_url_placeholders("{MY_FULL_URL}/v1/data") == "https://api.example.com/v1/data"

    # Double https:// cleanup
    assert (
        resolve_url_placeholders("https://${MY_FULL_URL}/v1/data")
        == "https://api.example.com/v1/data"
    )

    # Relative path with base_url
    assert (
        resolve_url_placeholders("/v1/items", base_url="https://api.example.com")
        == "https://api.example.com/v1/items"
    )

    # Missing ${VAR} raises ValueError
    with pytest.raises(ValueError, match="is not set or empty"):
        resolve_url_placeholders("${NON_EXISTENT_HOST_123}/api")

    # Lowercase path params left intact
    assert (
        resolve_url_placeholders("https://example.com/jobs/{job_id}")
        == "https://example.com/jobs/{job_id}"
    )


@pytest.mark.asyncio
async def test_execute_http_request_returns_full_list_intact(monkeypatch):
    """Ensure normal-sized lists are returned 100% intact with zero schema mutation."""
    monkeypatch.setattr(
        "socket.getaddrinfo",
        lambda host, port: [(2, 1, 6, "", ("93.184.216.34", port))],
    )

    fake_list = [{"id": i, "name": f"job-{i}"} for i in range(150)]
    mock_resp = MagicMock()
    mock_resp.is_redirect = False
    mock_resp.status_code = 200
    mock_resp.raise_for_status = MagicMock()
    mock_resp.headers = {"content-type": "application/json"}
    mock_resp.content = b"fake json content"
    mock_resp.json = MagicMock(return_value=fake_list)

    mock_client = MagicMock()
    mock_client.request = AsyncMock(return_value=mock_resp)

    with patch(
        "agents_md_server.http_client.HttpClientManager.get_client", return_value=mock_client
    ):
        res = await execute_http_request("https://api.example.com/jobs")
        # Assert full list is preserved directly without any missing items or wrapping
        assert isinstance(res, list)
        assert len(res) == 150
        assert res[104]["name"] == "job-104"


@pytest.mark.asyncio
async def test_execute_http_request_payload_too_large(monkeypatch):
    """Ensure catastrophic response sizes return an HTTP 413 error with pagination guidance."""
    monkeypatch.setattr(
        "socket.getaddrinfo",
        lambda host, port: [(2, 1, 6, "", ("93.184.216.34", port))],
    )

    mock_resp = MagicMock()
    mock_resp.is_redirect = False
    mock_resp.status_code = 200
    mock_resp.raise_for_status = MagicMock()
    mock_resp.headers = {"content-type": "application/json"}
    # Simulate a 2MB payload (exceeding settings.max_response_bytes)
    mock_resp.content = b"x" * (settings.max_response_bytes + 500)

    mock_client = MagicMock()
    mock_client.request = AsyncMock(return_value=mock_resp)

    with patch(
        "agents_md_server.http_client.HttpClientManager.get_client", return_value=mock_client
    ):
        res = await execute_http_request("https://api.example.com/massive-dump")
        assert res.get("status_code") == 413
        assert "exceeds maximum safety limit" in res.get("error")
        assert "page_token" in res.get("error") or "limit" in res.get("error")


@pytest.mark.asyncio
async def test_execute_http_request_blocks_binary(monkeypatch):
    monkeypatch.setattr(
        "socket.getaddrinfo",
        lambda host, port: [(2, 1, 6, "", ("93.184.216.34", port))],
    )

    mock_resp = MagicMock()
    mock_resp.is_redirect = False
    mock_resp.status_code = 200
    mock_resp.raise_for_status = MagicMock()
    mock_resp.headers = {"content-type": "application/pdf"}
    mock_resp.content = b"%PDF-1.4 binary data"

    mock_client = MagicMock()
    mock_client.request = AsyncMock(return_value=mock_resp)

    with patch(
        "agents_md_server.http_client.HttpClientManager.get_client", return_value=mock_client
    ):
        res = await execute_http_request("https://api.example.com/doc.pdf")
        assert "Binary content" in res.get("error")


@pytest.mark.asyncio
async def test_execute_http_request_allows_octet_stream_if_valid_json(monkeypatch):
    """Ensure application/octet-stream is not rejected if the payload is valid JSON."""
    monkeypatch.setattr(
        "socket.getaddrinfo",
        lambda host, port: [(2, 1, 6, "", ("93.184.216.34", port))],
    )

    mock_resp = MagicMock()
    mock_resp.is_redirect = False
    mock_resp.status_code = 200
    mock_resp.raise_for_status = MagicMock()
    mock_resp.headers = {"content-type": "application/octet-stream"}
    mock_resp.content = b'{"status": "ok", "items": [1, 2, 3]}'
    mock_resp.json = MagicMock(return_value={"status": "ok", "items": [1, 2, 3]})

    mock_client = MagicMock()
    mock_client.request = AsyncMock(return_value=mock_resp)

    with patch(
        "agents_md_server.http_client.HttpClientManager.get_client", return_value=mock_client
    ):
        res = await execute_http_request("https://api.example.com/data")
        assert res == {"status": "ok", "items": [1, 2, 3]}


@pytest.mark.asyncio
async def test_execute_http_request_blocks_redirect_to_private(monkeypatch):
    monkeypatch.setattr(
        "socket.getaddrinfo",
        lambda host, port: [(2, 1, 6, "", ("93.184.216.34", port))],
    )

    redirect_resp = MagicMock()
    redirect_resp.is_redirect = True
    redirect_resp.status_code = 302
    redirect_resp.headers = {"location": "http://127.0.0.1:8000/admin"}

    mock_client = MagicMock()
    mock_client.request = AsyncMock(return_value=redirect_resp)

    with patch(
        "agents_md_server.http_client.HttpClientManager.get_client", return_value=mock_client
    ):
        res = await execute_http_request(
            "https://api.example.com/login", allow_private_networks=False
        )
        assert res.get("status_code") == 403
        assert "Security / SSRF blocked redirect" in res.get("error")
