"""Skilldeck FastMCP Server implementation.

Provides:
- Dynamic Markdown Skills loading with hot-reloading support
- MCP Protocol Resources (agent://instructions, skills://index, skill://{name})
- MCP Prompts (agent-instructions, skill-instructions)
- Tools (get_skills, reload_skills, http_fetch, auth_http_fetch, cost_estimator)
- Clean lifespan management (HTTP connection pool cleanup)
"""

from __future__ import annotations

import json
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastmcp import FastMCP

from agents_md_server import __version__
from agents_md_server.config import Settings
from agents_md_server.config import settings as default_settings
from agents_md_server.http_client import HttpClientManager
from agents_md_server.skills.loader import build_system_prompt, load_skills
from agents_md_server.skills.models import Skill
from agents_md_server.tools import register_all_tools

logger = logging.getLogger(__name__)


class SkillsState:
    """Thread-safe state container for loaded skills and system prompt with hot-reloading."""

    def __init__(self, skills_dir: Path, agents_md_path: Path, preload_all: bool = False):
        self.skills_dir = skills_dir
        self.agents_md_path = agents_md_path
        self.preload_all = preload_all
        self.skills: dict[str, Skill] = {}
        self.system_prompt: str = ""
        self.reload()

    def reload(self) -> dict[str, Skill]:
        """Reload all skills from disk and rebuild system prompt."""
        self.skills = load_skills(self.skills_dir)
        self.system_prompt = build_system_prompt(
            self.agents_md_path, self.skills, preload_all=self.preload_all
        )
        logger.info(
            "Skills state reloaded: %s (preload_all=%s)",
            list(self.skills.keys()),
            self.preload_all,
        )
        return self.skills


def create_server(app_settings: Settings | None = None) -> FastMCP:
    """Factory function to build and configure the FastMCP server instance."""
    cfg = app_settings or default_settings

    # 1. Initialize SkillsState (loads skills and builds system prompt)
    skills_state = SkillsState(
        cfg.resolved_skills_dir,
        cfg.resolved_agents_md_path,
        preload_all=cfg.preload_all_skills,
    )

    logger.info("Initializing FastMCP server '%s' (v%s)", cfg.server_name, __version__)
    logger.info("Skills loaded: %s", list(skills_state.skills.keys()))

    # 2. Async lifespan for clean resource teardown
    @asynccontextmanager
    async def server_lifespan(server: FastMCP):
        logger.debug("Server starting up...")
        yield {"skills_state": skills_state}
        logger.debug("Server shutting down, closing connection pools...")
        await HttpClientManager.close()

    # 3. Create FastMCP instance with instructions and metadata
    mcp = FastMCP(
        name=cfg.server_name,
        version=__version__,
        instructions=skills_state.system_prompt,
        lifespan=server_lifespan,
    )
    # Attach state container to instance for programmatic reload access
    mcp.skills_state = skills_state

    # 4. Expose MCP Resources
    @mcp.resource("agent://instructions")
    def agent_instructions() -> str:
        """The agent's full system prompt and loaded skill instructions."""
        return skills_state.system_prompt

    @mcp.resource("skills://index")
    def skills_index() -> str:
        """JSON summary of all currently loaded skills and their metadata."""
        summaries = [s.to_summary_dict() for s in skills_state.skills.values()]
        return json.dumps(summaries, indent=2)

    # Dynamic resource template for any skill
    @mcp.resource("skill://{skill_name}")
    def dynamic_skill_resource(skill_name: str) -> str:
        """Read markdown instructions for any skill dynamically."""
        if skill_name in skills_state.skills:
            return skills_state.skills[skill_name].raw_content
        available = ", ".join(skills_state.skills.keys())
        return f"Skill '{skill_name}' not found. Available skills: {available}"

    # Also register individual resources for initial skills (for list_resources compatibility)
    for skill_name, skill_obj in skills_state.skills.items():
        uri = f"skill://{skill_name}"

        def _make_skill_resource(name: str):
            def _resource() -> str:
                if name in skills_state.skills:
                    return skills_state.skills[name].raw_content
                return f"Skill '{name}' not found."

            return _resource

        mcp.resource(
            uri,
            name=f"Skill: {skill_name}",
            description=skill_obj.description or f"Instructions for {skill_name}",
            mime_type="text/markdown",
        )(_make_skill_resource(skill_name))

    # 5. Expose MCP Prompts
    @mcp.prompt("agent-instructions")
    def agent_prompt() -> str:
        """Prompt template returning the full agent instructions."""
        return skills_state.system_prompt

    @mcp.prompt("skill-instructions")
    def skill_prompt(skill_name: str) -> str:
        """Prompt template returning instructions for a specific skill."""
        if skill_name in skills_state.skills:
            return skills_state.skills[skill_name].raw_content
        available = ", ".join(skills_state.skills.keys())
        return f"Skill '{skill_name}' not found. Available skills: {available}"

    # 6. Fallback tool: get_skills (optimized for LM Studio and models without resource injection)
    def _build_skill_descriptions_summary() -> str:
        if not skills_state.skills:
            return "No skills currently loaded."
        items = [f"- {name}: {s.description}" for name, s in skills_state.skills.items()]
        return "Available skills:\n" + "\n".join(items)

    @mcp.tool(
        description=(
            "Inspect and retrieve full API documentation, endpoints, and instructions for a specific skill. "
            "ALWAYS call this tool first before calling http_fetch or auth_http_fetch for any available skill.\n\n"
            + _build_skill_descriptions_summary()
        )
    )
    def get_skills(skill_name: str | None = None) -> str:
        """Retrieve loaded skill instructions.

        Args:
            skill_name: Name of a specific skill to fetch (e.g. 'azure-pricing').
                        If omitted, returns all loaded skills.
        """
        if not skills_state.skills:
            return "No skills are currently loaded."

        if skill_name:
            if skill_name in skills_state.skills:
                return f"## Skill: {skill_name}\n\n{skills_state.skills[skill_name].raw_content}"
            available = ", ".join(skills_state.skills.keys())
            return f"Skill '{skill_name}' not found. Available skills: {available}"

        # Return all skills
        parts = [f"## Skill: {name}\n\n{s.raw_content}" for name, s in skills_state.skills.items()]
        return "\n\n---\n\n".join(parts)

    @mcp.tool(
        description="Reload all skills from disk and update the active system prompt and skill catalog."
    )
    def reload_skills() -> str:
        """Reload all skills from disk and rebuild system prompt without server restart."""
        reloaded = skills_state.reload()
        names = ", ".join(reloaded.keys()) if reloaded else "none"
        return f"Successfully reloaded {len(reloaded)} skills: {names}"

    # 7. Register all tools (built-in and external)
    register_all_tools(mcp, cfg.resolved_tools_dir)

    return mcp


# Default server instance
mcp = create_server()
