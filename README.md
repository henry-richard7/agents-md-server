# Skilldeck (`agents-md-server`)

[![CI](https://github.com/henry-richard7/agents-md-server/actions/workflows/ci.yml/badge.svg)](https://github.com/henry-richard7/agents-md-server/actions)
[![Python 3.13+](https://img.shields.io/badge/python-3.13+-blue.svg)](https://www.python.org/)
[![FastMCP](https://img.shields.io/badge/FastMCP-3.3+-orange.svg)](https://github.com/jlowin/fastmcp)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

An MCP (Model Context Protocol) server that turns Markdown runbooks into callable agent skills.

Instead of writing and maintaining dedicated Python tool functions for every third-party API, you document API endpoints, parameter rules, and workflows in standard Markdown files (`skills/<name>/SKILL.md`). Skilldeck loads these files, provides the LLM with generic, safe HTTP execution tools (`http_fetch` and `auth_http_fetch`), and serves the instructions over MCP.

---

## How It Works

1. **Skills as Markdown**: Drop a `SKILL.md` inside `skills/<name>/`. Frontmatter metadata defines the skill name and description; the markdown body details endpoints, query parameters, auth requirements, and output parsing rules.
2. **Generic Execution Tools**: The model executes actions via built-in tools:
   - `http_fetch`: Makes arbitrary GET, POST, PUT, PATCH, and DELETE calls.
   - `auth_http_fetch`: Handles Bearer tokens, custom headers, and OAuth 2.0 client credentials flows with in-memory caching. Resolves secrets server-side from environment variables so the LLM never sees raw credentials.
   - `cost_estimator`: Utility tool for pricing calculations.
   - `get_skills`: Allows the model to inspect full skill documentation on demand.
   - `reload_skills`: Reloads all skills from disk at runtime without restarting the server process.
3. **SSRF Guardrails**: Outbound HTTP requests validate DNS and target IP addresses before connecting. Requests to loopback (`127.0.0.1`), private RFC1918 subnets (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`), and cloud metadata services (`169.254.169.254`) are blocked by default.
4. **Token-Efficient Loading**: With `PRELOAD_ALL_SKILLS=false` (default), Skilldeck injects only a lightweight skill catalog (~350 tokens) into system instructions. Full skill instructions are loaded on demand via `get_skills` or MCP resources (`skill://<name>`), keeping context small for local models (e.g., LM Studio, Ollama). Set `PRELOAD_ALL_SKILLS=true` if you prefer inlining everything upfront for larger models.

---

## Included Skills

The repository ships with ready-to-use skills under `skills/`:

| Skill | Description | Auth Type |
| :--- | :--- | :--- |
| `azure-pricing` | Query real-time Azure retail prices by service name, SKU, and region. | None (Public API) |
| `databricks` | Manage and inspect Databricks clusters, jobs, and job runs. | Bearer token (`DATABRICKS_TOKEN`) |
| `salesforce` | Read-only SOQL queries, schema inspection, and record retrieval with multi-page pagination. | OAuth2 client credentials or Bearer token |
| `get-ip-address` | Look up public IP details via `api.ipify.org`. | None (Public API) |

---

## Requirements

- Python 3.13+
- [uv](https://github.com/astral-sh/uv) (recommended package manager)

---

## Quick Start

### 1. Clone and Install

```bash
git clone https://github.com/henry-richard7/agents-md-server.git
cd agents-md-server

# Install runtime dependencies
uv sync

# Or install including development tools (pytest, ruff)
uv sync --extra dev
```

### 2. Configure Environment

Copy `.env.example` to `.env`:

```bash
cp .env.example .env
```

Set any credentials required by the skills you plan to use:

```env
# Server networking
TRANSPORT=stdio
PORT=8000
HOST=0.0.0.0
LOG_LEVEL=INFO

# Skill loading: false loads skill bodies on demand; true inlines all skills
PRELOAD_ALL_SKILLS=false

# Skill credentials (resolved server-side by auth_http_fetch)
DATABRICKS_HOST=https://your-workspace.cloud.databricks.com
DATABRICKS_TOKEN=dapi...

SALESFORCE_INSTANCE_URL=https://your-domain.my.salesforce.com
SALESFORCE_CLIENT_ID=3MVG9...
SALESFORCE_CLIENT_SECRET=...
```

### 3. Verify Discovery

Run `inspect` to check that skills, paths, and tools load without errors:

```bash
uv run agents-md-server inspect
```

### 4. Start the Server

**Stdio transport** (for Claude Desktop, Antigravity, LM Studio):
```bash
uv run agents-md-server run --transport stdio
```

**HTTP transport** (for Cursor, Windsurf, web clients):
```bash
uv run agents-md-server run --transport http --port 8000
# MCP endpoint: http://localhost:8000/mcp
```

*(You can also use the shorthand command `uv run skilldeck`)*.

---

## Configuration Reference

All settings can be specified in `.env` or as environment variables:

| Variable | Default | Description |
| :--- | :--- | :--- |
| `TRANSPORT` | `http` | Transport mode: `stdio`, `http`, `sse`, or `streamable-http`. |
| `HOST` | `0.0.0.0` | Host interface to bind when using HTTP/SSE. |
| `PORT` | `8000` | Port for HTTP/SSE server. |
| `LOG_LEVEL` | `INFO` | Logging level (`DEBUG`, `INFO`, `WARNING`, `ERROR`). Stdio routes logs to stderr. |
| `PRELOAD_ALL_SKILLS` | `false` | If `true`, inlines full markdown of all skills into the system prompt. If `false`, inlines a compact summary and loads bodies on demand. |
| `ALLOW_PRIVATE_NETWORKS` | `false` | If `true`, disables SSRF blocks on private/loopback IP addresses. |
| `HTTP_TIMEOUT_SECONDS` | `30.0` | Request timeout for outbound calls in `http_fetch` and `auth_http_fetch`. |
| `MAX_RESPONSE_BYTES` | `1000000` | Max response payload size (~1MB). Responses exceeding this return HTTP 413 with pagination guidance. |
| `MAX_REDIRECTS` | `5` | Maximum redirects followed per request with SSRF validation at each hop. |
| `SKILLS_DIR` | `skills/` | Path to custom skills directory. |
| `TOOLS_DIR` | `tools/` | Path to custom Python tools directory. |
| `AGENTS_MD_PATH` | `AGENTS.md` | Path to base agent system prompt template. |

---

## Client Setup

### Claude Desktop

Edit your `claude_desktop_config.json`:
- **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`

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

### Cursor / Windsurf / VS Code

Start Skilldeck in HTTP mode:

```bash
uv run agents-md-server run --transport http --port 8000
```

Add an MCP server in editor settings:
- **Type**: `HTTP` or `SSE`
- **URL**: `http://localhost:8000/mcp`

### LM Studio

Configure MCP server in LM Studio settings:

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

*Note: With `PRELOAD_ALL_SKILLS=false`, Skilldeck includes skill summaries in the `get_skills` tool description so models without resource prompt injection can discover and load instructions automatically.*

---

## Adding a New Skill

1. Create a directory under `skills/`:
   ```bash
   mkdir -p skills/weather
   ```

2. Add a `SKILL.md` file:
   ```markdown
   ---
   name: weather
   description: Look up current weather conditions and forecasts using Open-Meteo. Use whenever the user asks about temperature, rain, or forecasts for a location.
   compatibility: Requires internet access to api.open-meteo.com. No API key needed.
   ---

   # Weather Skill

   ## Step 1 — Call http_fetch
   Call `http_fetch` with latitude and longitude query parameters:

   ```json
   {
     "method": "GET",
     "url": "https://api.open-meteo.com/v1/forecast",
     "query_params": {
       "latitude": 40.7128,
       "longitude": -74.0060,
       "current": "temperature_2m,relative_humidity_2m,weather_code"
     }
   }
   ```

   ## Step 2 — Format the Response
   Summarize the current temperature and conditions for the user.
   ```

3. Call `reload_skills` in your MCP client or restart the server. The new skill is immediately available as:
   - Tool target: `get_skills(skill_name="weather")`
   - Resource: `skill://weather`
   - Prompt template: `skill-instructions` with argument `skill_name="weather"`

---

## Custom Python Tools

If a capability cannot be handled via HTTP calls, place a Python file in `tools/` with a `register(mcp)` function:

```python
# tools/string_tools.py
from fastmcp import FastMCP

def register(mcp: FastMCP) -> None:
    @mcp.tool
    def count_occurrences(text: str, substring: str) -> int:
        """Count how many times substring appears in text."""
        return text.count(substring)
```

The server automatically discovers and registers any `.py` file inside `tools/` on startup.

For complete patterns on OAuth 2.0 configuration, pagination handling, and writing tests, see [USAGE.md](USAGE.md).

---

## Docker

Build the container image:

```bash
docker build -t skilldeck:latest .
```

Run in HTTP mode:

```bash
docker run -d \
  --name skilldeck \
  -p 8000:8000 \
  --env-file .env \
  skilldeck:latest
```

The Dockerfile uses a multi-stage build, runs as a non-root user (`appuser`), and includes a healthcheck against `http://localhost:8000/mcp`.

---

## Testing & Quality Checks

Run test suite:
```bash
uv run pytest
```

Run linter and formatter checks:
```bash
uv run ruff check
uv run ruff format --check
```

---

## License

MIT License. See [LICENSE](LICENSE) for details.
