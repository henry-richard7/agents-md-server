# Skilldeck (Agents MD Server)

Skilldeck is a Model Context Protocol (MCP) server that dynamically loads agent instructions, modular skills, and Python tools. It serves as an extensible foundation for building multi-skill expert AI assistants.

This project is built using [FastMCP](https://github.com/jlowin/fastmcp) and designed to easily integrate with compliant MCP clients like Claude Desktop, Cursor, VS Code, and others.

## Features

- **Dynamic Skill Loading**: Automatically loads markdown-based skills from the `skills/` directory.
- **Python Tool Auto-discovery**: Dynamically discovers and registers Python tools from the `tools/` directory.
- **Agent Instructions Resource**: Serves the agent's core identity (`AGENTS.md`) and loaded skills as an accessible MCP resource (`agent://instructions`).
- **Flexible Transport**: Supports both `stdio` and HTTP/SSE transports based on your environment.
- **Tool Fallback**: Exposes a `get_skills` tool to ensure all AI models can access the required instructions, even if they don't natively fully support MCP instruction injection.

## Project Structure

```text
agents-md-server/
├── AGENTS.md           # Core agent identity, behavior, and boundaries
├── README.md           # This file
├── main.py             # Basic entrypoint
├── pyproject.toml      # Project metadata and dependencies
├── server.py           # Core FastMCP server implementation
├── skills/             # Directory for modular markdown skills
│   └── <skill_name>/
│       └── SKILL.md    # Instructions and API references for a specific skill
├── tools/              # Directory for Python-based FastMCP tools
│   └── <tool_name>.py  # Python module implementing an MCP tool
└── uv.lock             # uv dependency lockfile
```

## Installation

This project uses `uv` for fast dependency management. 

1. **Clone the repository**:
   ```bash
   git clone <repository-url>
   cd agents-md-server
   ```

2. **Install dependencies**:
   ```bash
   uv sync
   # or using pip:
   pip install -e .
   ```

3. **Set up your environment**:
   Create a `.env` file in the root directory.
   ```env
   # Optional configurations
   HOST=0.0.0.0
   PORT=8000
   TRANSPORT=http # use 'stdio' for standard input/output transport
   ```

## Usage

You can run the server directly using Python:

```bash
python server.py
```

### Transports

- **HTTP/SSE Transport** (Default): Set `TRANSPORT=http` in your `.env`. The server will run and listen on the configured `HOST` and `PORT`.
- **Stdio Transport**: Set `TRANSPORT=stdio` in your `.env`. This is commonly used when launching the server as a subprocess from an MCP client like Claude Desktop.

## Adding Capabilities

### Adding a New Skill
1. Create a new directory under `skills/`, for example: `skills/my_new_skill/`.
2. Inside that directory, create a `SKILL.md` file.
3. Define the instructions, API endpoints, and expected behavior for that specific skill inside the markdown file.
4. The server will automatically load and append this skill to the agent's system prompt upon startup.

### Adding a New Tool
1. Create a new Python file in the `tools/` directory, for example: `tools/my_tool.py`.
2. Define your tool logic and include a `register(mcp)` function that adds the tool to the `FastMCP` instance.
   ```python
   # tools/my_tool.py
   def register(mcp):
       @mcp.tool()
       def my_custom_action(param: str) -> str:
           """Description of what this tool does."""
           return f"Processed: {param}"
   ```
3. The server will automatically discover and register your tool upon startup.

## Requirements
- Python 3.13+
- Dependencies: `fastmcp`, `openai`, `python-dotenv`
