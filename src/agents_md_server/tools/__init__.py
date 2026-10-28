"""Tools registration and auto-discovery for agents-md-server."""

from __future__ import annotations

import importlib.util
import logging
from pathlib import Path

from fastmcp import FastMCP

from agents_md_server.tools import auth_http_fetch, cost_estimator, http_fetch

logger = logging.getLogger(__name__)


def register_all_tools(mcp: FastMCP, external_tools_dir: Path | None = None) -> None:
    """Register all built-in tools and optionally auto-discover custom external tools."""
    # Register core built-in tools
    http_fetch.register(mcp)
    auth_http_fetch.register(mcp)
    cost_estimator.register(mcp)
    logger.info("Registered built-in tools: http_fetch, auth_http_fetch, cost_estimator")

    # Optionally load external tools from a custom directory
    if external_tools_dir and external_tools_dir.exists():
        for tool_file in sorted(external_tools_dir.glob("*.py")):
            if tool_file.name.startswith("_"):
                continue
            # Skip if it matches a built-in name to avoid duplicate registration
            if tool_file.stem in ("http_fetch", "auth_http_fetch", "cost_estimator"):
                continue

            try:
                spec = importlib.util.spec_from_file_location(tool_file.stem, tool_file)
                if spec and spec.loader:
                    mod = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(mod)
                    if hasattr(mod, "register"):
                        mod.register(mcp)
                        logger.info("Registered external tool module: %s", tool_file.name)
                    else:
                        logger.warning(
                            "Skipped external tool %s (missing register(mcp))", tool_file.name
                        )
            except (ImportError, AttributeError, ValueError, OSError) as e:
                logger.error("Failed to load external tool %s: %s", tool_file.name, e)


__all__ = ["auth_http_fetch", "cost_estimator", "http_fetch", "register_all_tools"]
