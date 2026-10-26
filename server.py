"""skilldeck — FastMCP server entrypoint shim.

Delegates to the production agents_md_server package.
Exposes `mcp` and `create_server` for compatibility with FastMCP CLI and direct runs.
"""

from agents_md_server import create_server, mcp
from agents_md_server.cli import main

__all__ = ["create_server", "main", "mcp"]

if __name__ == "__main__":
    main()
