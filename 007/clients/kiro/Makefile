# Makefile for kiro client files (MCP servers, agents, ai-context)
#
# Copies files into $HOME following the same pattern as 007/skills/Makefile.
# Works identically inside containers (persistent home volume) and on the host.

KIRO_DATA := $(HOME)/.local/share/kiro
KIRO_CONFIG := $(HOME)/.kiro

MCP_SERVERS := $(wildcard mcp-servers/*)
AGENTS := $(wildcard agents/*.json)
AI_CONTEXT := ai-context

.PHONY: help install uninstall
.DEFAULT_GOAL := help

help: ## Show this help
	@echo "Usage: make [install|uninstall]"
	@echo ""
	@echo "Targets:"
	@echo "  install    Copy kiro client files into \$$HOME"
	@echo "  uninstall  Remove installed kiro client files from \$$HOME"

install: ## Install kiro client files into $HOME
	@mkdir -p "$(KIRO_DATA)/custom-mcp-servers" "$(KIRO_DATA)/personal" "$(KIRO_CONFIG)/agents"
	@for srv in $(MCP_SERVERS); do \
		name=$$(basename "$$srv"); \
		rm -rf "$(KIRO_DATA)/custom-mcp-servers/$$name"; \
		cp -R "$$srv" "$(KIRO_DATA)/custom-mcp-servers/$$name"; \
		echo "Installed MCP server: $$name"; \
	done
	@rm -rf "$(KIRO_DATA)/personal/obsidian-tasks"
	@cp -R mcp-servers/obsidian-tasks "$(KIRO_DATA)/personal/obsidian-tasks"
	@echo "Installed obsidian-tasks → personal/"
	@rm -rf "$(KIRO_DATA)/ai-context"
	@cp -R $(AI_CONTEXT) "$(KIRO_DATA)/ai-context"
	@echo "Installed ai-context"
	@for agent in $(AGENTS); do \
		name=$$(basename "$$agent"); \
		cp "$$agent" "$(KIRO_CONFIG)/agents/$$name"; \
		echo "Installed agent: $$name"; \
	done
	@echo ""
	@echo "Installed to:"
	@echo "  MCP servers: $(KIRO_DATA)/custom-mcp-servers/"
	@echo "  AI context:  $(KIRO_DATA)/ai-context/"
	@echo "  Agents:      $(KIRO_CONFIG)/agents/"

uninstall: ## Remove installed kiro client files
	@for srv in $(MCP_SERVERS); do \
		name=$$(basename "$$srv"); \
		rm -rf "$(KIRO_DATA)/custom-mcp-servers/$$name"; \
		echo "Removed MCP server: $$name"; \
	done
	@rm -rf "$(KIRO_DATA)/personal/obsidian-tasks"
	@rm -rf "$(KIRO_DATA)/ai-context"
	@for agent in $(AGENTS); do \
		name=$$(basename "$$agent"); \
		rm -f "$(KIRO_CONFIG)/agents/$$name"; \
		echo "Removed agent: $$name"; \
	done
	@echo "Uninstall complete."
