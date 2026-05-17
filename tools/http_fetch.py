"""
http_fetch.py
Generic HTTP tool — used by SKILL.md-driven agents to call external APIs.
The SKILL.md provides the URL structure and filters; this tool executes the call.
"""

import httpx


def register(mcp):

    @mcp.tool
    async def http_fetch(
        url: str,
        method: str = "GET",
        query_params: dict = None,
        body: dict = None,
        headers: dict = None,
    ) -> dict:
        """Make an HTTP request to any URL and return the JSON response.
        Use this when a skill instructs you to call an API endpoint.
        """

        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.request(
                method=method.upper(),
                url=url,
                params=query_params or {},
                json=body,
                headers=headers or {},
            )
            response.raise_for_status()
            
            try:
                return response.json()
            except ValueError:
                # If it's not valid JSON (like an IP address from api.ipify.org), return the raw text
                return {"text": response.text}
