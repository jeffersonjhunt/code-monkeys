SKILLS := $(wildcard */SKILL.md)
SKILL_DIRS := $(dir $(SKILLS))
CLAUDE_SKILLS := $(HOME)/.claude/skills
KIRO_SKILLS := $(HOME)/.kiro/skills
INSTALL_DIR := $(HOME)/.local/share/agent-skills

.PHONY: help list test validate clean build new install uninstall deps changelog bump
.DEFAULT_GOAL := help

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

list: ## List available skills
	@echo "Available skills:"
	@for d in $(SKILL_DIRS); do echo "  $${d%/}"; done

test: ## Run smoke tests on all skills
	@for d in $(SKILL_DIRS); do \
		echo "Testing $${d%/}..."; \
		if [ -d "$${d}scripts" ]; then \
			for f in $${d}scripts/*.py; do \
				[ -f "$$f" ] || continue; \
				python3 "$$f" --help > /dev/null 2>&1 || echo "  FAIL: $$f"; \
			done; \
		fi; \
	done
	@echo "Done."

validate: ## Validate all SKILL.md files
	@for d in $(SKILL_DIRS); do \
		cd skills-ref && uv run skills-ref validate "../$${d%/}" && cd ..; \
	done

build: ## Build (no-op for interpreted scripts)
	@echo "Nothing to build (scripts are interpreted)."

clean: ## Remove generated artifacts and installed skills
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -name '*.pyc' -delete 2>/dev/null || true
	@for d in $(SKILL_DIRS); do \
		skill=$${d%/}; \
		rm -f "$(CLAUDE_SKILLS)/$$skill"; \
		rm -f "$(KIRO_SKILLS)/$$skill"; \
		rm -rf "$(INSTALL_DIR)/$$skill"; \
	done

new: ## Scaffold a new skill (SKILL=<name>)
ifndef SKILL
	$(error Usage: make new SKILL=<skill-name>)
endif
	mkdir -p $(SKILL)/scripts $(SKILL)/assets $(SKILL)/references
	@echo "---\nname: $(SKILL)\ndescription: \nlicense: Apache-2.0\nmetadata:\n  author: ooe\n  version: \"1.0\"\n---" > $(SKILL)/SKILL.md
	@echo "Created skill: $(SKILL)"

install: ## Install skills for claude/kiro/opencode
	@mkdir -p $(INSTALL_DIR) $(CLAUDE_SKILLS) $(KIRO_SKILLS)
	@for d in $(SKILL_DIRS); do \
		skill=$${d%/}; \
		rm -rf "$(INSTALL_DIR)/$$skill"; \
		cp -R "$$skill" "$(INSTALL_DIR)/$$skill"; \
		rm -f "$(CLAUDE_SKILLS)/$$skill"; \
		ln -s "$(INSTALL_DIR)/$$skill" "$(CLAUDE_SKILLS)/$$skill"; \
		rm -f "$(KIRO_SKILLS)/$$skill"; \
		ln -s "$(INSTALL_DIR)/$$skill" "$(KIRO_SKILLS)/$$skill"; \
		echo "Installed $$skill"; \
	done
	@echo ""
	@echo "Installed to: $(INSTALL_DIR)/"
	@echo "Symlinked from:"
	@echo "  Claude:  $(CLAUDE_SKILLS)/"
	@echo "  Kiro:    $(KIRO_SKILLS)/"

uninstall: ## Remove installed skills
	@for d in $(SKILL_DIRS); do \
		skill=$${d%/}; \
		rm -f "$(CLAUDE_SKILLS)/$$skill"; \
		rm -f "$(KIRO_SKILLS)/$$skill"; \
		rm -rf "$(INSTALL_DIR)/$$skill"; \
		echo "Removed $$skill"; \
	done

deps: ## Check/resolve skill dependencies
	@python3 scripts/resolve-deps.py --check

changelog: ## Show changelog for a skill (SKILL=<name>)
ifndef SKILL
	@python3 scripts/changelog.py show-all
else
	@python3 scripts/changelog.py show --skill $(SKILL)
endif

bump: ## Bump version for a skill (SKILL=<name> [TYPE=patch|minor|major])
ifndef SKILL
	$(error Usage: make bump SKILL=<skill-name> [TYPE=patch|minor|major])
endif
	@python3 scripts/changelog.py bump --skill $(SKILL) --type $(or $(TYPE),patch)
