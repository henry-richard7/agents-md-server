from pathlib import Path

from agents_md_server.config import Settings


def test_default_settings():
    s = Settings()
    assert s.server_name == "skilldeck"
    assert s.host == "0.0.0.0"
    assert s.port == 8000
    assert s.transport == "http"
    assert s.allow_private_networks is False
    assert s.http_timeout_seconds == 30.0


def test_custom_paths(tmp_path: Path):
    custom_skills = tmp_path / "custom_skills"
    custom_skills.mkdir()
    s = Settings(skills_dir=custom_skills)
    assert s.resolved_skills_dir == custom_skills.resolve()
