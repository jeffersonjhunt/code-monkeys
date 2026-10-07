# Changelog — secret-ops

## [1.0.0] - 2026-10-07

- Initial secret-ops skill: documents the host-vs-primate SOPS/age boundary (crypto runs on the
  configured secret host over ssh, never inside a primate), reached via `scripts/secret-host.sh`
  (ssh with a login-grade PATH). Host/identity come from env or `~/.config/secret-ops.conf`; the
  public repo carries no fleet identifiers (only `secret-ops.conf.example`).
- Encryption is delegated to `vault seal` (added to the repo's `vault` in the same change), not a
  parallel `sops -e` — so binary mode, `.sops.yaml` recipient matching, and pathspec-scoped commits
  all have one implementation.
