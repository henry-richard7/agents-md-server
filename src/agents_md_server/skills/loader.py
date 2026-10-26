"""Skill discovery, parsing, and system prompt generation."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

from agents_md_server.skills.models import Skill

logger = logging.getLogger(__name__)


def parse_skill_markdown(content: str, default_name: str, path: Path | None = None) -> Skill:
    """Parse a SKILL.md file, extracting YAML frontmatter and markdown body."""
    raw = content.strip()
    instructions = raw
    metadata_dict: dict[str, Any] = {}

    if raw.startswith("---"):
        parts = raw.split("---", 2)
        if len(parts) >= 3:
            frontmatter_text = parts[1]
            instructions = parts[2].strip()
            try:
                parsed_yaml = yaml.safe_load(frontmatter_text)
                if isinstance(parsed_yaml, dict):
                    metadata_dict = parsed_yaml
            except (yaml.YAMLError, ValueError) as e:
                logger.warning("Failed to parse YAML frontmatter in %s: %s", path or default_name, e)

    name = str(metadata_dict.get("name") or default_name).strip()
    description = str(metadata_dict.get("description") or "").strip()
    compatibility = metadata_dict.get("compatibility")
    if compatibility is not None:
        compatibility = str(compatibility).strip()

    extra_metadata = metadata_dict.get("metadata")
    if not isinstance(extra_metadata, dict):
        extra_metadata = {
            k: v
            for k, v in metadata_dict.items()
            if k not in ("name", "description", "compatibility")
        }

    return Skill(
        name=name,
        description=description,
        compatibility=compatibility,
        metadata=extra_metadata,
        instructions=instructions,
        raw_content=content,
        path=path,
    )


def load_skills(skills_dir: Path) -> dict[str, Skill]:
    """Scan directory and load all valid skills."""
    skills: dict[str, Skill] = {}
    if not skills_dir.exists():
        logger.warning("Skills directory does not exist: %s", skills_dir)
        return skills

    for skill_path in sorted(skills_dir.iterdir()):
        if not skill_path.is_dir():
            continue
        skill_md = skill_path / "SKILL.md"
        if not skill_md.is_file():
            continue

        try:
            content = skill_md.read_text(encoding="utf-8")
            skill = parse_skill_markdown(content, default_name=skill_path.name, path=skill_md)
            skills[skill.name] = skill
            logger.info("Loaded skill: %s (version: %s)", skill.name, skill.metadata.get("version", "N/A"))
        except (OSError, UnicodeDecodeError, ValueError) as e:
            logger.error("Error reading skill from %s: %s", skill_md, e)

    return skills


def build_system_prompt(agents_md_path: Path, skills: dict[str, Skill]) -> str:
    """Combine AGENTS.md base prompt with loaded skills into full system prompt."""
    base = ""
    if agents_md_path.exists():
        try:
            base = agents_md_path.read_text(encoding="utf-8").strip()
        except OSError as e:
            logger.error("Error reading base AGENTS.md from %s: %s", agents_md_path, e)

    if not skills:
        return base

    skill_blocks = "\n\n---\n\n".join(
        f"## Skill: {skill.name}\n\n{skill.raw_content}" for skill in skills.values()
    )
    full = f"{base}\n\n# Loaded Skills\n\n{skill_blocks}".strip()
    logger.debug("System prompt built: %d characters, %d words", len(full), len(full.split()))
    return full
