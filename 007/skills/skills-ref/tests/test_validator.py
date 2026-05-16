"""Tests for validator module."""

from skills_ref.validator import validate


def test_valid_skill(tmp_path):
    skill_dir = tmp_path / "my-skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("""---
name: my-skill
description: A test skill
---
# My Skill
""")
    assert validate(skill_dir) == []


def test_nonexistent_path(tmp_path):
    errors = validate(tmp_path / "nonexistent")
    assert "does not exist" in errors[0]


def test_not_a_directory(tmp_path):
    f = tmp_path / "file.txt"
    f.write_text("test")
    errors = validate(f)
    assert "Not a directory" in errors[0]


def test_missing_skill_md(tmp_path):
    skill_dir = tmp_path / "my-skill"
    skill_dir.mkdir()
    errors = validate(skill_dir)
    assert "Missing required file: SKILL.md" in errors[0]


def test_invalid_name_uppercase(tmp_path):
    skill_dir = tmp_path / "MySkill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("---\nname: MySkill\ndescription: A test skill\n---\nBody\n")
    errors = validate(skill_dir)
    assert any("lowercase" in e for e in errors)


def test_name_too_long(tmp_path):
    long_name = "a" * 70
    skill_dir = tmp_path / long_name
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(f"---\nname: {long_name}\ndescription: A test skill\n---\nBody\n")
    errors = validate(skill_dir)
    assert any("exceeds" in e and "character limit" in e for e in errors)


def test_name_leading_hyphen(tmp_path):
    skill_dir = tmp_path / "-my-skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("---\nname: -my-skill\ndescription: A test skill\n---\nBody\n")
    errors = validate(skill_dir)
    assert any("cannot start or end with a hyphen" in e for e in errors)


def test_name_consecutive_hyphens(tmp_path):
    skill_dir = tmp_path / "my--skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("---\nname: my--skill\ndescription: A test skill\n---\nBody\n")
    errors = validate(skill_dir)
    assert any("consecutive hyphens" in e for e in errors)


def test_name_invalid_characters(tmp_path):
    skill_dir = tmp_path / "my_skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("---\nname: my_skill\ndescription: A test skill\n---\nBody\n")
    errors = validate(skill_dir)
    assert any("invalid characters" in e for e in errors)


def test_name_directory_mismatch(tmp_path):
    skill_dir = tmp_path / "wrong-name"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("---\nname: correct-name\ndescription: A test skill\n---\nBody\n")
    errors = validate(skill_dir)
    assert any("must match skill name" in e for e in errors)


def test_unexpected_fields(tmp_path):
    skill_dir = tmp_path / "my-skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("---\nname: my-skill\ndescription: A test skill\nunknown_field: bad\n---\nBody\n")
    errors = validate(skill_dir)
    assert any("Unexpected fields" in e for e in errors)


def test_valid_with_all_fields(tmp_path):
    skill_dir = tmp_path / "my-skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("---\nname: my-skill\ndescription: A test skill\nlicense: MIT\nmetadata:\n  author: Test\n---\nBody\n")
    assert validate(skill_dir) == []


def test_allowed_tools_accepted(tmp_path):
    skill_dir = tmp_path / "my-skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("---\nname: my-skill\ndescription: A test skill\nallowed-tools: Bash(jq:*) Bash(git:*)\n---\nBody\n")
    assert validate(skill_dir) == []


def test_description_too_long(tmp_path):
    skill_dir = tmp_path / "my-skill"
    skill_dir.mkdir()
    long_desc = "x" * 1100
    (skill_dir / "SKILL.md").write_text(f"---\nname: my-skill\ndescription: {long_desc}\n---\nBody\n")
    errors = validate(skill_dir)
    assert any("exceeds" in e and "1024" in e for e in errors)


def test_compatibility_too_long(tmp_path):
    skill_dir = tmp_path / "my-skill"
    skill_dir.mkdir()
    long_compat = "x" * 550
    (skill_dir / "SKILL.md").write_text(f"---\nname: my-skill\ndescription: A test skill\ncompatibility: {long_compat}\n---\nBody\n")
    errors = validate(skill_dir)
    assert any("exceeds" in e and "500" in e for e in errors)
