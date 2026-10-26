import pytest

from agents_md_server.http_client import HttpClientManager, SecurityError, validate_url


def test_validate_url_valid():
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
