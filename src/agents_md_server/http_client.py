"""HTTP Client with SSRF protection, connection pooling, and lifecycle management."""

from __future__ import annotations

import ipaddress
import logging
import socket
from typing import Any
from urllib.parse import urlsplit

import httpx

from agents_md_server.config import settings

logger = logging.getLogger(__name__)

# Cloud metadata IP addresses to strictly guard against credential exfiltration
BLOCKED_METADATA_IPS = {
    "169.254.169.254",  # AWS, GCP, Azure, OpenStack instance metadata
    "fd00:ec2::254",    # AWS IPv6 instance metadata
    "100.100.100.200",  # Alibaba Cloud metadata
}


class SecurityError(Exception):
    """Raised when an HTTP request violates security policies (e.g. SSRF protection)."""


def validate_url(url: str, allow_private_networks: bool | None = None) -> str:
    """Validate URL scheme and ensure it does not resolve to private/local/metadata IPs.

    Args:
        url: The URL to validate.
        allow_private_networks: Override settings.allow_private_networks.

    Returns:
        The validated URL.

    Raises:
        ValueError: If the URL or scheme is invalid.
        SecurityError: If the target resolves to a forbidden IP address.
    """
    if allow_private_networks is None:
        allow_private_networks = settings.allow_private_networks

    parsed = urlsplit(url)
    if not parsed.scheme or parsed.scheme.lower() not in ("http", "https"):
        raise ValueError(f"Invalid URL scheme: '{parsed.scheme}'. Only 'http' and 'https' are allowed.")

    hostname = parsed.hostname
    if not hostname:
        raise ValueError("URL does not contain a valid hostname.")

    # Always block explicit localhost references if private networks are disabled
    normalized_host = hostname.lower().strip()
    if not allow_private_networks and normalized_host in (
        "localhost",
        "localhost.localdomain",
        "0.0.0.0",
        "::1",
    ):
        raise SecurityError(f"Access to '{hostname}' is blocked by SSRF policy.")

    # Check for direct metadata IP access regardless
    if normalized_host in BLOCKED_METADATA_IPS:
        raise SecurityError(f"Access to cloud metadata endpoint '{hostname}' is forbidden.")

    # DNS resolution check if private networks are disabled
    if not allow_private_networks:
        try:
            # Resolve hostname to all associated IP addresses
            addr_info = socket.getaddrinfo(hostname, parsed.port or (443 if parsed.scheme == "https" else 80))
            for family, _, _, _, sockaddr in addr_info:
                ip_str = sockaddr[0]
                if ip_str in BLOCKED_METADATA_IPS:
                    raise SecurityError(f"Resolved address '{ip_str}' is a forbidden cloud metadata IP.")

                ip_obj = ipaddress.ip_address(ip_str)
                if (
                    ip_obj.is_private
                    or ip_obj.is_loopback
                    or ip_obj.is_link_local
                    or ip_obj.is_reserved
                    or ip_obj.is_multicast
                ):
                    raise SecurityError(
                        f"Resolved address '{ip_str}' for host '{hostname}' is a private or local network address. "
                        "Access is blocked by SSRF policy."
                    )
        except socket.gaierror as e:
            logger.debug("DNS resolution failed for %s: %s", hostname, e)
            # Let httpx handle DNS error during request execution

    return url


class HttpClientManager:
    """Manages a shared, pooled httpx.AsyncClient with keepalive connections."""

    _client: httpx.AsyncClient | None = None

    @classmethod
    def get_client(cls) -> httpx.AsyncClient:
        """Get or create the shared httpx.AsyncClient."""
        if cls._client is None or cls._client.is_closed:
            limits = httpx.Limits(
                max_keepalive_connections=20,
                max_connections=50,
                keepalive_expiry=30.0,
            )
            cls._client = httpx.AsyncClient(
                timeout=httpx.Timeout(settings.http_timeout_seconds),
                limits=limits,
                headers={"User-Agent": "Skilldeck-MCP/0.1.0 (FastMCP)"},
                follow_redirects=True,
            )
        return cls._client

    @classmethod
    async def close(cls) -> None:
        """Close the shared client connection pool gracefully."""
        if cls._client is not None and not cls._client.is_closed:
            await cls._client.aclose()
            cls._client = None
            logger.debug("HTTP client connection pool closed.")


async def execute_http_request(
    url: str,
    method: str = "GET",
    params: dict[str, Any] | None = None,
    json_body: Any = None,
    headers: dict[str, str] | None = None,
    allow_private_networks: bool | None = None,
) -> dict[str, Any]:
    """Validate URL, perform HTTP request using shared connection pool, and format response.

    Returns:
        Structured response dictionary containing status, headers, and parsed content or error.
    """
    try:
        validated_url = validate_url(url, allow_private_networks=allow_private_networks)
    except (ValueError, SecurityError) as e:
        return {"error": f"Security / Validation error: {e!s}", "status_code": 400}

    client = HttpClientManager.get_client()

    try:
        response = await client.request(
            method=method.upper(),
            url=validated_url,
            params=params or {},
            json=json_body,
            headers=headers or {},
        )
        response.raise_for_status()

        try:
            return response.json()
        except ValueError:
            return {"text": response.text}

    except httpx.HTTPStatusError as e:
        error_text = e.response.text[:1000] if e.response else "No response body"
        return {
            "error": f"HTTP {e.response.status_code} {e.response.reason_phrase}: {error_text}",
            "status_code": e.response.status_code,
        }
    except httpx.TimeoutException:
        return {
            "error": f"Request to {url} timed out after {settings.http_timeout_seconds} seconds.",
            "status_code": 408,
        }
    except httpx.RequestError as e:
        return {
            "error": f"Network request error: {e!s}",
            "status_code": 502,
        }
