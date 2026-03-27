# dotfiles + primates

Personal development environment: dotfiles, shell configuration, and the **primates** containerized dev environment system.

## Quick Start

```bash
# clone and set up dotfiles
git clone <repo-url> && cd <repo>
./setup

# unlock secrets (one-time, requires vault password)
./vault unlock

# build container images
cd primates
make all
```

## Repository Layout

```
.
├── setup                  # host machine setup script (symlinks dotfiles into $HOME)
├── vault                  # encrypt/decrypt secrets at rest
├── .ssh.vault             # encrypted SSH keys (committed)
├── .env.vault             # encrypted environment variables (committed)
├── codemonkey.dockerfile  # base Docker image (debian:13-slim)
├── primates/              # specialized Docker images built on codemonkey
│   ├── Makefile
│   └── *.dockerfile
├── zshrc.template         # zsh config for containers (sources zbase)
├── zbase                  # main zsh config (oh-my-zsh, plugins, PATH)
├── zaliases               # shell aliases
├── zfuncs                 # shell functions (primate launcher, utilities)
├── zprofile               # zsh profile
├── gitconfig              # global git config
├── gitignore              # global gitignore
├── vimrc                  # vim config
├── toprc                  # top config
├── hooks/                 # git hooks (installed by setup)
│   └── pre-commit         # warns if vault is stale
├── jjh.zsh-theme          # custom zsh prompt theme (based on ys, adds conda env)
├── ssh/                   # SSH keys (plaintext, gitignored — unlocked from vault)
├── env                    # environment variables (plaintext, gitignored — unlocked from vault)
├── aws/                   # AWS CLI config + credentials (plaintext, gitignored — unlocked from vault)
├── claude/                # Claude Code settings + custom commands (symlinked to ~/.claude)
│   ├── settings.json
│   └── commands/
└── fastfetch/             # fastfetch config
```

## Setup

The `setup` script symlinks dotfiles from this repo into `$HOME`:

```bash
./setup              # install symlinks, clone oh-my-zsh plugins
./setup --dry-run    # preview without making changes
./setup --uninstall  # remove symlinks and cloned repos
```

What it does:
- Symlinks `ssh`, `aws`, `gitconfig`, `gitignore`, `vimrc`, `toprc`, `zaliases`, `zbase`, `zfuncs`, `zprofile` as dotfiles in `$HOME`
- Symlinks `fastfetch` into `~/.config/`, `jjh.zsh-theme` into `~/.oh-my-zsh/custom/themes/`, and `claude` into `~/.claude`
- Installs `zbase` as `~/.zshrc` (copy, not symlink)
- Clones oh-my-zsh plugins: `zsh-autosuggestions`, `zsh-completions`, `zsh-syntax-highlighting`
- Installs git hooks from `hooks/` into `.git/hooks/` (pre-commit: warns if vault is stale)
- On macOS: installs custom key bindings to `~/Library/KeyBindings`

## Vault

Secrets (`ssh/`, `env`, and `aws/`) are encrypted at rest using AES-256-CBC with PBKDF2. The plaintext files are gitignored; only the encrypted `.ssh.vault`, `.env.vault`, and `.aws.vault` files are committed.

```bash
./vault unlock       # decrypt all vaults (prompts for password)
./vault lock         # encrypt all vaults and remove plaintext
./vault rekey        # re-encrypt with a new password
./vault status       # show lock/unlock state
```

The `setup` script symlinks `ssh` → `~/.ssh` and `aws` → `~/.aws`. Once unlocked, SSH keys and AWS credentials are available to the host and any containers that mount those directories. The `env` file is loaded by `primate` via `--env-file`.

## Primates

Primates are purpose-built Docker images for different development domains. They all share the `codemonkey` base image and a common shell environment.

### Image Hierarchy

```
debian:13-slim → codemonkey → miniforge3 → claude
                             │            → opencode
                             → embedded
                             → lamp
                             → huggingface
                             → minion

nvidia/cuda:13.1.1 → llama-cpp-spark  (multi-stage: full/light/server)
                   → comfy-ui-spark
```

| Image | Purpose |
|---|---|
| **codemonkey** | Base image — Debian 13, zsh, oh-my-zsh, git, vim, build-essential, cmake, python3, nmap, clamav |
| **miniforge3** | Adds Miniforge3 (conda for aarch64 and x86_64), creates `miniforge3-env` |
| **claude** | Adds Claude Code via native installer, creates `claude-env` |
| **opencode** | Adds npm and opencode-ai, creates `opencode-env` |
| **embedded** | Adds libfmt, libboost, cc65, vasm 6502 assembler |
| **lamp** | Adds Apache, MariaDB, PHP |
| **huggingface** | Adds python3 venv and huggingface-cli |
| **minion** | Bare codemonkey extension (general-purpose runner) |
| **llama-cpp-spark** | llama.cpp for NVIDIA DGX Spark (sm_121 Blackwell GPUs) |
| **comfy-ui-spark** | ComfyUI for NVIDIA DGX Spark (sm_121 Blackwell GPUs) |

### Building

```bash
cd primates
make help                   # show all targets
make all                    # build codemonkey + all standard images
make spark                  # build all + GPU images (requires NVIDIA kernel)
make claude.build           # build a single image
make all FORCE=1            # rebuild from scratch (--no-cache)
make clean                  # remove all images
```

### Launching

The `primate` shell function (defined in `zfuncs`) launches containers:

```bash
primate claude              # start claude image with workspace mount
primate embedded --no-workspace  # start without mounting current directory
```

What `primate` does:
- Creates a persistent Docker volume `<image>-home` for the home directory
- Mounts `~/.ssh` and `~/.aws` into the container (read from host)
- Mounts the current directory as `/home/codemonkey/workspace`
- Loads environment variables from the `env` file
- Auto-publishes any exposed ports
- Enables `--gpus all` on NVIDIA kernel hosts
- Runs as user `codemonkey` with zsh

### Container Conventions

- User: `codemonkey` (UID/GID 1000), has passwordless sudo
- Shell: zsh with oh-my-zsh (jjh theme — based on ys, adds conda env display)
- Home: `/home/codemonkey` (persisted via named Docker volume)
- Workspace: `/home/codemonkey/workspace` (bind mount from host)
- Standard images target aarch64 (ARM64); CUDA images target sm_121

## Shell Configuration

The shell config is layered:

1. **`zshrc.template`** — installed as `~/.zshrc` inside containers; sources `~/.zbase`, fixes ownership of mounted directories, activates the image's conda environment if present
2. **`zbase`** — main config: oh-my-zsh setup, plugins, PATH, editor, history settings
3. **`zaliases`** — aliases (`dps`, `dpi`, `probe`, `ocd`, `git.all`, etc.)
4. **`zfuncs`** — functions: `primate()`, `which-os()`, `code-here()`, `tree()`, `clamscan()`, `tad()`, `watch()`
