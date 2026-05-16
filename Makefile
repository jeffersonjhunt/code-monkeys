.PHONY: test

test: ## Run all tests
	cd 007/skills/skills-ref && uv run pytest ../tests/ -v
