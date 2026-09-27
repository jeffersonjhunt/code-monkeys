# Signing, the keychain over SSH, and TCC

## What xc-build signs with

| Platform | Signing |
|---|---|
| iOS Simulator | none needed (Xcode signs "to run locally") |
| iOS device | team required: `--team`, `TEAM_ID`, or `.devteam`; automatic signing + `-allowProvisioningUpdates` |
| macOS | `--adhoc` → ad-hoc. Else `.signid` → that identity, manual. Else a team → automatic. Else ad-hoc. |

`.signid` and `.devteam` are per-developer files at the project root and are gitignored.
This precedence comes from avatar's Makefile.

## Why a stable identity matters on macOS (TCC)

macOS remembers privacy grants (Microphone, Speech Recognition, Accessibility, Screen Recording…)
per **code signature**. An ad-hoc signature changes with every build, so every rebuild re-prompts.
For apps that need grants, sign with a stable identity:

- **No Apple account:** Keychain Access ▸ Certificate Assistant ▸ Create a Certificate…, type
  *Code Signing*, e.g. "MyApp Local". Then `security find-identity -v -p codesigning` and write the
  SHA-1 (or name) into `.signid`.
- **Apple developer account:** put the 10-character team ID in `.devteam`.

Apps that need no grants (e.g. a game) are fine ad-hoc.

## The SSH keychain problem

Signing with a real identity from an SSH session usually fails:

```
…/App.debug.dylib: errSecInternalComponent
Command CodeSign failed with a nonzero exit code
```

The certificate is found, but the login keychain's private key cannot be used from the SSH
session (it is not the GUI session that unlocked the keychain). `xc-doctor.py` detects this by
signing a throwaway binary with the identity the project would use.

Options:

1. **`xc-build.py --adhoc`** — verified. Right for iterating; TCC grants will not persist.
2. **Build that one on the Mac** (`make run` in avatar's case) when you need the stable identity.
3. **Unlock the keychain for the SSH session** — *unverified in this setup; try it*:
   `ssh -t <user>@host.docker.internal security unlock-keychain ~/Library/Keychains/login.keychain-db`
   (prompts for the Mac password), then build in the same session window. Never put the
   password in a script or env file.

## Screen Recording for SSH (macOS screenshots)

`xc-shot --platform macos` needs the Screen Recording (TCC) grant — not for the app, but for the
process that owns SSH sessions, `/usr/libexec/sshd-keygen-wrapper`. Grant it once under System
Settings ▸ Privacy & Security ▸ Screen & System Audio Recording. `xc-doctor` checks it with
`CGPreflightScreenCaptureAccess()` from inside an SSH session, which is exactly the process that
will capture. The grant covers every SSH session to that account, so give it only on a Mac you
control.

## Resetting a macOS app's state

```bash
tccutil reset All com.bundle.id
defaults delete com.bundle.id
rm -rf ~/Library/Saved\ Application\ State/com.bundle.id.savedState
```
