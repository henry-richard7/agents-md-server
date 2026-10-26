# Skilldeck: Developer Guide to Skills & Tools

This guide explains how to create, test, and use **Skills** (markdown instruction runbooks) and **Tools** (Python functions) in the Skilldeck Model Context Protocol (MCP) server.

---

## Architecture: Skills vs. Tools

In Skilldeck, **Skills** and **Tools** work in synergy:

```
┌────────────────────────────────────────────────────────┐
│                        AI Model                        │
└───────────────────────▲────────▲───────────────────────┘
                        │        │
         1. Instructions│        │2. Execution
                        │        │
┌───────────────────────┴──┐  ┌──┴───────────────────────┐
│     SKILL (Markdown)     │  │      TOOL (Python)       │
│  - Endpoint specifications│  │  - Network requests     │
│  - Filter & param syntax │  │  - SSRF guardrails       │
│  - Decision trees        │  │  - Credential resolution │
│  - Step-by-step procedures│  │  - Math & computation   │
└──────────────────────────┘  └──────────────────────────┘
```

- **Skills (`skills/<skill_name>/SKILL.md`)**: Teach the agent *what to do*, which API endpoints to use, how to query them, and what parameters to pass.
- **Tools (`tools/<tool_name>.py`)**: Provide the executable Python capabilities (e.g., `http_fetch`, `auth_http_fetch`, `cost_estimator`).

---

## 1. Creating New Skills

Skills are modular Markdown files stored in individual subdirectories under `skills/`.

### Directory Layout
```text
skills/
└── <skill_name>/
    └── SKILL.md
```

### SKILL.md Anatomy

Every `SKILL.md` must start with YAML frontmatter enclosed in `---` dashes:

```markdown
---
name: github-repo-info
description: Fetches repository details, stars, and open issues from GitHub's public API. Use when the user asks about a GitHub repository's statistics or status.
compatibility: Requires public internet access to api.github.com.
metadata:
  author: your-name
  version: "1.0"
---

# GitHub Repo Info Skill

Use this skill to fetch repository metadata from the public GitHub REST API.

## Step 1 — Parse Repository Input
Extract the repository owner and name from the user's prompt (e.g., `owner/repo`).

## Step 2 — Call http_fetch
Call `http_fetch` with the following parameters:

```json
{
  "method": "GET",
  "url": "https://api.github.com/repos/{owner}/{repo}",
  "headers": {
    "Accept": "application/vnd.github.v3+json"
  }
}
```

## Step 3 — Format Results
Present the following to the user:
- Full repository name (`full_name`)
- Star count (`stargazers_count`)
- Fork count (`forks_count`)
- Open issues (`open_issues_count`)
- Primary language (`language`)
```

### Key Skill Guidelines
1. **Clear `description`**: The `description` in the YAML frontmatter is indexed and displayed to models in tool descriptions and MCP resources. Make it specific about *when* the skill should trigger.
2. **Explicit Tool Call Schemas**: Give concrete JSON examples of how `http_fetch` or `auth_http_fetch` should be invoked.
3. **Parameter Encodings**: Instruct the model on parameter handling (e.g., *"pass filters in `query_params`, do not embed them in the raw URL"*).

---

## 2. Using Authentication in Skills

To call authenticated APIs, instruct the agent to use `auth_http_fetch`. **Never put secrets in the skill markdown.**

```markdown
---
name: send-slack-message
description: Sends a notification message to a Slack channel using a webhook or bot token.
compatibility: Requires SLACK_BOT_TOKEN environment variable.
---

# Slack Notification Skill

## Step 1 — Call auth_http_fetch
Use `auth_type="bearer"` and pass `env_key="SLACK_BOT_TOKEN"`.

```json
{
  "url": "https://slack.com/api/chat.postMessage",
  "method": "POST",
  "auth_type": "bearer",
  "env_key": "SLACK_BOT_TOKEN",
  "body": {
    "channel": "#alerts",
    "text": "Your message here"
  }
}
```
```

The server resolves `SLACK_BOT_TOKEN` server-side from `.env` — the model never sees the token.

---

## 3. Creating Custom Tools

Custom tools are Python modules placed in the `tools/` directory. The server auto-discovers and registers them on startup.

### Tool Contract
Every custom tool file must define a `register(mcp)` function that accepts the `FastMCP` server instance.

### Example 1: Synchronous Computation Tool

Create `tools/text_utils.py`:

```python
"""Text manipulation utilities tool."""

from fastmcp import FastMCP
from pydantic import Field


def register(mcp: FastMCP) -> None:
    @mcp.tool
    def word_counter(
        text: str = Field(..., description="Text content to analyze"),
    ) -> dict[str, int]:
        """Count characters, words, and lines in a string."""
        lines = text.splitlines()
        words = text.split()
        return {
            "characters": len(text),
            "words": len(words),
            "lines": len(lines),
        }
```

### Example 2: Async Tool with Context & Validation

Create `tools/dns_lookup.py`:

```python
"""DNS resolution utility tool."""

import socket
from fastmcp import FastMCP, Context
from pydantic import BaseModel, Field


class DNSQuery(BaseModel):
    hostname: str = Field(..., min_length=3, description="Domain name to resolve (e.g., 'example.com')")


def register(mcp: FastMCP) -> None:
    @mcp.tool
    async def dns_lookup(
        hostname: str,
        ctx: Context | None = None,
    ) -> dict[str, list[str]]:
        """Resolve a hostname to its IPv4 and IPv6 addresses."""
        query = DNSQuery(hostname=hostname.strip().lower())

        if ctx:
            await ctx.info(f"Resolving DNS for {query.hostname}...")

        try:
            results = socket.getaddrinfo(query.hostname, None)
            ips = sorted({sockaddr[0] for _, _, _, _, sockaddr in results})
            return {"hostname": query.hostname, "addresses": ips}
        except socket.gaierror as e:
            return {"error": f"DNS resolution failed: {e}", "addresses": []}
```

### Key Tool Guidelines
- **Type Annotations**: Always annotate parameters and return types (`str`, `float`, `dict[str, Any]`, `list[str]`).
- **Pydantic Validation**: Use Pydantic's `Field(...)` or models for bounds checking (`ge=0`, `min_length=1`).
- **Sync vs Async**:
  - Use `def` for pure in-memory calculations (faster, no event loop overhead).
  - Use `async def` for I/O operations (network, file access, context reporting).
- **Progress & Logging**: Inject `ctx: Context | None = None` and call `await ctx.info(...)` or `await ctx.report_progress(...)` to stream real-time updates to MCP clients.
- **SSRF Safety**: If making custom external network requests, use `HttpClientManager` from `agents_md_server.http_client` to benefit from SSRF protection and connection pooling.

---

## 4. Testing & Verification

### Step 1: Inspect Discoveries
Run the CLI `inspect` command to verify that your new skill or tool is recognized:

```bash
uv run agents-md-server inspect
```

You should see your skill and tool logged in the output:
```text
[INFO] Loaded skill: github-repo-info (version: 1.0)
[INFO] Registered external tool module: dns_lookup.py
```

### Step 2: Write a Unit Test
Create a test in `tests/test_custom_tool.py`:

```python
import pytest
from fastmcp import FastMCP
from tools.text_utils import register

def test_word_counter():
    mcp = FastMCP("test")
    register(mcp)
    
    tool = mcp.get_tool("word_counter")
    result = tool.fn(text="Hello world\nSecond line")
    
    assert result["words"] == 4
    assert result["lines"] == 2
```

Run tests with pytest:
```bash
uv run pytest
```

---

## 5. Live Testing in Clients

Once verified, your new capabilities are available immediately in all connected MCP clients:

| Client | How to Test |
| :--- | :--- |
| **Antigravity** | Simply ask: *"Can you look up the DNS records for github.com?"* (Antigravity invokes your tool automatically). |
| **LM Studio** | Look at the tool sidebar to see your new tool with a green badge. |
| **Claude Desktop / Cursor** | Restart the client to reload the server schema, then prompt the agent. |
