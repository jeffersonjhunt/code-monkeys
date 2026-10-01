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
3. **A dedicated signing keychain** — verified on a build Mac (below). The way to sign with a
   real identity, and to provision, unattended over SSH.

## A signing keychain for SSH

Verified on mighty-mouse (macOS 27, Xcode 27), 2026-09/10. A keychain of its own, holding only the
signing identity, with a password the Mac can read from a file — so an SSH session unlocks it
without your login password — plus an App Store Connect API key in place of the Apple ID in Xcode
(also unusable over SSH: builds fail "No Accounts").

1. **Keychain** (once, on the Mac; the password goes in a 600 file and in your secrets vault):
   ```bash
   KC=/Users/me/Library/Keychains/signing.keychain-db
   PW=/Users/me/.config/appstoreconnect/keychain-pass           # chmod 600, a random password
   security create-keychain -p "$(cat $PW)" $KC
   security set-keychain-settings $KC                            # no auto-lock
   security list-keychains -d user -s $KC $(security list-keychains -d user | xargs)
   ```
2. **Identity, without a GUI export:** make the key and a CSR on the Mac
   (`openssl req -new -newkey rsa:2048 -nodes …`), upload the CSR at developer.apple.com ▸
   Certificates ▸ + ▸ Apple Development, then combine key + downloaded `.cer` into a `.p12` and
   `security import … -k $KC -T /usr/bin/codesign`; delete the loose key.
3. **Open the key to codesign** — without this every signature fails `errSecInternalComponent`:
   `security set-key-partition-list -S apple-tool:,apple:,codesign: -s -k "$(cat $PW)" $KC`
4. **Apple's WWDR G3 intermediate.** A fresh Mac may hold only the expired 2023 one ("unable to
   build chain to self-signed root"): fetch `https://www.apple.com/certificateauthority/AppleWWDRCAG3.cer`,
   check it chains to Apple Root CA (`openssl verify -CAfile <system roots> g3.pem`), import it into $KC.
5. **API key:** App Store Connect ▸ Users and Access ▸ Integrations ▸ Team Keys, role Admin;
   the `.p8` (downloadable once) beside the password file, 600.
6. **`api.env`** — `$HOME/.config/appstoreconnect/api.env` on the Mac (or `ASC_ENV=`), make syntax,
   read by this skill and by project Makefiles alike:
   ```make
   ASC_KEY_ID=XXXXXXXXXX
   ASC_ISSUER_ID=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
   ASC_KEY_PATH=/Users/me/.config/appstoreconnect/AuthKey_XXXXXXXXXX.p8
   SIGNING_KEYCHAIN=/Users/me/Library/Keychains/signing.keychain-db
   SIGNING_KEYCHAIN_PASS_FILE=/Users/me/.config/appstoreconnect/keychain-pass
   ```

With it, identity- and team-signed `xc-build`/`xc-test` runs unlock the keychain **in the same
remote session** as `xcodebuild` (the Mac reads its own password file; nothing secret crosses the
SSH link), sign with `OTHER_CODE_SIGN_FLAGS=--keychain …`, and provision with the API key.
`xc-doctor`'s `codesign` check signs a probe exactly that way. A locked keychain still refuses to
sign, as it should.

The first team-signed run after ad-hoc ones makes macOS 27 ask, on the Mac's screen, whether to
open "“…-Runner” (and the app) — "differs from previously opened versions". Click **Open Anyway**
once; then keep signing the same way (stop passing `--adhoc` on that Mac), or it asks again. Since 1.3.1
`xc-build`/`xc-test` refuse to change a Mac app's signer unless given `--allow-signer-change`, and
`xc-doctor` warns about differently signed copies (e.g. a TestFlight install) on the build Mac.

## Screen Recording for SSH (macOS screenshots)

`xc-shot --platform macos` needs the Screen Recording (TCC) grant — not for the app, but for the
process that owns SSH sessions, `/usr/libexec/sshd-keygen-wrapper`. Grant it once under System
Settings ▸ Privacy & Security ▸ Screen & System Audio Recording. `xc-doctor` checks it with
`CGPreflightScreenCaptureAccess()` from inside an SSH session, which is exactly the process that
will capture. The grant covers every SSH session to that account, so give it only on a Mac you
control.

## Grants this skill does NOT need

- **Accessibility** (macOS 27: System Settings ▸ Privacy & Security ▸ *Device Control & Data
  Access*). Not needed for UI tests — `click()` works without it; granting it to
  `sshd-keygen-wrapper` would let any SSH session control the Mac. Verified by removing it: the
  macOS UI tests still passed.

Code started over SSH runs in a command-line session, not the logged-in GUI (Aqua) session; with
a user logged in on the Mac, `xcodebuild` from SSH works for all test kinds (Apple DTS). If that
ever stops being true, start the run in the GUI session instead (`launchctl bootstrap gui/<uid>`
a one-off LaunchAgent) rather than granting more permissions.

## Resetting a macOS app's state

```bash
tccutil reset All com.bundle.id
defaults delete com.bundle.id
rm -rf ~/Library/Saved\ Application\ State/com.bundle.id.savedState
```
