"""Skilldeck FastMCP Server implementation.

Provides:
- Dynamic Markdown Skills loading
- MCP Protocol Resources (agent://instructions, skills://index, skill://{name})
- MCP Prompts (agent-instructions, skill-instructions)
- Fallback tool (get_skills)
- Clean lifespan management (HTTP connection pool cleanup)
"""

from __future__ import annotations

import json
import logging
from contextlib import asynccontextmanager

from fastmcp import FastMCP

from agents_md_server import __version__
from agents_md_server.config import Settings
from agents_md_server.config import settings as default_settings
from agents_md_server.http_client import HttpClientManager
from agents_md_server.skills.loader import build_system_prompt, load_skills
from agents_md_server.skills.models import Skill
from agents_md_server.tools import register_all_tools

logger = logging.getLogger(__name__)


def create_server(app_settings: Settings | None = None) -> FastMCP:
    """Factory function to build and configure the FastMCP server instance."""
    cfg = app_settings or default_settings

    # 1. Load skills and build system prompt
    skills_dir = cfg.resolved_skills_dir
    agents_md_path = cfg.resolved_agents_md_path
    skills: dict[str, Skill] = load_skills(skills_dir)
    system_prompt: str = build_system_prompt(agents_md_path, skills)

    logger.info("Initializing FastMCP server '%s' (v%s)", cfg.server_name, __version__)
    logger.info("Skills loaded: %s", list(skills.keys()))

    # 2. Async lifespan for clean resource teardown
    @asynccontextmanager
    async def server_lifespan(server: FastMCP):
        logger.debug("Server starting up...")
        yield {"skills": skills, "system_prompt": system_prompt}
        logger.debug("Server shutting down, closing connection pools...")
        await HttpClientManager.close()

    # 3. Create FastMCP instance with instructions and metadata
    mcp = FastMCP(
        name=cfg.server_name,
        version=__version__,
        instructions=system_prompt,
        lifespan=server_lifespan,
    )

    # 4. Expose MCP Resources
    @mcp.resource("agent://instructions")
    def agent_instructions() -> str:
        """The agent's full system prompt and loaded skill instructions."""
        return system_prompt

    @mcp.resource("skills://index")
    def skills_index() -> str:
        """JSON summary of all currently loaded skills and their metadata."""
        summaries = [s.to_summary_dict() for s in skills.values()]
        return json.dumps(summaries, indent=2)

    for skill_name, skill_obj in skills.items():
        # Register a direct resource for each loaded skill
        uri = f"skill://{skill_name}"
        raw_text = skill_obj.raw_content

        def _make_skill_resource(text: str):
            def _resource() -> str:
                return text

            return _resource

        mcp.resource(
            uri,
            name=f"Skill: {skill_name}",
            description=skill_obj.description or f"Instructions for {skill_name}",
            mime_type="text/markdown",
        )(_make_skill_resource(raw_text))

    # 5. Expose MCP Prompts
    @mcp.prompt("agent-instructions")
    def agent_prompt() -> str:
        """Prompt template returning the full agent instructions."""
        return system_prompt

    @mcp.prompt("skill-instructions")
    def skill_prompt(skill_name: str) -> str:
        """Prompt template returning instructions for a specific skill."""
        if skill_name in skills:
            return skills[skill_name].raw_content
        available = ", ".join(skills.keys())
        return f"Skill '{skill_name}' not found. Available skills: {available}"

    # 6. Fallback tool: get_skills (optimized for LM Studio and models without resource injection)
    def _build_skill_descriptions_summary() -> str:
        if not skills:
            return "No skills currently loaded."
        items = [f"- {name}: {s.description}" for name, s in skills.items()]
        return "Available skills:\n" + "\n".join(items)

    @mcp.tool(
        description=(
            "Inspect and retrieve loaded skill instructions and API endpoints. "
            "Call this if you need instructions for a specific skill, or leave skill_name empty to list all skills.\n\n"
            + _build_skill_descriptions_summary()
        )
    )
    def get_skills(skill_name: str | None = None) -> str:
        """Retrieve loaded skill instructions.

        Args:
            skill_name: Name of a specific skill to fetch (e.g. 'azure-pricing').
                        If omitted, returns all loaded skills.
        """
        if not skills:
            return "No skills are currently loaded."

        if skill_name:
            if skill_name in skills:
                return f"## Skill: {skill_name}\n\n{skills[skill_name].raw_content}"
            available = ", ".join(skills.keys())
            return f"Skill '{skill_name}' not found. Available skills: {available}"

        # Return all skills
        parts = [f"## Skill: {name}\n\n{s.raw_content}" for name, s in skills.items()]
        return "\n\n---\n\n".join(parts)

    # 7. Register all tools (built-in and external)
    register_all_tools(mcp, cfg.resolved_tools_dir)

    return mcp


# Default server instance
mcp = create_server()
