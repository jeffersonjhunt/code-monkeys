# skills-ref

Reference library for Agent Skills — validates SKILL.md files and generates prompt XML.

## Usage

```bash
# Validate a skill
skills-ref validate path/to/skill

# Read skill properties (outputs JSON)
skills-ref read-properties path/to/skill

# Generate <available_skills> XML for agent prompts
skills-ref to-prompt path/to/skill-a path/to/skill-b
```

## Install

```bash
uv sync
source .venv/bin/activate
```

## Attribution

Derived from [agentskills/skills-ref](https://github.com/agentskills/agentskills/tree/main/skills-ref) by Keith Lazuka (Anthropic), licensed under Apache-2.0.
