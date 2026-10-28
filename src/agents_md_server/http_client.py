"""HTTP Client with SSRF protection, connection pooling, and lifecycle management."""

from __future__ import annotations

import ipaddress
import logging
import os
import re
import socket
from typing import Any
from urllib.parse import urljoin, urlsplit

import httpx

from agents_md_server.config import PROJECT_ROOT, settings

logger = logging.getLogger(__name__)

# Cloud metadata IP addresses to strictly guard against credential exfiltration
BLOCKED_METADATA_IPS = {
    "169.254.169.254",  # AWS, GCP, Azure, OpenStack instance metadata
    "fd00:ec2::254",  # AWS IPv6 instance metadata
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
        raise ValueError(
            f"Invalid URL scheme: '{parsed.scheme}'. Only 'http' and 'https' are allowed."
        )

    hostname = parsed.hostname
    if not hostname:
        raise ValueError("URL does not contain a valid hostname.")

    normalized_host = hostname.lower().strip()

    # Fast-path localhost check
    if not allow_private_networks and normalized_host in (
        "localhost",
        "localhost.localdomain",
        "127.0.0.1",
        "0.0.0.0",
        "::1",
    ):
        raise SecurityError(f"Access to '{hostname}' is blocked by SSRF policy.")

    # Check for direct metadata IP access regardless
    if normalized_host in BLOCKED_METADATA_IPS:
        raise SecurityError(f"Access to cloud metadata endpoint '{hostname}' is forbidden.")

    # Direct IP literal check (avoid DNS lookup if host is already an IP address)
    try:
        ip_obj = ipaddress.ip_address(normalized_host)
        if not allow_private_networks and (
            ip_obj.is_private
            or ip_obj.is_loopback
            or ip_obj.is_link_local
            or ip_obj.is_reserved
            or ip_obj.is_multicast
        ):
            raise SecurityError(
                f"Direct IP access to '{hostname}' is a private or local network address. "
                "Access is blocked by SSRF policy."
            )
        # If it's a valid public IP literal, no need for DNS resolution
        return url
    except ValueError:
        # Not an IP literal; proceed to domain DNS resolution
        pass

    # DNS resolution check if private networks are disabled
    if not allow_private_networks:
        try:
            # Resolve hostname to all associated IP addresses
            addr_info = socket.getaddrinfo(
                hostname, parsed.port or (443 if parsed.scheme == "https" else 80)
            )
            for family, _, _, _, sockaddr in addr_info:
                ip_str = sockaddr[0]
                if ip_str in BLOCKED_METADATA_IPS:
                    raise SecurityError(
                        f"Resolved address '{ip_str}' is a forbidden cloud metadata IP."
                    )

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
                follow_redirects=False,  # Redirects are validated and handled hop-by-hop for SSRF security
            )
        return cls._client

    @classmethod
    async def close(cls) -> None:
        """Close the shared client connection pool gracefully."""
        if cls._client is not None and not cls._client.is_closed:
            await cls._client.aclose()
            cls._client = None
            logger.debug("HTTP client connection pool closed.")


def resolve_env_var(name: str) -> str | None:
    """Retrieve an environment variable from os.environ or directly from .env file."""
    val = os.getenv(name)
    if val:
        return val.strip()

    from dotenv import dotenv_values

    env_path = PROJECT_ROOT / ".env"
    if env_path.exists():
        env_vars = dotenv_values(env_path)
        raw = env_vars.get(name)
        if raw:
            os.environ[name] = raw
            return raw.strip()
    return None


def resolve_url_placeholders(url: str, base_url: str | None = None) -> str:
    """Resolve environment variable placeholders in URL and join with optional base_url.

    Supports:
    - ${ENV_VAR} syntax: e.g. "https://${DATABRICKS_HOST}/api/..." or "${DATABRICKS_HOST}/api/..."
    - {ENV_VAR} syntax for uppercase env vars: e.g. "{DATABRICKS_HOST}/api/..."
    - base_url prepending if url is a relative path (e.g. "/api/...")
    """
    if base_url:
        base = base_url.rstrip("/")
        if not base.startswith(("http://", "https://")):
            base = f"https://{base}"
        if not url.startswith(("http://", "https://", "${", "{")):
            url = f"{base}/{url.lstrip('/')}"

    def _replace_var(match: re.Match[str]) -> str:
        var_name = match.group(1)
        val = resolve_env_var(var_name)
        if val is not None:
            return val.rstrip("/")
        if match.group(0).startswith("${"):
            raise ValueError(
                f"Environment variable '{var_name}' referenced in URL is not set or empty in .env"
            )
        return match.group(0)

    # 1. Replace ${VAR_NAME}
    url = re.sub(r"\$\{([A-Za-z0-9_]+)\}", _replace_var, url)

    # 2. Replace {VAR_NAME} (uppercase env vars)
    url = re.sub(r"\{([A-Z0-9_]+)\}", _replace_var, url)

    # Clean double scheme if both URL and env var specified https://
    url = re.sub(r"^https?://https?://", "https://", url)

    # Ensure http:// or https:// scheme if bare domain was injected
    if not url.startswith(("http://", "https://")) and not url.startswith("/"):
        url = f"https://{url}"

    return url


async def execute_http_request(
    url: str,
    method: str = "GET",
    params: dict[str, Any] | None = None,
    json_body: Any = None,
    headers: dict[str, str] | None = None,
    allow_private_networks: bool | None = None,
    base_url: str | None = None,
) -> dict[str, Any]:
    """Validate URL, perform HTTP request with SSRF-safe redirect following and size protection.

    Returns:
        Structured response dictionary containing status, headers, and parsed content or error.
    """
    try:
        resolved_url = resolve_url_placeholders(url, base_url=base_url)
        validated_url = validate_url(resolved_url, allow_private_networks=allow_private_networks)
    except (ValueError, SecurityError) as e:
        return {"error": f"Security / Validation error: {e!s}", "status_code": 400}

    client = HttpClientManager.get_client()

    current_url = validated_url
    current_method = method.upper()
    current_params = params or {}
    current_headers = dict(headers or {})
    current_body = json_body
    redirect_count = 0

    try:
        # Loop to safely follow redirects while validating each target against SSRF
        while True:
            # Determine whether payload should be sent as form data or JSON
            content_type_val = (
                current_headers.get("Content-Type") or current_headers.get("content-type") or ""
            )
            is_form = "application/x-www-form-urlencoded" in content_type_val.lower()

            # Determine whether payload should be sent as form data or JSON
            content_type_val = (
                current_headers.get("Content-Type") or current_headers.get("content-type") or ""
            )
            is_form = "application/x-www-form-urlencoded" in content_type_val.lower()

            response = await client.request(
                method=current_method,
                url=current_url,
                params=current_params,
                json=current_body if not is_form else None,
                data=current_body if is_form else None,
                headers=current_headers,
            )

            # Check for HTTP redirect status codes (301, 302, 303, 307, 308)
            if response.is_redirect and "location" in response.headers:
                if redirect_count >= settings.max_redirects:
                    return {
                        "error": f"Too many redirects (exceeded limit of {settings.max_redirects})",
                        "status_code": response.status_code,
                    }
                redirect_count += 1
                location = response.headers["location"]
                next_url = urljoin(current_url, location)

                # Validate next_url for SSRF security
                try:
                    current_url = validate_url(
                        next_url, allow_private_networks=allow_private_networks
                    )
                except (ValueError, SecurityError) as e:
                    return {
                        "error": f"Security / SSRF blocked redirect to '{location}': {e!s}",
                        "status_code": 403,
                    }

                # HTTP 301, 302, 303 typically switch to GET and drop payload
                if response.status_code in (301, 302, 303):
                    current_method = "GET"
                    current_body = None
                    current_params = {}
                continue

            break

        response.raise_for_status()

        # 1. Catastrophic payload protection: check byte size before processing
        content_bytes = response.content
        content_size = len(content_bytes)
        if content_size > settings.max_response_bytes:
            size_mb = content_size / 1_000_000
            max_mb = settings.max_response_bytes / 1_000_000
            return {
                "error": (
                    f"Response payload ({size_mb:.1f} MB) exceeds maximum safety limit ({max_mb:.1f} MB). "
                    "To prevent context window overflow, please narrow your request using API query parameters "
                    "(such as 'limit', 'page_size', 'page_token', or 'offset') or apply specific filters."
                ),
                "status_code": 413,
                "size_bytes": content_size,
            }

        # 2. Binary content detection
        content_type = response.headers.get("content-type", "").lower()
        is_explicit_binary = any(
            t in content_type
            for t in (
                "image/",
                "video/",
                "audio/",
                "application/pdf",
                "application/zip",
                "application/gzip",
            )
        )
        has_null_bytes = b"\x00" in content_bytes[:1024]

        if is_explicit_binary or (("octet-stream" in content_type) and has_null_bytes):
            return {
                "error": f"Binary content ({content_type or 'binary stream'}) is not supported directly. Expected JSON or text.",
                "status_code": response.status_code,
            }

        # 3. Parse JSON or text without mutating schema or truncating items
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
