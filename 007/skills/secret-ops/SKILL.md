---
name: secret-ops
description: Decrypt/encrypt this project's SOPS+age secrets and manage the private hemlighet repo. Use whenever a task reads or changes a secret — sops, age, vault, hemlighet, a *.sops file, personal/* dotfiles. Crypto runs on the configured secret host over ssh, NOT inside a primate. Host/identity come from env or ~/.config/secret-ops.conf (never hardcoded here).
license: Apache-2.0
metadata:
  author: ooe
  version: "1.0.0"
---

# secret-ops

How secrets work in this project, so an agent working from inside a primate stops re-deriving it and
getting it wrong. **One rule: SOPS/age crypto runs on the configured *secret host*. You reach it over
ssh and run it there — the maintainer does not run these commands by hand.**

This skill hardcodes **no** hostnames, usernames, or paths — the public repo carries none. The real
values live in `~/.config/secret-ops.conf` (or env), which is private to each machine; see
`secret-ops.conf.example`.

## When to use

- Any task that reads or changes a secret: `sops`, `age`, `vault`, the `hemlighet` repo, a `*.sops`
  file, `personal/*` dotfiles, an encrypted service config.
- Symptoms that lead here: "decrypt X", "add this key/value to the encrypted config", "rotate/rekey",
  an API/MCP `401` that needs a credential added, "the secret is stale on machine Y".

## The hard rules (where agents keep getting stuck — don't)

1. **Crypto is host-side.** `age`/`sops` are never installed on a host; they run in the `nyckel`
   container via the `bin/sops` / `vault` shims, which need the age key at
   `~/.config/sops/age/keys.txt`. `primate()` mounts the host's `~/.ssh` and `~/.aws` into a primate
   but **not** `~/.config/sops/age`, and `bin/sops` bind-mounts the repo at its literal path, which
   Docker Desktop won't share from a primate. **So sops/vault cannot run inside a primate.**
2. **Reach the secret host over ssh and run it there.** The host, user, and clone paths come from
   config (below). It holds the age key, the hemlighet clone, the shims, and the push creds.
   **hemlighet edits originate on that host and are pushed; other machines only pull** — don't try to
   encrypt on a machine whose clone is read-only / lacks push creds.
3. **Non-login ssh drops PATH.** `ssh host 'sops …'` gets only `/usr/bin:/bin:/usr/sbin:/sbin`, so
   docker and the shims come back "command not found". Prepend `/usr/local/bin` and `~/.local/bin`.
   `scripts/secret-host.sh` does this for you — route every host command through it.
4. **To encrypt, use `vault`. Never hand-roll `sops -e`.** `vault` is the one encryptor and it owns
   the three things that are easy to get wrong: `*.sops` files are **binary mode** (`sops -e file.json`
   plain writes a structured-JSON sops the fleet's `-d` can't read); recipients come from `.sops.yaml`
   matched against the *decrypted* path (vault uses `--filename-override`, so no copying plaintext
   around); and the commit is **pathspec-scoped** so unrelated staged changes aren't swept in. A
   hand-rolled `sops -e … > file.sops` gets all three wrong.
5. **vault's two scopes.** `vault unlock` / `lock` / `status` / `rekey` manage the `personal/*`
   dotfiles (ssh/, aws/, env, …). `vault seal <src> <dest.sops> [--push] [-m MSG]` encrypts **any
   other** file into the clone (e.g. a service config). `.sops.yaml` at the hemlighet root holds the
   per-path recipient lists. Reading a `*.sops` back is just `sops -d --input-type binary
   --output-type binary <file>.sops` (via `secret-host.sh`).

## Configuration

The scripts read, in order: environment variables, then `${SECRET_OPS_CONF:-~/.config/secret-ops.conf}`
if present. Nothing is baked into the repo. Copy `secret-ops.conf.example` to `~/.config/secret-ops.conf`
and fill it in (that file is private — never commit it):

```
SECRET_HOST=<the host where sops/age + the hemlighet clone + push creds live>
SECRET_USER=<ssh user on that host>
HEMLIGHET_DIR=$HOME/.local/share/hemlighet   # optional; this is the published default
CHECKOUT_DIR=<path to the code-monkeys checkout on that host>   # optional
```

## Script

### `scripts/secret-host.sh` — run a host command with a sane PATH
```
secret-host.sh 'sops -d --input-type binary --output-type binary <area>/config.json.sops'   # read
secret-host.sh --cwd "$CHECKOUT_DIR" './vault seal <src> <area>/config.json.sops --push -m "msg"'  # write
```
ssh's to `$SECRET_USER@$SECRET_HOST`, prepends `/usr/local/bin:~/.local/bin` to PATH, and runs in the
hemlighet clone by default (`--cwd` to change). Errors with guidance if the config is missing. This is
the skill's only script — the encryptor lives in `vault` (see rule 4), reached through here; the skill
does not hand-roll `sops`.

## Typical flow (generic)

1. **Read:** `secret-host.sh 'sops -d --input-type binary --output-type binary <area>/config.json.sops'`.
2. **Edit** the decrypted working copy of the config (wherever your workflow keeps it, on the host).
3. **Encrypt + publish:** `secret-host.sh --cwd "$CHECKOUT_DIR" './vault seal <plaintext> <area>/config.json.sops --push -m "describe the change"'`.
4. Other machines pick it up on their next pull / config sync.

## See also

- Bind mounts from inside a primate resolve on the daemon host — wrap workspace paths in
  `$(hostpath …)` or they come up empty/denied. That is also *why* `bin/sops` cannot run in a primate.
