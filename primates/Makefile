# Makefile for primates project

MAKEFILE_PATH := $(abspath $(lastword $(MAKEFILE_LIST)))
DIR := $(notdir $(patsubst %/,%,$(dir $(MAKEFILE_PATH))))
KERNEL := $(shell uname -r)
REPO_ROOT := $(abspath $(dir $(MAKEFILE_PATH))/..)

# Single source of truth for the fleet roster — see primates/fleet.conf for the field layout.
# `make all` builds in_all=yes rows; `make upgrade` walks home_volume=yes rows — codemonkey
# included, since its row says home_volume=yes and it has a codemonkey-home volume like any
# other. Row order in fleet.conf is the build order.
FLEET := $(REPO_ROOT)/primates/fleet.conf
TARGETS := $(shell awk -F: '!/^#/ && NF==7 && $$3=="yes" {print $$1}' < '$(FLEET)' 2>/dev/null)
UPGRADE_TARGETS := $(shell awk -F: '!/^#/ && NF==7 && $$7=="yes" {print $$1}' < '$(FLEET)' 2>/dev/null)

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
	@echo "  cuda                   Build all + cuda-llama-cpp + cuda-comfy + cuda-vllm (requires NVIDIA kernel)"
	@echo "  codemonkey.build       Build the codemonkey base image"
	@echo "  miniforge3.build       Build Miniforge3 (conda for aarch64)"
	@echo "  claude.build           Build claude-code environment"
	@echo "  opencode.build         Build opencode-ai environment"
	@echo "  aichat.build           Build aichat (generic OpenAI-compatible chat REPL)"
	@echo "  kiro.build             Build Amazon Kiro CLI environment"
	@echo "  embedded.build         Build embedded development environment (cc65, vasm, libfmt, libboost)"
	@echo "  lamp.build             Build LAMP stack (Apache, MariaDB, PHP)"
	@echo "  huggingface.build      Build Hugging Face environment (python3 venv, hf cli)"
	@echo "  minion.build           Build minion (bare codemonkey extension)"
	@echo "  nyckel.build           Build nyckel (Alpine secrets-ops primate: age + sops)"
	@echo "  samba.build            Build samba (Debian file-server primate: maintained Samba + macOS/TM VFS)"
	@echo "  cuda-base.build        Build the shared CUDA base (cuda-base:runtime + cuda-base:devel)"
	@echo "  cuda-llama-cpp.build   Build llama.cpp (cross-GPU sm_89/120/121; requires NVIDIA kernel)"
	@echo "  cuda-comfy.build       Build ComfyUI (cross-GPU; requires NVIDIA kernel)"
	@echo "  cuda-vllm.build        Build vLLM with native sm_89/120/121 kernels (requires NVIDIA kernel)"
	@echo "  spark-bench.build      Build LLM eval harness primate (build on x86 host; see 007/skills/spark-bench/)"
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
cuda-base.build:
	echo "Building cuda-base image (runtime + devel)..."
	docker buildx build $(BUILD_ARGS) --build-arg CUDA_FLAVOR=runtime -t cuda-base:runtime -f cuda-base.dockerfile .
	docker buildx build $(BUILD_ARGS) --build-arg CUDA_FLAVOR=devel   -t cuda-base:devel   -f cuda-base.dockerfile .

.PHONY:
cuda-llama-cpp.build: _nv_check cuda-base.build
	echo "Building cuda-llama-cpp image..."
	docker buildx build $(BUILD_ARGS) -t cuda-llama-cpp:latest --target full -f cuda-llama-cpp.dockerfile .

.PHONY:
cuda-comfy.build: _nv_check cuda-base.build
	echo "Building cuda-comfy image..."
	docker buildx build $(BUILD_ARGS) -t cuda-comfy:latest -f cuda-comfy.dockerfile .

.PHONY:
cuda-vllm.build: _nv_check cuda-base.build
	echo "Building cuda-vllm image..."
	docker buildx build $(BUILD_ARGS) -t cuda-vllm:latest -f cuda-vllm.dockerfile .

# Refuse to act on a missing/empty/unparseable inventory: an empty derived list must never
# look like "nothing to do" (F1/F4/F5/F10 were exactly that failure mode, silently).
.PHONY: _fleet_check
_fleet_check:
	@test -s "$(FLEET)" || { echo "ERROR: $(FLEET) missing or empty — refusing to build/upgrade an empty fleet" >&2; exit 1; }
	@test -n "$(TARGETS)" || { echo "ERROR: $(FLEET) parsed to zero in_all=yes targets — check its format" >&2; exit 1; }

.PHONY:
all: _fleet_check codemonkey.build $(addsuffix .build,$(TARGETS))

.PHONY:
cuda: all cuda-llama-cpp.build cuda-comfy.build cuda-vllm.build

# Deprecated alias — kept so existing muscle memory / scripts keep working.
.PHONY:
spark: cuda

.PHONY:
claude.build:
	echo "Building claude image..."
	cd ..; \
	docker buildx build $(BUILD_ARGS) --build-arg IMAGE_NAME=claude -t claude:latest -f primates/claude.dockerfile .

.PHONY:
%.build:
	echo $@; \
	docker buildx build $(BUILD_ARGS) --build-arg IMAGE_NAME=$(basename $@) -t $(basename $@):latest -f ./$(basename $@).dockerfile .

# The home-volume dotfile sync lives in ONE place — primates/upgrade-home.sh — reached through the
# read-only repo mount below. zfuncs' primate-upgrade runs the same file the same way.
.PHONY:
%.upgrade:
	@VOL=$(basename $@)-home; \
	SRC='$(REPO_ROOT)'; \
	if [ -f /.dockerenv ] && command -v hostpath >/dev/null 2>&1; then \
		SRC=$$(hostpath '$(REPO_ROOT)') || { \
			echo "ERROR: $(REPO_ROOT) is not under a host-shared mount, so the upgrade container cannot see it." >&2; \
			echo "       Bind mounts resolve on the Docker daemon host — run this from the host checkout." >&2; \
			exit 1; \
		}; \
	fi; \
	if ! docker volume inspect "$$VOL" >/dev/null 2>&1; then \
		echo "skip: volume $$VOL does not exist"; \
	else \
		echo "upgrading $(basename $@)..."; \
		docker run --rm \
			--env "PRIMATE=$(basename $@)" \
			--volume "$$SRC:/opt/user-jhunt:ro" \
			--volume "$$VOL:/home/codemonkey" \
			codemonkey:latest bash /opt/user-jhunt/primates/upgrade-home.sh \
			|| { echo "  FAILED: $(basename $@) (home volume may be partially upgraded)" >&2; exit 1; }; \
		echo "  done: $(basename $@)"; \
	fi

.PHONY:
upgrade: _fleet_check
	@rc=0; \
	for name in $(UPGRADE_TARGETS); do \
		$(MAKE) --no-print-directory $$name.upgrade || rc=1; \
	done; \
	if [ "$$rc" -ne 0 ]; then echo "ERROR: one or more upgrades FAILED (see above)" >&2; fi; \
	exit $$rc

.PHONY:
clean: _fleet_check
	echo "Cleaning up images..."
	docker rmi -f $(TARGETS:%=%:latest) spark-bench:latest codemonkey:latest cuda-llama-cpp:latest cuda-comfy:latest cuda-vllm:latest cuda-base:runtime cuda-base:devel || true

# Guard for the CUDA image targets. Passes on any host that can build/run
# them: a DGX Spark (-nvidia kernel), or an x86/other box with an NVIDIA GPU
# (nvidia-smi present, or the card visible on the PCI bus). Kernel-name-only
# was Spark-specific and wrongly blocked x86 NVIDIA hosts like ren (4090).
.PHONY:
_nv_check:
	@if echo "$(KERNEL)" | grep -q -- '-nvidia$$'; then :; \
	elif command -v nvidia-smi >/dev/null 2>&1; then :; \
	elif lspci 2>/dev/null | grep -qi nvidia; then :; \
	else \
		echo "ERROR: no NVIDIA GPU detected — kernel '$(KERNEL)' is not an -nvidia kernel, nvidia-smi is absent, and lspci shows no NVIDIA device." >&2; \
		exit 1; \
	fi
