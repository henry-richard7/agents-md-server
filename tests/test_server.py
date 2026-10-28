import json
from pathlib import Path

import pytest

from agents_md_server.server import SkillsState, create_server


def test_skills_state_hot_reload(tmp_path: Path):
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    agents_md = tmp_path / "AGENTS.md"
    agents_md.write_text("# Base Agent\nDo things.", encoding="utf-8")

    # Initial skill
    s1 = skills_dir / "skill1"
    s1.mkdir()
    (s1 / "SKILL.md").write_text(
        "---\nname: skill1\ndescription: First skill\n---\nRun skill 1",
        encoding="utf-8",
    )

    state = SkillsState(skills_dir, agents_md)
    assert "skill1" in state.skills
    assert "First skill" in state.system_prompt
    assert "skill2" not in state.skills

    # Add second skill dynamically on disk
    s2 = skills_dir / "skill2"
    s2.mkdir()
    (s2 / "SKILL.md").write_text(
        "---\nname: skill2\ndescription: Second skill\n---\nRun skill 2",
        encoding="utf-8",
    )

    # Hot reload!
    state.reload()
    assert "skill2" in state.skills
    assert "Second skill" in state.system_prompt


@pytest.mark.asyncio
async def test_server_initialization():
    mcp = create_server()
    assert mcp.name == "skilldeck"

    # Verify tool registrations
    tools = await mcp.list_tools()
    tool_names = [tool.name for tool in tools]
    assert "http_fetch" in tool_names
    assert "auth_http_fetch" in tool_names
    assert "cost_estimator" in tool_names
    assert "get_skills" in tool_names
    assert "reload_skills" in tool_names


@pytest.mark.asyncio
async def test_server_resources():
    mcp = create_server()
    resources = await mcp.list_resources()
    uris = [str(r.uri) for r in resources]

    assert "agent://instructions" in uris
    assert "skills://index" in uris
    assert "skill://azure-pricing" in uris

    # Verify reading skills index resource
    index_res = await mcp.read_resource("skills://index")
    content = index_res.contents[0].content
    parsed = json.loads(content)
    assert any(s["name"] == "azure-pricing" for s in parsed)


@pytest.mark.asyncio
async def test_get_skills_tool():
    mcp = create_server()
    tool = await mcp.get_tool("get_skills")

    # Get all skills
    all_skills = tool.fn()
    assert "azure-pricing" in all_skills
    assert "get-ip-address" in all_skills

    # Get specific skill
    azure_skill = tool.fn(skill_name="azure-pricing")
    assert "Azure Pricing Skill" in azure_skill

    # Unknown skill
    missing = tool.fn(skill_name="unknown-skill-xyz")
    assert "not found" in missing
