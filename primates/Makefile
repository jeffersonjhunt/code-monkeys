# Makefile for primates project

TARGETS := minion embedded miniforge3 claude opencode kiro lamp huggingface

MAKEFILE_PATH := $(abspath $(lastword $(MAKEFILE_LIST)))
DIR := $(notdir $(patsubst %/,%,$(dir $(MAKEFILE_PATH))))
KERNEL := $(shell uname -r)

BUILD_ARGS ?=
ifdef FORCE
BUILD_ARGS += --no-cache
endif
ifdef UNSAFE_SSL
BUILD_ARGS += --build-arg UNSAFE_SSL=$(UNSAFE_SSL)
endif
ifdef FRESH
BUILD_ARGS += --build-arg FRESH=$(FRESH)
endif

.PHONY:
help:
	@echo "Usage: make [target] [FORCE=1] [UNSAFE_SSL=true] [FRESH=false] [BUILD_ARGS='...']"
	@echo ""
	@echo "Targets:"
	@echo "  all                    Build codemonkey base + all standard images"
	@echo "  spark                  Build all + llama-cpp-spark + comfy-ui-spark (requires NVIDIA kernel)"
	@echo "  codemonkey.build       Build the codemonkey base image"
	@echo "  miniforge3.build       Build Miniforge3 (conda for aarch64)"
	@echo "  claude.build           Build claude-code environment"
	@echo "  opencode.build         Build opencode-ai environment"
	@echo "  kiro.build             Build Amazon Kiro CLI environment"
	@echo "  embedded.build         Build embedded development environment (cc65, vasm, libfmt, libboost)"
	@echo "  lamp.build             Build LAMP stack (Apache, MariaDB, PHP)"
	@echo "  huggingface.build      Build Hugging Face environment (python3 venv, hf cli)"
	@echo "  minion.build           Build minion (bare codemonkey extension)"
	@echo "  llama-cpp-spark.build  Build llama.cpp for DGX Spark (requires NVIDIA kernel)"
	@echo "  comfy-ui-spark.build   Build ComfyUI for DGX Spark (requires NVIDIA kernel)"
	@echo "  upgrade                Upgrade all existing primate home volumes with latest dotfiles"
	@echo "  <name>.upgrade         Upgrade a specific primate home volume"
	@echo "  clean                  Remove all built images"
	@echo "  help                   Show this help message"
	@echo ""
	@echo "Arguments:"
	@echo "  FORCE=1                Rebuild images from scratch (--no-cache)"
	@echo "  UNSAFE_SSL=true        Disable SSL verification during build (sets TAINTED_BUILD=true in image)"
	@echo "  FRESH=false            Skip freshclam (ClamAV DB update) to speed up codemonkey build"
	@echo "  BUILD_ARGS='...'       Pass additional arguments to docker buildx build"

.PHONY:
codemonkey.build:
	echo "Building codemonkey image..."
	cd ..; \
	docker buildx build $(BUILD_ARGS) -t codemonkey:latest -f codemonkey.dockerfile .

.PHONY:
llama-cpp-spark.build: _nv_check
	echo "Building llama.cpp image..."
	docker buildx build $(BUILD_ARGS) -t llama-cpp-spark:latest --target full -f llama-cpp-spark.dockerfile .

.PHONY:
comfy-ui-spark.build: _nv_check
	echo "Building comfy-ui-spark image..."
	docker buildx build $(BUILD_ARGS) -t comfy-ui-spark:latest -f comfy-ui-spark.dockerfile .

.PHONY:
all: codemonkey.build $(addsuffix .build,$(TARGETS))

.PHONY:
spark: all llama-cpp-spark.build comfy-ui-spark.build

.PHONY:
claude.build:
	echo "Building claude image..."
	cd ..; \
	docker buildx build $(BUILD_ARGS) --build-arg IMAGE_NAME=claude -t claude:latest -f primates/claude.dockerfile .

.PHONY:
%.build:
	echo $@; \
	docker buildx build $(BUILD_ARGS) --build-arg IMAGE_NAME=$(basename $@) -t $(basename $@):latest -f ./$(basename $@).dockerfile .

REPO_ROOT := $(abspath $(dir $(MAKEFILE_PATH))/..)

define UPGRADE_SCRIPT
SRC=/opt/user-jhunt
HOME=/home/codemonkey
cp "$$SRC/zaliases"  "$$HOME/.zaliases"
cp "$$SRC/zbase"     "$$HOME/.zbase"
cp "$$SRC/zprofile"  "$$HOME/.zprofile"
[ -f "$$SRC/gitconfig" ] && cp "$$SRC/gitconfig" "$$HOME/.gitconfig"
cp "$$SRC/gitignore" "$$HOME/.gitignore"
cp "$$SRC/vimrc"     "$$HOME/.vimrc"
cp "$$SRC/toprc"     "$$HOME/.toprc"
cp "$$SRC/zshrc.template" "$$HOME/.zshrc"
cp "$$SRC/zfuncs"    "$$HOME/.zfuncs"
if [ -d "$$HOME/.oh-my-zsh" ]; then
  git -C "$$HOME/.oh-my-zsh" pull --quiet 2>/dev/null || true
  for plugin in zsh-autosuggestions zsh-completions zsh-syntax-highlighting; do
    if [ -d "$$HOME/.oh-my-zsh/custom/plugins/$$plugin" ]; then
      git -C "$$HOME/.oh-my-zsh/custom/plugins/$$plugin" pull --quiet 2>/dev/null || true
    fi
  done
fi
mkdir -p "$$HOME/.oh-my-zsh/custom/themes"
cp "$$SRC/jjh.zsh-theme" "$$HOME/.oh-my-zsh/custom/themes/jjh.zsh-theme"
if [ -d "$$SRC/claude" ]; then
  mkdir -p "$$HOME/.claude/commands"
  cp "$$SRC/claude/settings.json" "$$HOME/.claude/settings.json"
  cp "$$SRC/claude/commands/"* "$$HOME/.claude/commands/" 2>/dev/null
fi
chown -R codemonkey:codemonkey "$$HOME"
endef
export UPGRADE_SCRIPT

.PHONY:
%.upgrade:
	@VOL=$(basename $@)-home; \
	if ! docker volume inspect "$$VOL" >/dev/null 2>&1; then \
		echo "skip: volume $$VOL does not exist"; \
	else \
		echo "upgrading $(basename $@)..."; \
		docker run --rm \
			--volume "$(REPO_ROOT):/opt/user-jhunt:ro" \
			--volume "$$VOL:/home/codemonkey" \
			codemonkey:latest bash -c "$$UPGRADE_SCRIPT"; \
		echo "  done: $(basename $@)"; \
	fi

.PHONY:
upgrade:
	@for name in codemonkey $(TARGETS); do \
		$(MAKE) --no-print-directory $$name.upgrade; \
	done

.PHONY:
clean:
	echo "Cleaning up images..."
	docker rmi -f $(TARGETS:%=%:latest) codemonkey:latest llama-cpp-spark:latest comfy-ui-spark:latest || true

.PHONY:
_nv_check:
ifneq ($(shell echo $(KERNEL) | grep -c -- '-nvidia$$'),1)
	$(error This machine is not running an NVIDIA kernel. Detected: $(KERNEL))
endif
