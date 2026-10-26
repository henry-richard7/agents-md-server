"""Skilldeck (agents-md-server) - Production-ready Model Context Protocol (MCP) server."""

__version__ = "0.1.0"
__all__ = ["__version__", "create_server", "mcp"]


def __getattr__(name: str):
    # Lazy export to avoid circular imports and enable quick metadata access
    if name in ("create_server", "mcp"):
        from agents_md_server.server import create_server, mcp

        return create_server if name == "create_server" else mcp
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
