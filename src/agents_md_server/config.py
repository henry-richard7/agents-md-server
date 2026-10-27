"""Configuration management using Pydantic Settings."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _find_project_root() -> Path:
    """Locate the project root directory containing pyproject.toml or skills/."""
    current = Path(__file__).resolve().parent
    for parent in [current, *current.parents]:
        if (parent / "pyproject.toml").exists() or (parent / "AGENTS.md").exists():
            return parent
    return Path.cwd()


PROJECT_ROOT = _find_project_root()

# Load .env file into os.environ so server-side secrets are available
load_dotenv(PROJECT_ROOT / ".env")



class Settings(BaseSettings):
    """Application and MCP server configuration."""

    # Server networking
    host: str = Field(default="0.0.0.0", description="Host interface to bind HTTP/SSE server to")
    port: int = Field(default=8000, description="Port for HTTP/SSE server")
    transport: Literal["stdio", "http", "sse", "streamable-http"] = Field(
        default="http", description="MCP transport mode"
    )
    stateless_http: bool = Field(
        default=True, description="Whether HTTP transport runs in stateless mode"
    )

    # Logging and diagnostics
    log_level: str = Field(default="INFO", description="Logging level")
    server_name: str = Field(default="skilldeck", description="MCP Server Name")

    # Security & HTTP Client Guardrails
    allow_private_networks: bool = Field(
        default=False,
        description="Allow HTTP tools to request private, loopback, or cloud metadata addresses (SSRF protection)",
    )
    http_timeout_seconds: float = Field(
        default=30.0, description="Default timeout for HTTP client requests"
    )
    oauth_token_buffer_seconds: int = Field(
        default=60, description="Safety buffer before token expiry to trigger refresh"
    )

    # File and Directory Paths
    skills_dir: Path | None = Field(
        default=None, description="Path to skills directory (defaults to PROJECT_ROOT/skills)"
    )
    tools_dir: Path | None = Field(
        default=None, description="Path to tools directory (defaults to PROJECT_ROOT/tools)"
    )
    agents_md_path: Path | None = Field(
        default=None, description="Path to AGENTS.md (defaults to PROJECT_ROOT/AGENTS.md)"
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="",
        extra="ignore",
    )

    @property
    def resolved_skills_dir(self) -> Path:
        if self.skills_dir:
            return self.skills_dir.resolve()
        return (PROJECT_ROOT / "skills").resolve()

    @property
    def resolved_tools_dir(self) -> Path:
        if self.tools_dir:
            return self.tools_dir.resolve()
        return (PROJECT_ROOT / "tools").resolve()

    @property
    def resolved_agents_md_path(self) -> Path:
        if self.agents_md_path:
            return self.agents_md_path.resolve()
        return (PROJECT_ROOT / "AGENTS.md").resolve()


settings = Settings()
