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


def _build_get_skills_description(skills: dict[str, Skill], preload_all: bool) -> str:
    """Generate the description for get_skills tool based on preload mode and available skills."""
    if preload_all:
        base = (
            "Inspect and retrieve API documentation and instructions for a specific skill. "
            "Note: All skill runbooks are already preloaded in your system prompt, so calling this tool is optional."
        )
    else:
        base = (
            "Inspect and retrieve full API documentation, endpoints, and instructions for a specific skill. "
            "Call this tool with `skill_name` to load a skill's runbook before calling http_fetch or auth_http_fetch."
        )

    if not skills:
        summary = "No skills currently loaded."
    else:
        items = [f"- {name}: {s.description}" for name, s in skills.items()]
        summary = "Available skills:\n" + "\n".join(items)

    return f"{base}\n\n{summary}"


def _sync_get_skills_description(mcp: FastMCP, skills: dict[str, Skill], preload_all: bool) -> None:
    """Update get_skills tool description in-place in FastMCP component registry."""
    new_desc = _build_get_skills_description(skills, preload_all)
    for key, comp in getattr(mcp.local_provider, "_components", {}).items():
        if key.startswith("tool:get_skills"):
            comp.description = new_desc


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
    @mcp.tool(
        description=_build_get_skills_description(skills_state.skills, cfg.preload_all_skills)
    )
    def get_skills(skill_name: str | None = None) -> str:
        """Retrieve loaded skill instructions or view available skills.

        Args:
            skill_name: Optional name of a specific skill to fetch (e.g. 'salesforce', 'azure-pricing').
                        If omitted or None, returns a compact index of all available skills.
        """
        if not skills_state.skills:
            return "No skills are currently loaded."

        if skill_name and skill_name.strip():
            name = skill_name.strip()
            if name in skills_state.skills:
                return f"## Skill: {name}\n\n{skills_state.skills[name].raw_content}"
            available = ", ".join(skills_state.skills.keys())
            return f"Skill '{name}' not found. Available skills: {available}"

        # Return compact summary catalog of available skills — do NOT dump raw content
        items = []
        for name, s in skills_state.skills.items():
            compat = f" ({s.compatibility})" if s.compatibility else ""
            items.append(f"- **{name}**: {s.description}{compat}")

        return (
            "Available skills:\n"
            + "\n".join(items)
            + "\n\nTo view full instructions and endpoints for a skill, call `get_skills(skill_name='<name>')`."
        )

    @mcp.tool(
        description="Reload all skills from disk and update the active system prompt and skill catalog."
    )
    def reload_skills() -> str:
        """Reload all skills from disk and rebuild system prompt without server restart."""
        reloaded = skills_state.reload()
        mcp.instructions = skills_state.system_prompt
        _sync_get_skills_description(mcp, reloaded, skills_state.preload_all)
        names = ", ".join(reloaded.keys()) if reloaded else "none"
        return f"Successfully reloaded {len(reloaded)} skills: {names}"

    # 7. Register all tools (built-in and external)
    register_all_tools(mcp, cfg.resolved_tools_dir)

    return mcp


# Default server instance
mcp = create_server()
