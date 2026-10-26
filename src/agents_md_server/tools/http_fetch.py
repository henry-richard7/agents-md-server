"""http_fetch tool for MCP.

Generic HTTP tool used by SKILL.md-driven agents to call external APIs.
The skill provides the URL structure and filters; this tool safely executes the call.
"""

from __future__ import annotations

from typing import Any

from fastmcp import Context, FastMCP

from agents_md_server.http_client import execute_http_request


def register(mcp: FastMCP) -> None:
    """Register the http_fetch tool with the FastMCP server."""

    @mcp.tool
    async def http_fetch(
        url: str,
        method: str = "GET",
        query_params: dict[str, Any] | None = None,
        body: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        ctx: Context | None = None,
    ) -> dict[str, Any]:
        """Make an HTTP request to any URL and return the JSON response.

        Use this when a skill instructs you to call an API endpoint.

        Args:
            url: The target endpoint URL.
            method: HTTP method (GET, POST, PUT, DELETE, PATCH). Defaults to GET.
            query_params: Optional URL query parameters dict.
            body: Optional JSON payload dict for POST/PUT/PATCH requests.
            headers: Optional HTTP headers dict.
            ctx: MCP request context.
        """
        if ctx:
            await ctx.info(f"Executing HTTP {method.upper()} to {url}")

        return await execute_http_request(
            url=url,
            method=method,
            params=query_params,
            json_body=body,
            headers=headers,
        )
