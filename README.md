# Skilldeck (agents-md-server)

[![CI](https://github.com/henry-richard7/agents-md-server/actions/workflows/ci.yml/badge.svg)](https://github.com/henry-richard7/agents-md-server/actions)
[![Python 3.13+](https://img.shields.io/badge/python-3.13+-blue.svg)](https://www.python.org/)
[![MCP Compliant](https://img.shields.io/badge/MCP-1.2+-green.svg)](https://modelcontextprotocol.io/)
[![Built with FastMCP](https://img.shields.io/badge/Built%20with-FastMCP%203.3+-orange.svg)](https://github.com/jlowin/fastmcp)

**Skilldeck** is a production-grade [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) server built with Python 3.13 and FastMCP. It dynamically loads Markdown-based agent capabilities (skills), exposes MCP resources, prompts, and tools, and adheres to strict production engineering and MCP industry standards.

---

## Key Features & MCP Industry Standards

- **Strict Stdio Protocol Compliance**: Standard output (`sys.stdout`) is strictly reserved for JSON-RPC messages in `stdio` mode. All diagnostic and operational logs route to `sys.stderr` to prevent client disconnection or JSON parsing errors.
- **SSRF (Server-Side Request Forgery) Protection**: External HTTP calls (`http_fetch`, `auth_http_fetch`) are guarded against loopback (`127.0.0.1`, `localhost`), link-local, private subnets (`10.0.0.0/8`, `192.168.0.0/16`, etc.), and cloud instance metadata services (`169.254.169.254`, `fd00:ec2::254`).
- **Connection Pooling & Lifecycle Management**: Managed `httpx.AsyncClient` pool with keepalive connections and automatic graceful cleanup via FastMCP lifespan context.
- **In-Memory OAuth2 Token Caching**: Authenticated requests using `client_credentials` automatically cache access tokens according to `expires_in` with safety buffers, preventing unnecessary roundtrips to authentication providers.
- **Full MCP Primitive Support**:
  - **Tools**: `http_fetch`, `auth_http_fetch`, `cost_estimator`, `get_skills` (with fallback support for LLMs lacking native resource injection).
  - **Resources**: `agent://instructions` (full system instructions), `skills://index` (JSON catalog of loaded skills), and dynamic `skill://{skill_name}` endpoints.
  - **Prompts**: `agent-instructions` and `skill-instructions` templates for instant agent alignment.
- **Production Packaging**: Modern `src/` layout, typed configuration via `pydantic-settings`, Hatchling build system, CLI scripts, multi-stage Dockerfile, and automated GitHub Actions CI.

---

## Project Structure

```text
agents-md-server/
├── AGENTS.md                         # Core agent identity, behavior, and boundaries
├── Dockerfile                        # Multi-stage production container
├── .dockerignore
├── .env.example                      # Documented environment template
├── .github/workflows/ci.yml          # Automated CI pipeline
├── pyproject.toml                    # Modern packaging metadata & tools
├── README.md
├── server.py                         # Backward-compatible entrypoint shim
├── main.py                           # CLI shortcut shim
├── skills/                           # Markdown skills directory
│   ├── azure-pricing/
│   │   └── SKILL.md
│   └── get-ip-address/
│       └── SKILL.md
├── tools/                            # Custom external tools directory
├── src/
│   └── agents_md_server/             # Core Python package
│       ├── __init__.py               # Package exports & version
│       ├── cli.py                    # Command-line interface
│       ├── config.py                 # Pydantic Settings & environment config
│       ├── http_client.py            # Pooled client with SSRF guardrails
│       ├── logging.py                # Stderr-safe logging system
│       ├── server.py                 # FastMCP server factory & primitives
│       ├── skills/
│       │   ├── loader.py             # Skill discovery & frontmatter parser
│       │   └── models.py             # Skill & metadata Pydantic models
│       └── tools/
│           ├── http_fetch.py         # Generic HTTP tool
│           ├── auth_http_fetch.py    # Authenticated HTTP with OAuth2 caching
│           └── cost_estimator.py     # Azure cost estimation tool
└── tests/                            # Comprehensive Pytest test suite
    ├── test_config.py
    ├── test_http_client.py
    ├── test_server.py
    ├── test_skills.py
    └── test_tools.py
```

---

## Quick Start

### 1. Installation

This project uses [`uv`](https://github.com/astral-sh/uv) for fast and reliable dependency resolution.

```bash
# Clone the repository
git clone https://github.com/henry-richard7/agents-md-server.git
cd agents-md-server

# Install dependencies and editable package
uv sync --all-extras
```

### 2. Environment Setup

Create your `.env` file from the provided template:

```bash
cp .env.example .env
```

Key environment options in `.env`:
```env
HOST=0.0.0.0
PORT=8000
TRANSPORT=http               # Options: stdio, http, sse
LOG_LEVEL=INFO
ALLOW_PRIVATE_NETWORKS=false # SSRF protection (keep false for production)
```

### 3. Running the Server

#### CLI (Recommended)
```bash
# Inspect loaded skills, tools, and resources
uv run agents-md-server inspect

# Run with HTTP transport (default: http://0.0.0.0:8000/mcp)
uv run agents-md-server run --transport http --port 8000

# Run with Stdio transport (for Claude Desktop, Cursor, etc.)
uv run agents-md-server run --transport stdio
```

#### Direct Python Execution
```bash
python server.py
```

---

## MCP Client Configurations

### Claude Desktop

Add this server to your `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "skilldeck": {
      "command": "uv",
      "args": [
        "--directory",
        "/absolute/path/to/agents-md-server",
        "run",
        "agents-md-server",
        "run",
        "--transport",
        "stdio"
      ]
    }
  }
}
```

### Antigravity (Global or Project)

Add to `~/.gemini/config/mcp_config.json` (or `.agents/mcp_config.json` in your workspace):

```json
{
  "mcpServers": {
    "skilldeck": {
      "command": "uv",
      "args": [
        "--directory",
        "G:/Codings/Python/agents-md-server",
        "run",
        "agents-md-server",
        "run",
        "--transport",
        "stdio"
      ]
    }
  }
}
```

### LM Studio

LM Studio supports MCP via its `mcp.json` configuration or the MCP settings panel:

```json
{
  "mcpServers": {
    "skilldeck": {
      "command": "uv",
      "args": [
        "--directory",
        "G:/Codings/Python/agents-md-server",
        "run",
        "agents-md-server",
        "run",
        "--transport",
        "stdio"
      ]
    }
  }
}
```

> **LM Studio Compatibility Note:** Local LLMs in LM Studio often ignore server-level `instructions` or MCP resources. Skilldeck embeds the available skills and instructions summary directly into the `get_skills` tool description, enabling local models to discover, invoke, and follow skills automatically.

### Cursor / VS Code / Windsurf

For tools connecting over HTTP or SSE:
1. Start the server:
   ```bash
   uv run agents-md-server run --transport http --port 8000
   ```
2. Configure the client endpoint:
   - **Type**: `HTTP` or `SSE`
   - **URL**: `http://localhost:8000/mcp`

---

## Docker Deployment

Build and run the production container:

```bash
# Build the image
docker build -t skilldeck:latest .

# Run container (non-root user, exposed port 8000)
docker run -d \
  --name skilldeck \
  -p 8000:8000 \
  --env-file .env \
  skilldeck:latest
```

The container includes a built-in `HEALTHCHECK` probing `http://localhost:8000/mcp`.

---

## Testing & Quality Assurance

Run the test suite and linter:

```bash
# Run 100% passing pytest suite
uv run pytest

# Run Ruff linter
uv run ruff check
```

---

## Extending Capabilities

> 📖 **Comprehensive Guide:** See [USAGE.md](file:///G:/Codings/Python/agents-md-server/USAGE.md) for detailed tutorials, code patterns, and testing instructions for skills and custom tools.

### Adding a Skill
1. Create a directory: `skills/<skill_name>/`
2. Add `SKILL.md` with YAML frontmatter:
   ```markdown
   ---
   name: my-api-skill
   description: Queries the external data service
   compatibility: Public internet access
   metadata:
     version: "1.0"
   ---

   # Instructions
   Use `http_fetch` to call: `https://api.example.com/v1/data`
   ```
3. The server auto-discovers and exposes it as a resource (`skill://my-api-skill`), prompt, and prompt context.

### Adding a Custom Tool
Place any custom `.py` file into the `tools/` directory with a `register(mcp)` function:

```python
# tools/calculator.py
from fastmcp import FastMCP

def register(mcp: FastMCP) -> None:
    @mcp.tool
    def add(a: float, b: float) -> float:
        """Add two numbers together."""
        return a + b
```
The server will automatically discover and register your tool on startup.

---

## License

MIT License. See [LICENSE](LICENSE) for details.
