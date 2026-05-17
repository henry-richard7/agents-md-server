"""
skilldeck — FastMCP server (MCP only)
  *  /mcp  → MCP protocol (Claude Desktop, Cursor, VS Code, etc.)
"""

from pathlib import Path
from fastmcp import FastMCP
from fastmcp.server.providers.skills import SkillsDirectoryProvider
import importlib.util
import os

from dotenv import load_dotenv

load_dotenv()

# ── Paths ──────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent
SKILLS_DIR = BASE_DIR / "skills"
TOOLS_DIR = BASE_DIR / "tools"

# ── FastMCP server ─────────────────────────────────────────────────────────
mcp = FastMCP("skilldeck")


# ── Skills — one SkillProvider per subdirectory containing SKILL.md ────────
if SKILLS_DIR.exists():
    mcp.add_provider(
        SkillsDirectoryProvider(
            roots=SKILLS_DIR,
            reload=bool(os.getenv("SKILLS_RELOAD", "")),
        )
    )
    print(f"OK skills loaded from {SKILLS_DIR}")
else:
    print(f"WARN skills dir not found: {SKILLS_DIR}")


# ── AGENTS.md as MCP resource ──────────────────────────────────────────────
_agents_md = BASE_DIR / "AGENTS.md"

if _agents_md.exists():
    _content = _agents_md.read_text(encoding="utf-8")

    @mcp.resource("agent://instructions")
    def agent_instructions() -> str:
        """The agent's instructions from AGENTS.md"""
        return _content

else:
    print("WARN AGENTS.md not found")


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
    transport = os.getenv("TRANSPORT", "http")  # "http", "sse", or "stdio"

    print(f"\n[RUNNING] skilldeck MCP server")

    if transport == "stdio":
        print("Transport -> stdio")
        mcp.run(transport="stdio")
    else:
        print(f"   Transport -> {transport}  http://{host}:{port}/mcp")
        mcp.run(
            transport=transport,
            host=host,
            port=port,
            stateless_http=True,  # ← fixes "Session not found" error
        )
