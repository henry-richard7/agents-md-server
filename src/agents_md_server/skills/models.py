"""Skill data models and representations."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class SkillMetadata(BaseModel):
    """Metadata extracted from SKILL.md YAML frontmatter."""

    name: str = Field(..., description="Skill identifier name")
    description: str = Field(default="", description="Skill purpose and capability summary")
    compatibility: str | None = Field(default=None, description="System requirements or constraints")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Custom metadata fields")


class Skill(BaseModel):
    """Complete representation of a loaded skill."""

    name: str
    description: str
    compatibility: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    instructions: str = Field(..., description="Markdown instructions body")
    raw_content: str = Field(..., description="Full original content including frontmatter")
    path: Path | None = None

    def to_summary_dict(self) -> dict[str, Any]:
        """Compact dictionary suitable for MCP resources and listings."""
        return {
            "name": self.name,
            "description": self.description,
            "compatibility": self.compatibility,
            "metadata": self.metadata,
        }
