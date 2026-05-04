# code-monkeys

Dotfiles, shell configuration, and the **primates** containerized development environment system.

## Quick Start

```bash
git clone <repo-url> && cd code-monkeys
./setup
cd primates
make all
```

This gives you a working shell environment and Docker images. To pull in secrets from a previous setup:

```bash
export VAULT_BUCKET=my-vault-bucket   # required
export VAULT_PROFILE=my-aws-profile   # optional
./vault sync pull
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
- Symlinks `gitconfig` (if present), `gitignore`, `vimrc`, `toprc`, `zaliases`, `zbase`, `zfuncs`, `zprofile` as dotfiles in `$HOME`
- Symlinks `ssh` and `aws` if present (created by `vault unlock`)
- Symlinks `fastfetch` into `~/.config/`, `jjh.zsh-theme` into `~/.oh-my-zsh/custom/themes/`, and `claude` into `~/.claude`
- Symlinks each script in `bin/` individually into `~/.local/bin/` (creates the directory if missing — files from other installers are left alone)
- Installs `zbase` as `~/.zshrc` (copy, not symlink)
- Clones oh-my-zsh plugins: `zsh-autosuggestions`, `zsh-completions`, `zsh-syntax-highlighting`
- Installs git hooks from `hooks/` into `.git/hooks/`
- On macOS: installs custom key bindings to `~/Library/KeyBindings`
- Warns (non-fatal) if optional tools `aws` or `fastfetch` are not installed (the `bin/aws` shim covers a missing AWS CLI by running it in the `minion` container)

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
                             │            → kiro
                             → embedded
                             → lamp
                             → huggingface
                             → minion

nvidia/cuda:13.1.1 → llama-cpp-spark  (multi-stage: full/light/server)
                   → comfy-ui-spark
```

| Image | Purpose |
|---|---|
| **codemonkey** | Base image — Debian 13, zsh, oh-my-zsh, git, vim, build-essential, cmake, python3, nodejs, nmap, clamav, AWS CLI v2 |
| **miniforge3** | Adds Miniforge3 (conda for aarch64 and x86_64), creates `miniforge3-env` |
| **claude** | Adds Claude Code via native installer, creates `claude-env` |
| **opencode** | Adds npm and opencode-ai, creates `opencode-env` |
| **kiro** | Adds Amazon Kiro CLI via native installer, creates `kiro-env` |
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
make all UNSAFE_SSL=true    # disable SSL verification during build (tainted build)
make all FRESH=false        # skip freshclam (faster codemonkey build)
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
- `TAINTED_BUILD` env var: `true` if built with `UNSAFE_SSL=true` (login warning displayed), `false` otherwise. Note: `UNSAFE_SSL` only relaxes verification *during* image construction — conda/git/npm config changes are reverted before the RUN ends, so SSL verification is restored at runtime.

## Vault (optional)

The `vault` script encrypts secrets at rest using AES-256-CBC with PBKDF2. It manages five items:

| Source | Encrypted to | Type |
|---|---|---|
| `ssh/` | `.ssh.vault` | directory |
| `env` | `.env.vault` | file |
| `aws/` | `.aws.vault` | directory |
| `face` | `.face.vault` | file |
| `gitconfig` | `.gitconfig.vault` | file |

Both the plaintext files and the encrypted `.vault` files are gitignored.

```bash
./vault unlock       # decrypt all vaults (prompts for password)
./vault lock         # encrypt all vaults and remove plaintext
./vault rekey        # re-encrypt with a new password
./vault status       # show per-vault lock/unlock + S3 sync state inline
```

Once unlocked, `setup` symlinks `ssh` → `~/.ssh`, `aws` → `~/.aws`, and `gitconfig` → `~/.gitconfig`. The `env` file is loaded by `primate` via `--env-file`.

### Syncing vault files with S3

Vault files can be backed up and shared across machines using an S3 bucket. Set the `VAULT_BUCKET` environment variable (e.g., in your `env` file or shell profile):

```bash
export VAULT_BUCKET=my-vault-bucket
export VAULT_PROFILE=my-aws-profile  # optional, defaults to 'default'
```

Then use `vault sync`:

```bash
./vault sync push          # upload vault files to S3
./vault sync pull          # download vault files from S3 (skip files where local is same/newer)
./vault sync pull --force  # delete local *.vault files and re-download (prompts for confirmation)
```

Uses `aws s3 sync` under the hood — only transfers files that have changed. Requires credentials with read/write access to the bucket. The AWS CLI itself is optional: `vault` prepends the repo's `bin/` to `PATH`, so `bin/aws` (a local-first shim that falls back to running `aws` inside the `minion` container) handles invocations on hosts where the CLI isn't installed.

`vault status` queries S3 (one `aws s3 sync --dryrun` call per direction) and folds the remote state into the per-vault status line, e.g. `aws       UNLOCKED (up to date, s3 LOCAL NEWER — run 'vault sync push')`. Use `--force` on pull when you trust S3 over local — typical case: machine A pushed, machine B was idle, you want machine B to take S3's copy regardless of local mtimes.

### Creating vaults from scratch

1. Create `ssh/`, `aws/`, and/or `env` with your credentials
2. Run `./vault lock` to encrypt them (you'll set a password)
3. Run `./vault sync push` to back them up to S3 (optional)

## Repository Layout

```
.
├── setup                  # host machine setup script (symlinks dotfiles into $HOME)
├── vault                  # encrypt/decrypt secrets at rest
├── bin/                   # host shim scripts symlinked into ~/.local/bin/
│   └── aws                # local-first AWS CLI wrapper (falls back to minion container)
├── codemonkey.dockerfile  # base Docker image (debian:13-slim)
├── primates/              # specialized Docker images built on codemonkey
│   ├── Makefile
│   └── *.dockerfile
├── zshrc.template         # zsh config for containers (sources zbase)
├── zbase                  # main zsh config (oh-my-zsh, plugins, PATH)
├── zaliases               # shell aliases
├── zfuncs                 # shell functions (primate launcher, utilities)
├── zprofile               # zsh profile
├── gitconfig              # global git config (gitignored, managed via vault sync)
├── gitignore              # global gitignore
├── vimrc                  # vim config
├── toprc                  # top config
├── hooks/                 # git hooks (installed by setup)
│   └── pre-commit         # warns if vault is stale
├── jjh.zsh-theme          # custom zsh prompt theme (based on ys, adds conda env)
├── claude/                # Claude Code settings + custom commands
│   ├── settings.json
│   └── commands/
├── fastfetch/             # fastfetch config
└── Library/                # macOS-only assets
    └── KeyBindings/        # custom key bindings (installed to ~/Library/KeyBindings)
```
