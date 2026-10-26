"""Command Line Interface (CLI) for agents-md-server."""

from __future__ import annotations

import argparse

from agents_md_server import __version__
from agents_md_server.config import Settings
from agents_md_server.config import settings as default_settings
from agents_md_server.logging import configure_logging
from agents_md_server.server import create_server


def main() -> None:
    """CLI entrypoint."""
    parser = argparse.ArgumentParser(
        prog="agents-md-server",
        description="Skilldeck MCP Server - Multi-skill Agent Model Context Protocol Server",
    )
    parser.add_argument(
        "-v", "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )

    subparsers = parser.add_subparsers(dest="command", help="Available subcommands")

    # Command: run (default)
    run_parser = subparsers.add_parser("run", help="Run the MCP server")
    run_parser.add_argument(
        "--transport",
        choices=["stdio", "http", "sse", "streamable-http"],
        default=default_settings.transport,
        help="MCP transport mode (stdio, http, sse)",
    )
    run_parser.add_argument(
        "--host",
        default=default_settings.host,
        help="Host interface to bind HTTP/SSE server to",
    )
    run_parser.add_argument(
        "-p", "--port",
        type=int,
        default=default_settings.port,
        help="Port for HTTP/SSE server",
    )
    run_parser.add_argument(
        "--log-level",
        default=default_settings.log_level,
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Log level",
    )

    # Command: inspect
    subparsers.add_parser(
        "inspect", help="Inspect loaded skills, tools, and resources without starting server"
    )

    # Parse arguments
    args = parser.parse_args()

    command = args.command or "run"

    if command == "inspect":
        logger = configure_logging("INFO", stdio_mode=False)
        server = create_server()
        skills_dir = default_settings.resolved_skills_dir
        print("\n=== Skilldeck Server Inspection ===")
        print(f"Version:      {__version__}")
        print(f"Skills Dir:   {skills_dir}")
        print(f"Tools Dir:    {default_settings.resolved_tools_dir}")
        print(f"AGENTS.md:    {default_settings.resolved_agents_md_path}")
        print("\nServer initialized successfully.")
        return

    # Run command
    transport = getattr(args, "transport", default_settings.transport)
    host = getattr(args, "host", default_settings.host)
    port = getattr(args, "port", default_settings.port)
    log_level = getattr(args, "log_level", default_settings.log_level)

    stdio_mode = transport == "stdio"
    logger = configure_logging(level=log_level, stdio_mode=stdio_mode)

    logger.info("Starting Skilldeck MCP server (v%s) with transport '%s'", __version__, transport)

    app_settings = Settings(
        host=host,
        port=port,
        transport=transport,
        log_level=log_level,
    )
    server = create_server(app_settings)

    if transport == "stdio":
        # In stdio mode, show_banner must be False to preserve JSON-RPC on stdout
        server.run(transport="stdio", show_banner=False)
    else:
        logger.info("Serving MCP at http://%s:%d/mcp", host, port)
        server.run(
            transport=transport,
            host=host,
            port=port,
            stateless_http=app_settings.stateless_http,
        )


if __name__ == "__main__":
    main()
