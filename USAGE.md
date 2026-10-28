# Skilldeck: Developer Guide

This guide covers how to write, configure, and test **Skills** (Markdown API runbooks) and **Tools** (Python functions) in Skilldeck.

---

## 1. Core Concepts

Skilldeck splits agent capabilities into two layers:

1. **Instructions (`skills/<name>/SKILL.md`)**: Tell the agent which API endpoints exist, which parameters to send, how to construct filters, and how to format responses.
2. **Execution (`http_fetch`, `auth_http_fetch`, custom tools)**: Handle outbound networking, SSL/TLS, timeouts, SSRF validation, and credential resolution.

Because the execution tools are generic, adding support for a new REST API does not require writing Python code or redeploying the server. You write a Markdown file that explains the API, and the model executes calls through the built-in HTTP tools.

---

## 2. Writing a Skill

### Directory Structure

Every skill lives in its own subdirectory under `skills/`:

```text
skills/
└── weather/
    └── SKILL.md
```

### Frontmatter Schema

Every `SKILL.md` must start with YAML frontmatter:

```markdown
---
name: weather
description: Look up current conditions and forecasts for coordinates or cities via Open-Meteo. Use when the user asks about weather, temperatures, precipitation, or forecasts.
compatibility: Requires outbound internet access to api.open-meteo.com. No authentication needed.
metadata:
  version: "1.0"
  author: your-name
---
```

- **`name`** *(required)*: Unique identifier matching the directory name (lowercase alphanumeric and hyphens).
- **`description`** *(required)*: The indexing summary. This text is injected into the system prompt catalog, the `skills://index` resource, and the `get_skills` tool description. Make it clear and describe **when** the model should use the skill.
- **`compatibility`** *(optional)*: Documents network or credential requirements.
- **`metadata`** *(optional)*: Key-value metadata (author, version, required env vars).

### Markdown Body Guidelines

Follow these rules when writing the markdown instructions:

1. **Explicit parameter structure**: Show concrete JSON snippets for `http_fetch` or `auth_http_fetch`.
2. **Use `query_params` for URL parameters**: Instruct the model to pass query parameters in `query_params`, not inside the URL string. This ensures values with spaces or special characters are encoded correctly.
3. **No hardcoded secrets**: Never include API keys or tokens in `SKILL.md`. Document the required environment variable names instead.
4. **Document pagination**: If an API returns paginated lists, explain which response fields indicate additional pages (e.g. `nextRecordsUrl`, `page_token`, `$skipToken`).
5. **Output guidance**: State what fields to extract and present to the user.

### Complete Example: Public API (`skills/azure-pricing/SKILL.md`)

```markdown
---
name: azure-pricing
description: Fetches real-time Azure retail pricing using the Azure Retail Prices API. Use when the user asks about Azure service costs, compares SKU prices, or needs pricing data.
compatibility: Requires public internet access to prices.azure.com. No auth needed.
metadata:
  version: "1.0"
---

# Azure Pricing Skill

Use this skill to fetch Azure retail pricing. No credentials required.

## How to Call http_fetch

Always pass filters in `query_params`, never in the URL string:

```json
{
  "method": "GET",
  "url": "https://prices.azure.com/api/retail/prices",
  "query_params": {
    "api-version": "2023-01-01-preview",
    "$filter": "armRegionName eq 'eastus' and serviceName eq 'Virtual Machines' and contains(skuName, 'D2s v5')"
  }
}
```

## Response Formatting

Extract and display:
- Service Name (`serviceName`)
- Product & SKU Name (`productName`, `skuName`)
- Region (`armRegionName`)
- Hourly and Monthly Retail Price (`retailPrice`, `unitOfMeasure`)
```

---

## 3. Authentication Patterns (`auth_http_fetch`)

When an API requires authentication, instruct the model to call `auth_http_fetch`.

> **Security Rule**: The model must only provide the **name** of the environment variable containing the secret (e.g. `env_key="DATABRICKS_TOKEN"`). The server resolves the secret locally. If the model accidentally sends a raw token string, the server rejects the request.

### Pattern A: Bearer Token

For APIs that accept an `Authorization: Bearer <token>` header:

```json
{
  "url": "https://your-workspace.cloud.databricks.com/api/2.1/clusters/list",
  "method": "GET",
  "auth_type": "bearer",
  "env_key": "DATABRICKS_TOKEN"
}
```

In `.env`:
```env
DATABRICKS_TOKEN=dapi1234567890abcdef
```

### Pattern B: OAuth 2.0 Client Credentials

For APIs using OAuth 2.0 Client Credentials flow (such as Salesforce Connected Apps):

```json
{
  "url": "https://your-instance.my.salesforce.com/services/data/v60.0/query",
  "method": "GET",
  "auth_type": "client_credentials",
  "token_url": "https://your-instance.my.salesforce.com/services/oauth2/token",
  "env_client_id": "SALESFORCE_CLIENT_ID",
  "env_client_secret": "SALESFORCE_CLIENT_SECRET",
  "query_params": {
    "q": "SELECT Id, Name, StageName FROM Opportunity WHERE IsClosed = false"
  }
}
```

In `.env`:
```env
SALESFORCE_CLIENT_ID=3MVG9...
SALESFORCE_CLIENT_SECRET=98765...
```

**How token caching works**:
- `auth_http_fetch` sends a `POST` request to `token_url` with `grant_type=client_credentials`.
- The acquired access token is cached in memory until its `expires_in` period expires (minus a configurable safety buffer, default 60s).
- Concurrent token requests are serialized with an internal asyncio lock to avoid duplicate token grants.
- If the target API returns an HTTP 401 Unauthorized, the cache entry is automatically evicted so the next call fetches a fresh token.

### Pattern C: Custom Header and Prefix

For APIs using custom header names or prefix formats (e.g., `X-API-Key: <key>` or `Authorization: Token <key>`):

```json
{
  "url": "https://api.example.com/v1/data",
  "method": "GET",
  "auth_type": "api_key_header",
  "header_name": "X-API-Key",
  "env_key": "EXAMPLE_API_KEY"
}
```

For tokens with custom prefixes:
```json
{
  "url": "https://api.example.com/v1/data",
  "method": "GET",
  "auth_type": "api_key_header",
  "header_name": "Authorization",
  "header_prefix": "Token ",
  "env_key": "EXAMPLE_TOKEN"
}
```

### Pattern D: Query Parameter API Key

For APIs that take the key in the query string:

```json
{
  "url": "https://api.example.com/v1/lookup",
  "method": "GET",
  "auth_type": "api_key_query",
  "query_param_name": "apikey",
  "env_key": "EXAMPLE_API_KEY"
}
```

### Pattern E: Environment Variable Interpolation

You can reference environment variables anywhere in `headers` or `query_params` using the `__ENV__<VAR_NAME>__` placeholder:

```json
{
  "url": "https://api.example.com/v1/tenant-data",
  "method": "GET",
  "headers": {
    "X-Tenant-ID": "__ENV__MY_TENANT_ID__"
  }
}
```

---

## 4. Handling Pagination and Payload Limits

### The 1MB Limit (`MAX_RESPONSE_BYTES`)

To protect LLM context windows and prevent client-side parser lockups, `http_fetch` enforces a default payload limit of **1,000,000 bytes (~1MB)**.

If an endpoint returns a payload larger than this limit, the request does not crash. Instead, the server returns an HTTP 413 error object:

```json
{
  "status_code": 413,
  "error": "Payload Too Large: response size (1,450,210 bytes) exceeds the 1,000,000 byte safety limit.",
  "hint": "Refine your query using API query parameters (e.g. limit, per_page, date ranges, or field selection) to fetch a smaller page."
}
```

### Writing Multi-Page Instructions

When authoring a skill for an API that returns large datasets, teach the model how to follow pagination.

**Example from `skills/salesforce/SKILL.md`**:
```markdown
## Pagination Loop

When executing SOQL queries:
1. Call `auth_http_fetch` with your `SELECT` query.
2. Check the response field `done`.
3. If `done` is `false`, the response contains a `nextRecordsUrl` field (e.g., `/services/data/v60.0/query/01g...-2000`).
4. To fetch the next page, call `auth_http_fetch` with:
   - `url`: `"${SALESFORCE_INSTANCE_URL}" + nextRecordsUrl`
   - Do NOT pass the `q` parameter on pagination requests.
5. Repeat until `done` is `true`.
```

---

## 5. Token Optimization (`PRELOAD_ALL_SKILLS`)

In MCP, instructions passed to the server constructor become part of the agent's system prompt. If you have 10 skills that each contain 1,000 tokens of documentation, inlining all of them wastes 10,000 tokens on every single user turn.

Skilldeck handles this with the `PRELOAD_ALL_SKILLS` setting:

| Mode | `PRELOAD_ALL_SKILLS` | Behavior |
| :--- | :--- | :--- |
| **Catalog Mode** *(default)* | `false` | Inlines only skill names and descriptions (~350 tokens total). When the model needs a skill, it calls `get_skills(skill_name="...")` or reads `skill://<name>` to fetch full instructions. Recommended for local models (LM Studio, Ollama, 7B/8B models). |
| **Preload Mode** | `true` | Inlines the full markdown body of every skill directly into the system prompt. Useful if you use frontier models with 1M+ context windows and want zero-latency instruction access. |

You can switch modes in `.env`:
```env
PRELOAD_ALL_SKILLS=false
```

---

## 6. Hot Reloading Skills

You do not need to restart the server after adding, editing, or deleting a `SKILL.md`.

Call the `reload_skills` tool from your client:
- The server re-scans the `skills/` directory on disk.
- Re-parses all YAML frontmatter and markdown content.
- Rebuilds the internal `SkillsState` and updates the system prompt.
- Returns a list of all currently active skill names.

You can also read any skill directly via its MCP resource URI:
```text
skill://azure-pricing
skill://salesforce
```

Or inspect all loaded skills via the index resource:
```text
skills://index
```

---

## 7. Writing Custom Python Tools

If an integration requires local computation, disk operations, or custom libraries that cannot be handled via HTTP, add a Python tool to `tools/`.

### Tool Contract

1. Place a `.py` file inside `tools/` (or your configured `TOOLS_DIR`).
2. Define a `register(mcp: FastMCP) -> None` function.
3. Decorate tool functions with `@mcp.tool`.

### Example: Sync Computation Tool

```python
# tools/math_utils.py
"""Math utilities tool."""

from fastmcp import FastMCP
from pydantic import Field


def register(mcp: FastMCP) -> None:
    @mcp.tool
    def calculate_compound_interest(
        principal: float = Field(..., gt=0, description="Initial investment amount"),
        annual_rate: float = Field(
            ..., gt=0, le=1.0, description="Annual interest rate as decimal (e.g. 0.05)"
        ),
        years: int = Field(..., gt=0, description="Investment duration in years"),
        compounds_per_year: int = Field(
            default=12, gt=0, description="Compounding periods per year"
        ),
    ) -> dict[str, float]:
        """Calculate compound interest and final balance."""
        total = principal * ((1 + annual_rate / compounds_per_year) ** (compounds_per_year * years))
        return {
            "principal": round(principal, 2),
            "total_interest": round(total - principal, 2),
            "final_balance": round(total, 2),
        }
```

### Example: Async Tool with Context Logging

```python
# tools/port_checker.py
"""Network connectivity diagnostic tool."""

import asyncio
from fastmcp import FastMCP, Context
from pydantic import Field


def register(mcp: FastMCP) -> None:
    @mcp.tool
    async def check_tcp_port(
        host: str = Field(..., description="Target hostname or IP address"),
        port: int = Field(..., ge=1, le=65535, description="Port number to test"),
        timeout_seconds: float = Field(default=3.0, gt=0, le=10.0),
        ctx: Context | None = None,
    ) -> dict[str, object]:
        """Test whether a TCP port is open on a target host."""
        if ctx:
            await ctx.info(f"Probing {host}:{port} with {timeout_seconds}s timeout...")

        try:
            _, writer = await asyncio.wait_for(
                asyncio.open_connection(host, port),
                timeout=timeout_seconds,
            )
            writer.close()
            await writer.wait_closed()
            return {"host": host, "port": port, "open": True}
        except (OSError, asyncio.TimeoutError) as err:
            return {"host": host, "port": port, "open": False, "reason": str(err)}
```

---

## 8. Testing and Troubleshooting

### Step 1: Inspect Discoveries via CLI

Verify that your new skill or tool is picked up:

```bash
uv run agents-md-server inspect
```

Output:
```text
=== Skilldeck Server Inspection ===
Version:      0.1.0
Skills Dir:   /path/to/agents-md-server/skills
Tools Dir:    /path/to/agents-md-server/tools
AGENTS.md:    /path/to/agents-md-server/AGENTS.md

Server initialized successfully.
```

### Step 2: Run Unit Tests

Skilldeck includes a test suite covering configuration, HTTP clients, SSRF protection, OAuth caching, and skills loading:

```bash
# Run full suite
uv run pytest

# Run specific test file
uv run pytest tests/test_skills.py
```

### Common Issues & Fixes

| Issue | Cause | Fix |
| :--- | :--- | :--- |
| **HTTP 403: Access to private network is blocked** | URL resolves to `127.0.0.1`, `10.x.x.x`, `192.168.x.x`, or `169.254.169.254`. | SSRF guardrail. If querying internal test services intentionally, set `ALLOW_PRIVATE_NETWORKS=true` in `.env`. |
| **ValueError: Parameter 'env_key' expects the NAME of an environment variable** | The model or user passed a raw token string (e.g. `sk-...` or `dapi...`) instead of the variable name. | Instruct the model to pass the variable name itself (e.g. `"DATABRICKS_TOKEN"`), not the value. |
| **OAuth2 400: `unsupported_grant_type`** | 1. Missing "Run-As" user in Connected App policy (Salesforce).<br>2. Hitting generic login URL instead of custom domain.<br>3. Sending JSON instead of form-urlencoded. | 1. In Salesforce Setup, go to Connected Apps $\rightarrow$ Edit Policies $\rightarrow$ Client Credentials Flow and assign a Run-As user.<br>2. Use `${SALESFORCE_INSTANCE_URL}/services/oauth2/token`. |
| **Model returns only 10 records and stops** | The prompt or skill example hardcoded `LIMIT 10`. | Remove `LIMIT 10` from skill query examples and document multi-page iteration via `nextRecordsUrl`. |
| **Local model in LM Studio doesn't use skills** | Context window overflow or model unable to read MCP resources. | Set `PRELOAD_ALL_SKILLS=false`. Skilldeck embeds skill names and descriptions in the `get_skills` tool description so the model calls it automatically. |
