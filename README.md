# code-monkeys

Dotfiles, shell configuration, and the **primates** containerized development environment system.

## Quick Start

```bash
git clone <repo-url> && cd code-monkeys
./setup
cd primates
make all
```

This gives you a working shell environment and Docker images. To pull in secrets from a previous setup (needs a `~/.local/share/hemlighet` clone and this machine's age key — see [Vault](#vault-optional)):

```bash
./vault unlock
```

## Setup

The `setup` script symlinks dotfiles from this repo into `$HOME`:

```bash
./setup              # install symlinks, clone oh-my-zsh plugins
./setup --dry-run    # preview without making changes
./setup --uninstall  # remove symlinks and cloned repos
```

What it does:
- Installs Oh-My-Zsh if it isn't already there, and sets zsh as the default shell
- Symlinks `gitconfig` (if present), `gitignore`, `vimrc`, `toprc`, `tmux.conf`, `zaliases`, `zbase`, `zfuncs`, `zprofile` as dotfiles in `$HOME`
- Symlinks `ssh` and `aws` if present (created by `vault unlock`)
- Symlinks `fastfetch` into `~/.config/` and `jjh.zsh-theme` into `~/.oh-my-zsh/custom/themes/`
- Links `claude/settings.json` and `claude/commands` **into** `~/.claude` (which stays a real directory — it holds Claude Code's live state). Existing real files there are left alone, not overwritten
- Symlinks each script in `bin/` individually into `~/.local/bin/` (creates the directory if missing — files from other installers are left alone)
- Installs `zbase` as `~/.zshrc` (copy, not symlink)
- Clones oh-my-zsh plugins: `zsh-autosuggestions`, `zsh-completions`, `zsh-syntax-highlighting`
- Installs git hooks from `hooks/` into `.git/hooks/`
- Installs the agent skills library (`make -C 007/skills install`) — symlinks each skill into `~/.claude/skills/` and `~/.kiro/skills/`
- On macOS: installs custom key bindings to `~/Library/KeyBindings`
- Warns (non-fatal) if optional tools `aws` or `fastfetch` are not installed (the `bin/aws` shim covers a missing AWS CLI by running it in the `minion` container)

## Shell Configuration

The shell config is layered:

1. **`zshrc.template`** — installed as `~/.zshrc` inside containers; sources `~/.zbase`, fixes ownership of mounted directories, activates the image's conda environment if present
2. **`zbase`** — main config: oh-my-zsh setup, plugins, PATH, editor, history settings
3. **`zaliases`** — aliases (`dps`, `dpi`, `probe`, `nvtop` (GPU monitor via the cuda-base primate), `ocd`, `git.all`, etc.)
4. **`zfuncs`** — functions: `primate()`, `primate-session()`, `primate-session-list()`, `primate-session-resume()`, `primate-session-kill()`, `primate-upgrade()`, `zoo()`, `which-os()`, `code-here()`, `tree()`, `clamscan()`, `tad()`, `watch()`

## Primates

Primates are purpose-built Docker images for different development domains. They all share the `codemonkey` base image and a common shell environment.

### Image Hierarchy

```
debian:13-slim → codemonkey → miniforge3 → claude
                             │            → opencode
                             │            → aichat
                             │            → kiro
                             │            → spark-bench   (x86-only)
                             → embedded
                             → lamp
                             → huggingface
                             → minion

nvidia/cuda:13.2.1 → cuda-base → cuda-llama-cpp  (multi-stage: full/light/server)
                              → cuda-comfy
                              → cuda-vllm       (vLLM with native sm_89/120/121 cutlass)

alpine:3.21        → nyckel    (standalone — age + sops only)
debian:trixie-slim → samba     (standalone — file-server daemon)
```

| Image | Purpose |
|---|---|
| **codemonkey** | Base image — Debian 13, zsh, oh-my-zsh, git, vim, build-essential, cmake, python3, nodejs, nmap, clamav, AWS CLI v2 |
| **miniforge3** | Adds Miniforge3 (conda for aarch64 and x86_64), creates `miniforge3-env`, installs `uv` in the conda base env |
| **claude** | Adds Claude Code via native installer, creates `claude-env` |
| **opencode** | Adds opencode via the curl installer (binary in `/usr/local/bin`), creates `opencode-env`. Ships a placeholder `opencode.json.example`; the real config (LiteLLM router + model + corpus MCP) is gitignored and SOPS+age-encrypted in `hemlighet`, synced into the home volume by `make opencode.upgrade` |
| **aichat** | Adds [aichat](https://github.com/sigoden/aichat) (generic OpenAI-compatible chat REPL, static binary in `/usr/local/bin`), creates `aichat-env`. Deliberately **provider-agnostic** — ships only a placeholder config; point `AICHAT_CONFIG_DIR` at an external config dir (endpoint, models, roles) at runtime |
| **kiro** | Adds Amazon Kiro CLI via native installer, creates `kiro-env` |
| **spark-bench** | LLM eval harnesses (AIME, GPQA, LiveCodeBench, tau2-bench, SWE-Bench via SWE-agent) run against the cluster endpoint. **amd64-only** (SWE-Bench testbeds are x86) — runs on `intel-nuc.tworivers`; see `007/skills/spark-bench/` |
| **embedded** | Adds libfmt, libboost, cc65, vasm 6502 assembler |
| **lamp** | Adds Apache, MariaDB, PHP |
| **huggingface** | Adds python3 venv and huggingface-cli |
| **minion** | Bare codemonkey extension (general-purpose runner) |
| **nyckel** | Standalone (from `alpine:3.21`, not codemonkey) — age + sops only; the containerized secrets-ops tooling behind `vault` and the `bin/{sops,age,age-keygen}` shims |
| **samba** | Standalone (from `debian:trixie-slim`) — Samba file-server daemon with the macOS/Time-Machine VFS modules |
| **cuda-base** | Shared CUDA base for the GPU images (one dockerfile, two flavors — `cuda-base:runtime` + `cuda-base:devel`). Adds `nvtop`, the codemonkey user, and cross-GPU arch defaults (sm_89 RTX 4090 / sm_120 RTX 5090 / sm_121 DGX Spark) so the family runs on x86 NVIDIA boxes as well as Spark |
| **cuda-llama-cpp** | llama.cpp for NVIDIA GPUs (from `cuda-base`; cross-GPU default arch sm_89/120/121) |
| **cuda-comfy** | ComfyUI for NVIDIA GPUs (from `cuda-base:runtime`; cross-GPU via PyTorch wheels) |
| **cuda-vllm** | vLLM v0.28.0 source build with native sm_89/120/121 cutlass (runtime from `cuda-base:devel`) — backs the spark-cluster, unblocks FP8 dense / NVFP4 MoE that crashes on upstream `vllm/vllm-openai`, and runs on the 4090s |

### Building

```bash
cd primates
make help                   # show all targets
make all                    # build codemonkey + all standard images
make cuda                   # build all + the cuda-* GPU images (requires an NVIDIA GPU)
make cuda-base.build        # shared CUDA base (cuda-base:runtime + cuda-base:devel); auto-built by the GPU targets
make claude.build           # build a single image
make all FORCE=1            # rebuild from scratch (--no-cache)
make all UNSAFE_SSL=true    # disable SSL verification during build (tainted build)
make all FRESH=false        # skip freshclam (faster codemonkey build)
make clean                  # remove all images
```

### Launching

The `primate` shell function (defined in `zfuncs`) launches containers:

```bash
primate claude              # start claude image with workspace mount
primate embedded --no-workspace  # start without mounting current directory
primate minion --allow-home      # allow the workspace mount to be $HOME (refused otherwise)
```

The workspace mount is `$(pwd)`, so launching from `~` would put `.ssh`, `.aws`, `.docker` and
every other dotfile at `/home/codemonkey/workspace`, read-write. `primate` and `primate-session`
refuse that and say so; `--allow-home` is the override, `--no-workspace` the usual answer.
Re-attaching to an existing session makes no new mount and is never refused.

What `primate` does:
- Creates a persistent Docker volume `<image>-home` for the home directory — and on the **first
  run of an image** seeds it from the image, then syncs the repo's configs into it with
  `primates/upgrade-home.sh`, so gitignored files the image can only ship as placeholders
  (`opencode.json`, the claude primate's `settings.json`/`commands`) are correct before the shell
  starts. Warns and starts anyway if there is no host repo checkout to sync from
- Mounts `~/.ssh` and `~/.aws` into the container if present
- Mounts `/var/run/docker.sock` into the container if present, with `--group-add <socket gid>` (Docker-out-of-Docker)
- Mounts the current directory as `/home/codemonkey/workspace`
- Exports `HOST_WORKSPACE` / `HOST_SSH_DIR` / `HOST_AWS_DIR` — the *host-side* path of each mount, needed for nested bind mounts (see below)
- Loads environment variables from the `env` file if present
- Auto-publishes any exposed ports
- Enables `--gpus all` on NVIDIA kernel hosts
- Runs as user `codemonkey` with zsh

#### Long-lived sessions

`primate` runs a foreground `--rm` container tied to the TTY: close the terminal (or drop an SSH
connection) and the container is gone. For work that must outlive the connection, use
`primate-session`, which starts a **detached, named** container (PID 1 = `sleep infinity`) and
`docker exec`s into an in-container `tmux` session:

```bash
primate-session claude                # start (or re-attach to) the claude-session container
primate-session claude scratch        # ...under an explicit session name, so one image
primate-session claude build          #    can have several sessions in flight at once
# ctrl-b d detaches; re-run the same command from anywhere to re-attach

zoo                                   # top(1) for primates: live table of all of them
                                      #   ↑↓ select, a resume, e shell, k kill,
                                      #   n new session, N new primate, q quit, ? help
zoo -i 1                              # ...refreshing every second
zoo --once                            # one frame, then exit (also what a pipe gets)
primate-session-list                  # what is in flight, running or stopped
primate-session-resume scratch        # re-attach by session name — no need to recall the image
primate-session-resume                # ...and with one session in flight, not even the name
primate-session-kill scratch          # tear one down (the home volume persists)
```

The `<image>-home` volume survives `primate-session-kill`, so a torn-down session loses nothing
but the running processes. Note the volume is per **image**, not per session — several sessions of
one primate share one home.

Sessions are found by a `primate.session` **label** set at creation, not by their container name:
a session you name `scratch` is a container called `scratch`, with nothing in the name to say it is
ours. Listing and killing therefore ask Docker rather than pattern-matching, and an unrelated
container that happens to share the name cannot be matched. A session started before labels existed
is still killable by `<image>`, via a suffix-only fallback, but will not appear in the listing.

### Docker-out-of-Docker

Primate containers can build and manage sibling containers via the host Docker daemon. This lets AI agents (claude, opencode, kiro) run `docker build`, `make all`, etc. directly.

**How it works:**
- The `codemonkey` base image includes `docker-ce-cli`, `docker-buildx-plugin`, `docker-compose-plugin` and `acl`, so `docker build`, `docker buildx` and `docker compose` all work
- `primate()` / `primate-session()` bind-mount `/var/run/docker.sock` when it exists on the host, and pass `--group-add <socket gid>` (Linux: `stat -c %g`; macOS: `0`, since Docker Desktop's VM presents the socket as `root:root 660` — that grants only the root *group's* rw bit on the socket, not root privileges)
- That is enough for plain `docker …` as the unprivileged `codemonkey` user: **no sudo, no `chmod`, no `chgrp`**
- Belt and braces: `/usr/local/bin/docker` (the `docker-shim` in this repo) shadows `/usr/bin/docker` and quietly re-execs under `sudo -n` if the socket is still not writable — so `docker` works even in a container started by hand without `--group-add`. `zshrc.template` also adds `codemonkey` to the socket's group for *future* logins (`docker exec` / `newgrp`); it cannot fix the shell it runs in, which is what the shim is for

**Usage from inside a primate container:**
```bash
cd workspace/primates            # if code-monkeys repo is your workspace
make all                         # build all images from inside the container — no sudo
docker ps                        # manage sibling containers
docker compose version
```

Never `chmod`/`chgrp` the socket: on a Linux host that inode *is* the host's socket.

**Bind mounts resolve on the daemon host, not inside the container.** A `-v /path:/x`, `--mount`, or compose `volumes:` entry is interpreted by the *host* daemon, so a container-local path (`/tmp/…`, `/home/codemonkey/…`) comes up as an empty host-created directory — or fails with Docker Desktop's file-sharing error. Mount only host-shared directories, under their host path. `primate()` exports those as `HOST_WORKSPACE`, `HOST_SSH_DIR`, `HOST_AWS_DIR`, and the `hostpath` helper (baked into the image) does the translation:

```bash
docker run -v "$(hostpath ~/workspace/proj/data):/data" …
docker compose -f ~/workspace/proj/compose.yaml \
  --project-directory "$(hostpath ~/workspace/proj)" up
```

`docker build .`, `docker cp` and `COPY` are unaffected — the client streams those from inside the container.

**Security note:** Mounting the Docker socket grants root-equivalent access to the host. This is standard for personal dev environments but should not be used in multi-tenant or production contexts.

### Upgrading

After updating dotfiles or the zsh theme, use `primate-upgrade` or the Makefile to update existing home volumes without destroying them.
**Run these from the host checkout only** — both refuse inside a primate, because the home volume of the image you are
running is that container's `$HOME`, and upgrading it would rewrite your shell config under a live session:

```bash
primate-upgrade claude       # upgrade one container's home volume
primate-upgrade --all        # upgrade all existing home volumes

cd primates
make claude.upgrade          # same, via Makefile
make upgrade                 # upgrade all
```

### Container Conventions

- User: `codemonkey` (UID/GID 1000), has passwordless sudo
- Shell: zsh with oh-my-zsh (jjh theme — based on ys, adds conda env display)
- Home: `/home/codemonkey` (persisted via named Docker volume)
- Workspace: `/home/codemonkey/workspace` (bind mount from host)
- Standard images target aarch64 (ARM64); the `cuda-*` images build from `cuda-base` with cross-GPU arch defaults (sm_89/sm_120/sm_121), including `cuda-vllm` (override its `TORCH_CUDA_ARCH_LIST` for a slimmer single-target build). The `make` GPU targets pass on any NVIDIA host (an `-nvidia` kernel, or `nvidia-smi`/`lspci` seeing a card), not just DGX Spark
- `TAINTED_BUILD` env var: `true` if built with `UNSAFE_SSL=true` (login warning displayed), `false` otherwise. Note: `UNSAFE_SSL` only relaxes verification *during* image construction — conda/git/npm config changes are reverted before the RUN ends, so SSL verification is restored at runtime.

## Vault (optional)

The `vault` script manages personal secrets as **SOPS + age** encrypted files stored in a separate
private git repo (`~/.local/share/hemlighet`, under `code-monkeys/personal/`) — one encrypted `.sops` file per
original file, binary mode, so everything round-trips byte-for-byte. This public repo never holds
secrets, plaintext or encrypted. It manages five items:

| Item | Type | Notes |
|---|---|---|
| `ssh/` | directory | top-level files only; `known_hosts*` excluded (runtime state) |
| `env` | file | loaded by `primate` via `--env-file` |
| `aws/` | directory | excludes `amazonq/`, `sso/`, `cli/` |
| `face` | file | |
| `gitconfig` | file | |

The plaintext files are gitignored here; the encrypted copies live in hemlighet and travel via git.

```bash
./vault unlock [item...]   # decrypt from the hemlighet clone into the working tree (--force to overwrite)
./vault lock   [item...]   # encrypt into the hemlighet clone and remove plaintext (--keep to leave it)
./vault lock --push        # ...and commit + push hemlighet in one go (otherwise it prints how)
./vault status             # per-item state + hemlighet git state (--local skips the fetch)
./vault rekey              # re-wrap data keys after editing recipients in hemlighet's .sops.yaml
```

Once unlocked, `setup` symlinks `ssh` → `~/.ssh`, `aws` → `~/.aws`, and `gitconfig` → `~/.gitconfig`.

The clone location resolves as `VAULT_HEMLIGHET`, then `${XDG_DATA_HOME:-~/.local/share}/hemlighet`,
then a legacy `~/hemlighet` if one still exists — so older machines keep working until you move
theirs with `mv ~/hemlighet ~/.local/share/hemlighet`.

Encryption runs containerized via the `nyckel` primate (age + sops; pulled from ECR on demand) — no
host installs. `bin/{sops,age,age-keygen}` are matching shims for ad-hoc use. Machine-to-machine
sync is just git: `lock --push` on one box, then pull + `unlock` on another. A machine can only
decrypt if its age key is a recipient — to add one, append its pubkey to the
`code-monkeys/personal/.*` rule in hemlighet's `.sops.yaml`, run `./vault rekey` on a machine that
can already decrypt, then commit + push hemlighet.

### Creating the vault from scratch

1. Create `ssh/`, `aws/`, and/or `env` with your credentials
2. Clone your secrets repo to `~/.local/share/hemlighet` and give it a `.sops.yaml` rule for `code-monkeys/personal/.*`
3. Run `./vault lock --push` to encrypt and publish (or `./vault lock`, then commit + push hemlighet yourself)

## Repository Layout

```
.
├── setup                  # host machine setup script (symlinks dotfiles into $HOME)
├── vault                  # secrets manager (SOPS + age via the nyckel primate; store = ~/.local/share/hemlighet)
├── bin/                   # host shim scripts symlinked into ~/.local/bin/
│   ├── primate-pull       # THE ECR pull — ensures <image>:latest is local; used by every shim,
│   │                      #   by vault, and by primate() in zfuncs
│   ├── aws                # local-first AWS CLI wrapper (falls back to minion container)
│   ├── spark-bench        # runs an eval harness in the spark-bench primate (see 007/skills/spark-bench/)
│   └── sops, age, age-keygen  # shims running the tools in the nyckel primate
├── codemonkey.dockerfile  # base Docker image (debian:13-slim)
├── docker-shim            # /usr/local/bin/docker in every image — sudo -n fallback if the socket is denied
├── hostpath               # /usr/local/bin/hostpath — translates a container path to its daemon-host path
├── primates/              # specialized Docker images built on codemonkey
│   ├── Makefile
│   ├── upgrade-home.sh    # the one home-volume dotfile sync (used by both primate-upgrade and make *.upgrade)
│   └── *.dockerfile
├── 007/                   # agent skills library (installed by setup via `make -C 007/skills install`)
│   ├── Makefile           # `make test` runs the skill test suite
│   └── skills/            # one directory per skill (SKILL.md + scripts/assets/references)
├── zshrc.template         # zsh config for containers (sources zbase)
├── zbase                  # main zsh config (oh-my-zsh, plugins, PATH)
├── zaliases               # shell aliases
├── zfuncs                 # shell functions (primate launcher, utilities)
├── zprofile               # zsh profile
├── tmux.conf              # tmux config (-> ~/.tmux.conf by setup; baked into images; used by primate-session)
├── gitconfig              # global git config (gitignored, vault-managed)
├── gitignore              # global gitignore
├── vimrc                  # vim config
├── toprc                  # top config
├── hooks/                 # git hooks (installed by setup)
│   └── pre-commit         # warns if vault is stale, or if stored credentials are >30 days old
├── jjh.zsh-theme          # custom zsh prompt theme (based on ys, adds conda env)
├── claude/                # Claude Code settings, global memory + custom commands
│   ├── settings.json
│   ├── CLAUDE.md          # global user memory (copied to ~/.claude/CLAUDE.md in the claude primate)
│   └── commands/
├── fastfetch/             # fastfetch config
├── Library/               # macOS-only assets
│   └── KeyBindings/       # custom key bindings (installed to ~/Library/KeyBindings)
└── spark/                 # DGX Spark cluster ops
    └── cluster/           # vLLM replica cluster (compose + scripts + docs)
```

## Spark cluster

`spark/cluster/` runs a vLLM replica cluster that consumes the `cuda-vllm` primate, fronted by a model-aware **LiteLLM** router. Hosts and roles come from a gitignored `cluster.env` (copy `cluster.env.example` and edit), so the same scripts work for any set of SSH-reachable GPU boxes plus an LB host. The maintainer's current deployment is one DGX Spark replica (`hutch.tworivers`) with the router on the control plane (`minerva.tworivers:8888`); `starsky` was repurposed out of the pool in June 2026. See `spark/cluster/README.md` and `spark/cluster/CLAUDE.md`.
