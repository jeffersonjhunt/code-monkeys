"""Tests for parser module."""

import pytest

from skills_ref.parser import ParseError, ValidationError, find_skill_md, parse_frontmatter, read_properties


def test_valid_frontmatter():
    content = "---\nname: my-skill\ndescription: A test skill\n---\n# My Skill\n"
    metadata, body = parse_frontmatter(content)
    assert metadata["name"] == "my-skill"
    assert metadata["description"] == "A test skill"
    assert "# My Skill" in body


def test_missing_frontmatter():
    with pytest.raises(ParseError, match="must start with YAML frontmatter"):
        parse_frontmatter("# No frontmatter here")


def test_unclosed_frontmatter():
    with pytest.raises(ParseError, match="not properly closed"):
        parse_frontmatter("---\nname: my-skill\ndescription: A test skill\n")


def test_invalid_yaml():
    with pytest.raises(ParseError, match="Invalid YAML"):
        parse_frontmatter("---\nname: [invalid\ndescription: broken\n---\nBody\n")


def test_non_dict_frontmatter():
    with pytest.raises(ParseError, match="must be a YAML mapping"):
        parse_frontmatter("---\n- just\n- a\n- list\n---\nBody\n")


def test_read_valid_skill(tmp_path):
    skill_dir = tmp_path / "my-skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("---\nname: my-skill\ndescription: A test skill\nlicense: MIT\n---\n# My Skill\n")
    props = read_properties(skill_dir)
    assert props.name == "my-skill"
    assert props.description == "A test skill"
    assert props.license == "MIT"


def test_read_with_metadata(tmp_path):
    skill_dir = tmp_path / "my-skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("---\nname: my-skill\ndescription: A test skill\nmetadata:\n  author: Test Author\n  version: '1.0'\n---\nBody\n")
    props = read_properties(skill_dir)
    assert props.metadata == {"author": "Test Author", "version": "1.0"}


def test_missing_skill_md(tmp_path):
    with pytest.raises(ParseError, match="SKILL.md not found"):
        read_properties(tmp_path)


def test_missing_name(tmp_path):
    skill_dir = tmp_path / "my-skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("---\ndescription: A test skill\n---\nBody\n")
    with pytest.raises(ValidationError, match="Missing required field.*name"):
        read_properties(skill_dir)


def test_missing_description(tmp_path):
    skill_dir = tmp_path / "my-skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("---\nname: my-skill\n---\nBody\n")
    with pytest.raises(ValidationError, match="Missing required field.*description"):
        read_properties(skill_dir)


def test_find_skill_md_prefers_uppercase(tmp_path):
    skill_dir = tmp_path / "my-skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("uppercase")
    (skill_dir / "skill.md").write_text("lowercase")
    result = find_skill_md(skill_dir)
    assert result is not None
    assert result.name == "SKILL.md"


def test_find_skill_md_returns_none_when_missing(tmp_path):
    skill_dir = tmp_path / "my-skill"
    skill_dir.mkdir()
    assert find_skill_md(skill_dir) is None


def test_read_with_allowed_tools(tmp_path):
    skill_dir = tmp_path / "my-skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("---\nname: my-skill\ndescription: A test skill\nallowed-tools: Bash(jq:*) Bash(git:*)\n---\nBody\n")
    props = read_properties(skill_dir)
    assert props.allowed_tools == "Bash(jq:*) Bash(git:*)"
    assert props.to_dict()["allowed-tools"] == "Bash(jq:*) Bash(git:*)"
