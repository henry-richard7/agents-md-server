from pathlib import Path

from agents_md_server.skills.loader import build_system_prompt, load_skills, parse_skill_markdown


def test_parse_skill_markdown_with_frontmatter():
    content = """---
name: my-skill
description: Skill description
compatibility: Internet required
metadata:
  version: "1.0"
  author: tester
---

# My Skill Instructions
Step 1: Do this.
"""
    skill = parse_skill_markdown(content, default_name="fallback-name")
    assert skill.name == "my-skill"
    assert skill.description == "Skill description"
    assert skill.compatibility == "Internet required"
    assert skill.metadata.get("version") == "1.0"
    assert "Step 1: Do this." in skill.instructions


def test_parse_skill_markdown_without_frontmatter():
    content = "# Simple Skill\nJust markdown body."
    skill = parse_skill_markdown(content, default_name="simple-skill")
    assert skill.name == "simple-skill"
    assert skill.description == ""
    assert skill.instructions == content


def test_load_skills(tmp_path: Path):
    skill_dir = tmp_path / "skill1"
    skill_dir.mkdir()
    skill_file = skill_dir / "SKILL.md"
    skill_file.write_text(
        "---\nname: skill-one\ndescription: test skill\n---\nBody",
        encoding="utf-8",
    )

    skills = load_skills(tmp_path)
    assert len(skills) == 1
    assert "skill-one" in skills
    assert skills["skill-one"].description == "test skill"


def test_build_system_prompt_on_demand(tmp_path: Path):
    agents_md = tmp_path / "AGENTS.md"
    agents_md.write_text("# Core Agent\nBase instructions.", encoding="utf-8")

    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    s_dir = skills_dir / "calc"
    s_dir.mkdir()
    (s_dir / "SKILL.md").write_text(
        "---\nname: calc\ndescription: calculator\n---\nCalculate things.",
        encoding="utf-8",
    )

    skills = load_skills(skills_dir)
    prompt = build_system_prompt(agents_md, skills, preload_all=False)

    assert "Core Agent" in prompt
    assert "Available Skills Catalog" in prompt
    assert "calc" in prompt
    assert "calculator" in prompt
    # Full body should NOT be in the on-demand prompt
    assert "Calculate things." not in prompt


def test_build_system_prompt_preload_all(tmp_path: Path):
    agents_md = tmp_path / "AGENTS.md"
    agents_md.write_text("# Core Agent\nBase instructions.", encoding="utf-8")

    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    s_dir = skills_dir / "calc"
    s_dir.mkdir()
    (s_dir / "SKILL.md").write_text(
        "---\nname: calc\ndescription: calculator\n---\nCalculate things.",
        encoding="utf-8",
    )

    skills = load_skills(skills_dir)
    prompt = build_system_prompt(agents_md, skills, preload_all=True)

    assert "Core Agent" in prompt
    assert "Loaded Skills" in prompt
    assert "Calculate things." in prompt
