"""
skilldeck — FastMCP server (MCP only)
  *  /mcp  → MCP protocol (Claude Desktop, Cursor, VS Code, etc.)
"""

from pathlib import Path
from fastmcp import FastMCP
import importlib.util
import os

from dotenv import load_dotenv

load_dotenv()

# ── Paths ──────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent
SKILLS_DIR = BASE_DIR / "skills"
TOOLS_DIR = BASE_DIR / "tools"
AGENTS_MD = BASE_DIR / "AGENTS.md"


# ── Load all SKILL.md files at startup ────────────────────────────────────
def load_skills_content(skills_dir: Path) -> dict[str, str]:
    """Read every SKILL.md and return a dict of {skill_name: content}."""
    skills = {}
    if not skills_dir.exists():
        return skills
    for skill_dir in sorted(skills_dir.iterdir()):
        if not skill_dir.is_dir():
            continue
        skill_md = skill_dir / "SKILL.md"
        if not skill_md.exists():
            continue
        skills[skill_dir.name] = skill_md.read_text(encoding="utf-8")
        print(f"OK skill loaded: {skill_dir.name}")
    return skills


SKILLS = load_skills_content(SKILLS_DIR)


# ── Build system prompt ────────────────────────────────────────────────────
def build_system_prompt() -> str:
    base = AGENTS_MD.read_text(encoding="utf-8") if AGENTS_MD.exists() else ""
    if not SKILLS:
        return base
    skill_blocks = "\n\n---\n\n".join(
        f"## Skill: {name}\n\n{content}" for name, content in SKILLS.items()
    )
    full = f"{base}\n\n# Loaded Skills\n\n{skill_blocks}"
    print(f"System prompt: {len(full.split())} words, {len(full)} chars")
    return full


SYSTEM_PROMPT = build_system_prompt()

# ── FastMCP server ─────────────────────────────────────────────────────────
# Pass instructions= so compliant clients (Claude Desktop etc.) get it.
# LM Studio may ignore this — see get_skills tool below as fallback.
mcp = FastMCP("skilldeck")


# ── Fallback: expose skills via tool description ───────────────────────────
# LM Studio injects tool *descriptions* into the model context on every
# request, even when it ignores the instructions= field. So we embed the
# full skill content in the description so it always reaches the model.


def _build_skill_tool_description() -> str:
    if not SKILLS:
        return "No skills loaded."
    lines = [
        "IMPORTANT: You have skills loaded. Read them and follow their "
        "instructions exactly before handling any user request.\n"
    ]
    for name, content in SKILLS.items():
        lines.append(f"=== SKILL: {name} ===\n{content}\n")
    return "\n".join(lines)


@mcp.tool(description=_build_skill_tool_description())
async def get_skills() -> str:
    """Returns all loaded skill instructions. Call this before handling
    any user request to ensure you follow the correct API endpoints and steps."""
    if not SKILLS:
        return "No skills are currently loaded."
    parts = [f"## {name}\n\n{content}" for name, content in SKILLS.items()]
    return "\n\n---\n\n".join(parts)


# ── AGENTS.md as MCP resource ──────────────────────────────────────────────
if AGENTS_MD.exists():

    @mcp.resource("agent://instructions")
    def agent_instructions() -> str:
        """The agent's full instructions including all loaded skills."""
        return SYSTEM_PROMPT


# ── Auto-load tools from tools/ ────────────────────────────────────────────
def load_tools(tools_dir: Path) -> None:
    if not tools_dir.exists():
        print(f"WARN tools dir not found: {tools_dir}")
        return
    for tool_file in sorted(tools_dir.glob("*.py")):
        if tool_file.name.startswith("_"):
            continue
        spec = importlib.util.spec_from_file_location(tool_file.stem, tool_file)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        if hasattr(mod, "register"):
            mod.register(mcp)
            print(f"OK tool loaded: {tool_file.name}")
        else:
            print(f"WARN skipped {tool_file.name} — no register() function")


load_tools(TOOLS_DIR)


# ── Entry point ────────────────────────────────────────────────────────────
if __name__ == "__main__":
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))
    transport = os.getenv("TRANSPORT", "http")

    print(f"\n[RUNNING] skilldeck MCP server")
    print(f"   Skills loaded: {list(SKILLS.keys())}")
    print(f"   System prompt: {len(SYSTEM_PROMPT)} chars")

    if transport == "stdio":
        mcp.run(transport="stdio")
    else:
        print(f"   Transport -> {transport}  http://{host}:{port}/mcp")
        mcp.run(
            transport=transport,
            host=host,
            port=port,
            stateless_http=True,
        )
