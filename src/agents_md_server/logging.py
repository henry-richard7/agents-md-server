"""Logging configuration for agents-md-server.

CRITICAL FOR MCP COMPLIANCE:
When running in stdio transport mode, standard output (sys.stdout) is strictly
reserved for MCP JSON-RPC protocol messages. Writing logs or arbitrary prints
to stdout corrupts client communication (Claude Desktop, Cursor, etc.).
All application logging is routed to sys.stderr.
"""

from __future__ import annotations

import logging
import sys


def configure_logging(level: str = "INFO", stdio_mode: bool = False) -> logging.Logger:
    """Configure root and package loggers to output safely to stderr.

    Args:
        level: Desired log level string (DEBUG, INFO, WARNING, ERROR, CRITICAL).
        stdio_mode: Whether the server is running in stdio transport mode.

    Returns:
        The configured package root logger.
    """
    numeric_level = getattr(logging, level.upper(), logging.INFO)

    root_logger = logging.getLogger()
    root_logger.setLevel(numeric_level)

    # Remove existing handlers to avoid duplicates
    for handler in list(root_logger.handlers):
        root_logger.removeHandler(handler)

    handler = logging.StreamHandler(sys.stderr)
    handler.setLevel(numeric_level)

    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(formatter)
    root_logger.addHandler(handler)

    # Quiet overly chatty third-party loggers unless DEBUG is requested
    if numeric_level > logging.DEBUG:
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("httpcore").setLevel(logging.WARNING)
        logging.getLogger("uvicorn").setLevel(logging.INFO)
        logging.getLogger("uvicorn.access").setLevel(logging.WARNING)

    logger = logging.getLogger("agents_md_server")
    logger.setLevel(numeric_level)
    return logger
