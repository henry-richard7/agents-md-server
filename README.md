# Skilldeck (`agents-md-server`)

[![CI](https://github.com/henry-richard7/agents-md-server/actions/workflows/ci.yml/badge.svg)](https://github.com/henry-richard7/agents-md-server/actions)
[![Python 3.13+](https://img.shields.io/badge/python-3.13+-blue.svg)](https://www.python.org/)
[![FastMCP](https://img.shields.io/badge/FastMCP-3.3+-orange.svg)](https://github.com/jlowin/fastmcp)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**Skilldeck** is an MCP (Model Context Protocol) server that turns Markdown files into actionable agent skills.

Instead of writing custom MCP tools or hardcoding API instructions into long system prompts, you define API procedures and runbooks in plain Markdown (`SKILL.md`). Skilldeck dynamically indexes these skills, bundles them with your base agent rules (`AGENTS.md`), and serves them to any MCP-compatible client alongside safe, built-in HTTP execution tools.

```text
skills/
└── azure-pricing/
    └── SKILL.md  ──▶  Skilldeck (MCP Server)  ──▶  Claude Desktop / Cursor / LM Studio
                        ├── System instructions & resources
                        └── HTTP tools (http_fetch, auth_http_fetch)
```

---

## What It Does

- **Markdown-first skills**: Drop a `SKILL.md` into `skills/<skill-name>/` with YAML frontmatter. Skilldeck exposes it as an MCP resource (`skill://<name>`), a prompt template, and incorporates it into the agent's instructions.
- **Built-in HTTP tools**:
  - `http_fetch`: Generic HTTP requests with method, query params, headers, and payload.
  - `auth_http_fetch`: Authenticated requests supporting Bearer tokens and OAuth2 `client_credentials` with in-memory token caching. Secrets are read server-side from environment variables—the LLM never sees raw credentials.
  - `cost_estimator`: Utility for calculating compute and cloud resource pricing.
- **SSRF protection**: Outbound requests are validated against loopback (`127.0.0.1`), private subnets (`10.0.0.0/8`, `192.168.0.0/16`), and cloud metadata endpoints (`169.254.169.254`).
- **Clean stdio logging**: In `stdio` mode, diagnostic logs are routed exclusively to `stderr` to avoid corrupting JSON-RPC streams on `stdout`.
- **Local model fallback**: Many local LLMs (e.g. in LM Studio) do not natively inspect MCP resources. Skilldeck embeds skill listings directly into the `get_skills` fallback tool description so local models discover available skills automatically.
- **Extensible via Python**: Add custom functions to `tools/` with a simple `register(mcp)` hook.

---

## Quick Start

### 1. Installation

Requires Python 3.13+ and [uv](https://github.com/astral-sh/uv):

```bash
git clone https://github.com/henry-richard7/agents-md-server.git
cd agents-md-server

# Install dependencies
uv sync

# Or install including development dependencies (pytest, ruff):
uv sync --extra dev
```

### 2. Configuration

Copy the sample environment file:

```bash
cp .env.example .env
```

Key settings in `.env`:

| Variable | Default | Description |
| :--- | :--- | :--- |
| `TRANSPORT` | `http` | Transport protocol: `stdio`, `http`, `sse` |
| `PORT` | `8000` | HTTP/SSE port |
| `HOST` | `0.0.0.0` | HTTP/SSE host bind address |
| `LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `ALLOW_PRIVATE_NETWORKS` | `false` | Set `true` to allow requests to internal/private IPs |
| `HTTP_TIMEOUT_SECONDS` | `30.0` | Timeout for external HTTP requests |

### 3. Run

```bash
# Check loaded skills and tools
uv run agents-md-server inspect

# Run with stdio (for Claude Desktop, Cursor, etc.)
uv run agents-md-server run --transport stdio

# Run with HTTP server (default endpoint: http://localhost:8000/mcp)
uv run agents-md-server run --transport http --port 8000
```

> **Tip:** You can also run the server directly via `uv run skilldeck` or `python server.py`.

---

## Client Setup

### Claude Desktop

Add Skilldeck to `claude_desktop_config.json`:

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

*(On Windows, use full paths with escaped backslashes or forward slashes, e.g. `C:/Users/you/Code/agents-md-server`)*.

### Cursor / VS Code / Windsurf

Start the HTTP server:

```bash
uv run agents-md-server run --transport http --port 8000
```

Configure your editor's MCP settings:
- **Type**: `HTTP` or `SSE`
- **URL**: `http://localhost:8000/mcp`

### LM Studio

Add to your MCP servers in LM Studio:

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

*Skilldeck's `get_skills` tool description exposes loaded skills directly, ensuring local models recognize and trigger them without needing resource prompt injection.*

### Antigravity / Gemini CLI

Add to `~/.gemini/config/mcp_config.json` (or `.agents/mcp_config.json` inside your workspace):

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

---

## Adding Skills & Tools

### Adding a Skill

Create a folder in `skills/` with a `SKILL.md` file:

```markdown
---
name: github-repo-info
description: Fetches star count and recent issues for a GitHub repository.
compatibility: Requires public internet access.
metadata:
  version: "1.0"
---

# GitHub Repo Info

When asked about a repository's stats, extract the owner and repo name, then call `http_fetch`:

```json
{
  "method": "GET",
  "url": "https://api.github.com/repos/{owner}/{repo}",
  "headers": {
    "Accept": "application/vnd.github.v3+json"
  }
}
```
```

Skilldeck automatically detects this file on startup, parses the frontmatter, and registers:
- Resource: `skill://github-repo-info`
- Prompt: `skill-instructions` (with argument `skill_name: github-repo-info`)
- Entry in `skills://index` and the `get_skills` fallback tool

### Adding a Custom Tool

Drop a Python file into `tools/` with a `register(mcp)` function:

```python
# tools/calculator.py
from fastmcp import FastMCP

def register(mcp: FastMCP) -> None:
    @mcp.tool
    def add(a: float, b: float) -> float:
        """Add two numbers together."""
        return a + b
```

Skilldeck will automatically load and register the tool when the server boots.

> 📖 **Full Guide:** Check out [USAGE.md](USAGE.md) for in-depth examples covering OAuth2 authentication in skills, async tools with progress reporting, and writing unit tests.

---

## Development

```bash
# Run test suite
uv run --extra dev pytest

# Run linter
uv run --extra dev ruff check
```

---

## Docker

Build and run with Docker:

```bash
docker build -t skilldeck:latest .

docker run -d \
  --name skilldeck \
  -p 8000:8000 \
  --env-file .env \
  skilldeck:latest
```

The container runs as a non-root user and includes an automated healthcheck at `http://localhost:8000/mcp`.

---

## License

MIT
