"""Tests for prompt module."""

from skills_ref.prompt import to_prompt


def test_empty_list():
    assert to_prompt([]) == "<available_skills>\n</available_skills>"


def test_single_skill(tmp_path):
    skill_dir = tmp_path / "my-skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("---\nname: my-skill\ndescription: A test skill\n---\nBody\n")
    result = to_prompt([skill_dir])
    assert "<available_skills>" in result
    assert "</available_skills>" in result
    assert "<name>\nmy-skill\n</name>" in result
    assert "<description>\nA test skill\n</description>" in result
    assert "SKILL.md" in result


def test_multiple_skills(tmp_path):
    for name in ("skill-a", "skill-b"):
        d = tmp_path / name
        d.mkdir()
        (d / "SKILL.md").write_text(f"---\nname: {name}\ndescription: Skill {name}\n---\nBody\n")
    result = to_prompt([tmp_path / "skill-a", tmp_path / "skill-b"])
    assert result.count("<skill>") == 2
    assert "skill-a" in result
    assert "skill-b" in result


def test_special_characters_escaped(tmp_path):
    skill_dir = tmp_path / "special-skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("---\nname: special-skill\ndescription: Use <foo> & <bar> tags\n---\nBody\n")
    result = to_prompt([skill_dir])
    assert "&lt;foo&gt;" in result
    assert "&amp;" in result
    assert "<foo>" not in result
