# 007 — Skills Library

A portable collection of agent skills for inclusion in other projects.

Each skill lives in its own directory and follows a standard structure:

```
<skill-name>/
├── SKILL.md          # Skill metadata (name, description, license, author, version)
├── scripts/          # Executable scripts
├── assets/           # Static assets (images, data files)
└── references/       # Reference material
```

## Skills

| Skill | Description |
|-------|-------------|
| [math-fibonacci](math-fibonacci/) | Fibonacci sequence generation and ASCII tile art (kept as a reference template for skill authoring) |
| [img-sixel](img-sixel/) | Display images as SIXEL graphics or convert SIXEL to PNG |
| [review-adversarial](review-adversarial/) | Adversarial code review with state-tracked review loops |
| [althingi](althingi/) | Roundtable discussions with multiple agent voices (subagent or solo mode) |
| [docs-issues](docs-issues/) | Manage markdown-based issues in docs/reviews/ and export to GitHub/GitLab/todo.md |

## Usage

Include this library as a submodule or copy skills into your project:

```bash
git submodule add <repo-url> skills
```

Then invoke skill scripts directly:

```bash
python skills/math-fibonacci/scripts/fibonacci-generator.py --count 10
python skills/math-fibonacci/scripts/fibonacci-tiles.py --count 6
```

## Development

```bash
make test    # Run all skill tests
make clean   # Remove generated artifacts
make list    # List available skills
```

## License

Apache-2.0

---

## Attribution

The `skills-ref/` tool is derived from [agentskills/skills-ref](https://github.com/agentskills/agentskills/tree/main/skills-ref) by Keith Lazuka (Anthropic), licensed under Apache-2.0.
