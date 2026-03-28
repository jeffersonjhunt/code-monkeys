# code-monkeys

Dotfiles, shell configuration, and the **primates** containerized development environment system.

## Quick Start

```bash
git clone <repo-url> && cd code-monkeys
./setup
cd primates
make all
```

This gives you a working shell environment and Docker images — no secrets required. If you have encrypted vault files from a private repo, see [Vault](#vault) below.

## Setup

The `setup` script symlinks dotfiles from this repo into `$HOME`:

```bash
./setup              # install symlinks, clone oh-my-zsh plugins
./setup --dry-run    # preview without making changes
./setup --uninstall  # remove symlinks and cloned repos
```

What it does:
- Symlinks `gitconfig`, `gitignore`, `vimrc`, `toprc`, `zaliases`, `zbase`, `zfuncs`, `zprofile` as dotfiles in `$HOME`
- Symlinks `ssh` and `aws` if present (created by `vault unlock`)
- Symlinks `fastfetch` into `~/.config/`, `jjh.zsh-theme` into `~/.oh-my-zsh/custom/themes/`, and `claude` into `~/.claude`
- Installs `zbase` as `~/.zshrc` (copy, not symlink)
- Clones oh-my-zsh plugins: `zsh-autosuggestions`, `zsh-completions`, `zsh-syntax-highlighting`
- Installs git hooks from `hooks/` into `.git/hooks/`
- On macOS: installs custom key bindings to `~/Library/KeyBindings`

## Shell Configuration

The shell config is layered:

1. **`zshrc.template`** — installed as `~/.zshrc` inside containers; sources `~/.zbase`, fixes ownership of mounted directories, activates the image's conda environment if present
2. **`zbase`** — main config: oh-my-zsh setup, plugins, PATH, editor, history settings
3. **`zaliases`** — aliases (`dps`, `dpi`, `probe`, `ocd`, `git.all`, etc.)
4. **`zfuncs`** — functions: `primate()`, `primate-upgrade()`, `which-os()`, `code-here()`, `tree()`, `clamscan()`, `tad()`, `watch()`

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
- Mounts `~/.ssh` and `~/.aws` into the container if present
- Mounts the current directory as `/home/codemonkey/workspace`
- Loads environment variables from the `env` file if present
- Auto-publishes any exposed ports
- Enables `--gpus all` on NVIDIA kernel hosts
- Runs as user `codemonkey` with zsh

### Upgrading

After updating dotfiles or the zsh theme, use `primate-upgrade` or the Makefile to update existing home volumes without destroying them:

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
- Standard images target aarch64 (ARM64); CUDA images target sm_121

## Vault (optional)

The `vault` script encrypts secrets at rest using AES-256-CBC with PBKDF2. It manages three items:

| Source | Encrypted to | Type |
|---|---|---|
| `ssh/` | `.ssh.vault` | directory |
| `env` | `.env.vault` | file |
| `aws/` | `.aws.vault` | directory |

The plaintext files are gitignored. The encrypted vault files are not included in this repo — they live in a separate private repo (see below).

```bash
./vault unlock       # decrypt all vaults (prompts for password)
./vault lock         # encrypt all vaults and remove plaintext
./vault rekey        # re-encrypt with a new password
./vault status       # show lock/unlock state
```

Once unlocked, `setup` symlinks `ssh` → `~/.ssh` and `aws` → `~/.aws`. The `env` file is loaded by `primate` via `--env-file`.

To create your own vaults from scratch:

1. Create `ssh/`, `aws/`, and/or `env` with your credentials
2. Run `./vault lock` to encrypt them (you'll set a password)
3. The `.vault` files are ready to store in a private repo

## Private Repo (optional)

To keep your vault files in version control without publishing them, use a two-repo setup: this public repo for code, and a private repo for secrets.

### Initial setup

1. Create a private repo (GitHub, CodeCommit, GitLab, etc.)
2. Add it as a remote:

```bash
git remote add private <private-repo-url>
```

3. Push your vault files to the private repo:

```bash
git checkout --orphan private
git reset
# create a .gitignore that ignores everything except vault files:
#   *
#   !.gitignore
#   !.ssh.vault
#   !.env.vault
#   !.aws.vault
git add .gitignore .ssh.vault .env.vault .aws.vault
git commit -m "initial vault files"
git push private private:master
git checkout master
```

### Cloning on a new machine

```bash
git clone <public-repo-url> && cd code-monkeys
git remote add private <private-repo-url>
git fetch private
git restore --source private/master -- .ssh.vault .env.vault .aws.vault
git reset HEAD .ssh.vault .env.vault .aws.vault
./vault unlock
./setup
```

### Updating vault files

After changing secrets (`./vault lock`), push to the private remote:

```bash
git checkout private
git add .ssh.vault .env.vault .aws.vault
git commit -m "update vaults"
git push private private:master
git checkout master
```

## Repository Layout

```
.
├── setup                  # host machine setup script (symlinks dotfiles into $HOME)
├── vault                  # encrypt/decrypt secrets at rest
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
├── claude/                # Claude Code settings + custom commands
│   ├── settings.json
│   └── commands/
└── fastfetch/             # fastfetch config
```
