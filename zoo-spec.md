# zoo — specification

A manager for primates: `top(1)`, but for the containers `primate` and `primate-session`
start.

This document states **requirements, constraints and evidence**. It deliberately does not
prescribe an architecture. A previous implementation exists on the `zoo-legacy-ref` branch
(and a dead-end follow-up on `feat/zoo-stream`); both were abandoned. Read them for
evidence if useful, not for design.

Every number and claim below was measured, not assumed. Where something is untested, it
says so.

---

## 1. What it must do

- List every container started by `primate` or `primate-session`, running or stopped.
- For each: kind (foreground primate vs detached session), name, image, status, and live
  CPU / memory / process count.
- Stopped sessions must be listed — they still hold an `<image>-home` volume and are still
  resumable.
- Act on a selected container: kill it, re-attach to a session, open a shell in it.
- Launch a new primate or session, choosing from the image roster.
- Be usable in a terminal a person is sitting at, and leave that terminal exactly as it
  was found.

## 2. Hard constraints

Each of these was learned the expensive way. They are not preferences.

### 2.1 Launch and attach must go through the zsh functions

`primate()`, `primate-session()` and `primate-session-resume()` are **zsh functions** in
`zfuncs`. They own the workspace mount, the `$HOME` refusal, the docker socket gid, the
`<image>-home` volume, and the first-run config sync that puts real (gitignored,
vault-managed) configs into a fresh volume.

Anything that launches or attaches must therefore either **be** a zsh shell, or invoke one.
Reimplementing that logic is not an option: duplicated launch logic in this repo has
already caused a production failure (five hand-copied copies of the ECR pull, two of which
were missing, producing `pull access denied … may require 'docker login'` on a pruned host).

This constraint is what makes a compiled binary or a containerised process awkward. If a
future design wants one, the honest fix is to extract that logic into something both a
shell and a program can call — that is real work, not a detail.

### 2.2 Containers must be identified by label, never by image name

Containers carry `primate.managed` and `primate.image`; sessions additionally carry
`primate.session` and `primate.name`. **These labels already exist in `zfuncs` today** —
they are the only part of the previous implementation that was kept.

Matching container *images* against the dockerfile roster is wrong, and measurably
dangerous: `intel-nuc.tworivers` holds six `spark-bench:latest` containers from real eval
runs, and `spark-bench` **is** in the roster. Name-matching selects 7 of 8 containers there;
label-matching selects 1. Those six would each have been one keystroke from a kill.

Sessions started before `primate.managed` existed carry only `primate.session`. Docker ANDs
repeated `--filter label=`, so no single filter selects both sets.

### 2.3 The self-container guard must compare a prefix

A process must refuse to kill or exec into the container it is itself running in.

`docker ps` reports a **12-character** id; the container's own id (from
`/proc/self/mountinfo` — `/proc/self/cgroup` is empty under cgroup v2 in Docker Desktop's
VM) is **64 characters**. An equality comparison never matches, so the guard looks present
in the source while doing nothing.

An **empty** id is also a prefix of every id, so an unparsed row must be rejected before the
comparison, not fed into it.

**`/proc/self/mountinfo` is empty on a host.** On macOS and on any host shell, the guard is
inert — correct, and the branch every real invocation takes. Testing only from inside a
container exercises the other branch.

### 2.4 Session names are reusable; re-verify at the moment of action

`primate-session-kill` and `primate-session-resume` resolve by **name**. A confirmation
prompt can sit open indefinitely, so the row it names may be stale. Kill and recreate a
session under the same name while a prompt waits, and the action lands on the new container.
Verify the selected container id still belongs to that name immediately before acting.

### 2.5 Only one process may own the terminal

If two processes both set termios on the same tty — one rendering, one reading keys — they
contend. Whatever the design, exactly one must own the terminal at a time, and handing it
over (to `tmux`, to an interactive shell, to `docker exec -it`) must be explicit.

### 2.6 The user's shell follows the repo working tree

`~/.zfuncs` is a symlink into the repo. Whatever branch is checked out **is** the user's
live `primate`/`zoo`. Development must happen in a git worktree, or the maintainer's
everyday environment silently becomes whatever is being worked on. This already happened.

## 3. Measurements

Taken on Docker Desktop (macOS, arm64) and on `intel-nuc.tworivers` (native Linux, x86_64).

| | cost |
|---|---|
| `docker ps -a --filter label=… --format …` | **15–30 ms** |
| `docker stats --no-stream` | **~1.6 s** |
| Docker Engine API `/containers/{id}/stats?stream=false` | **~2.0 s** |
| `docker stats` **streamed** | first sample ~2 s, then a full set every **~500 ms** |

The ~2 s is the **daemon** waiting for the second sample it needs to compute CPU%. It is not
client overhead and no client avoids it — the API is not faster. Only streaming removes it.

Streamed `docker stats` emits terminal control (`\e[H`, `\e[K`, `\e[J`) **even when stdout is
not a tty**, so it cannot be parsed without stripping. The API returns JSON with
`precpu_stats` and `cpu_stats` in one response, and raw numeric fields (bytes, nanoseconds)
rather than pre-formatted `686MiB / 31.29GiB` — which matters for sorting or arithmetic.

`jq` is installed on **every** machine including the Mac. `zsh/curses` (`zmodload zsh/curses`)
is available on every machine including the Mac; `zcurses` supports `init`, `addwin`,
`refresh`, `attr`, colour, `timeout`, `input`, `resize`, and `end` → run a normal command →
`init` again. It does **not** name special keys: an arrow arrives as three raw reads
(`\e`, `[`, `A`) with the key-name parameter empty, so escape parsing stays manual.

## 4. Testing requirements

### 4.1 Job control exists only in a shell reading from a terminal

`zsh -c`, `zsh -i -c` and `zsh -i script.zsh` all report `monitor=off` and produce **no**
job-control messages. Feeding commands **through a pty** to `zsh -if` does produce them.

A suite without that is structurally blind to background-process noise, terminal-state
damage, and signal handling — the exact defects that reached the maintainer instead of the
tests. Any implementation must be tested in a shell with job control on.

### 4.2 Every assertion must be watched failing

Six assertions in the previous implementation passed while proving nothing. Every one was an
**absence** — "nothing was launched", "no refusal", "the name appears", "the footer appears" —
satisfied by the code doing nothing at all. None was found by inspection; all were found by
deliberately breaking the code and re-running.

Two specific traps, both of which caught the previous implementation more than once:

- **Terminal echo satisfies a marker.** If a test types `echo MARKER` into a shell, `MARKER`
  appears in the capture whether or not anything ran. The marker's *output* must differ from
  the text typed to produce it.
- **A string present in every frame proves nothing.** Counting a footer that appears on every
  render cannot distinguish "came back" from "never left". Order matters: assert the marker
  appears *after* the event.

### 4.3 Environment forks must both be covered

Testing the convenient side looks like full coverage. Concretely: `TERM` set vs unset
(`tput` emits nothing without a terminfo entry), inside a container vs on a host
(`/proc/self/mountinfo`), macOS daemon vs native Linux, and a shell with job control vs
without.

Tests must not depend on ambient state — an image happening to be local, a roster on disk,
`TERM` happening to be set. All three caused a suite to pass on one machine and fail on
another for reasons unrelated to the code.

### 4.4 Session tests are opt-in

Tests that create or attach to primate sessions must be explicitly enabled and must skip
loudly otherwise. Running a suite must never start session containers on a machine where the
maintainer has live ones.

## 5. Non-goals

- Not a general docker UI. Non-primate containers are out of scope and must stay invisible.
- Not multi-host. One daemon.
- Not a process viewer *inside* a primate.
- Not a replacement for `primate-session-list`, which stays as the scriptable view.

## 6. Failure catalogue

Recorded so the same ground is not re-covered. From the abandoned implementation:

- A confirmed kill that killed nothing for three commits, because the branch referenced a
  variable removed in a refactor. Unit tests of the kill function passed throughout; the
  suite never pressed the confirm key.
- Five functions silently deleted by an edit that replaced a *range* between two markers
  without asserting what else the range contained. `zsh -n` passed; the display was fine;
  only the test suite noticed.
- "Flashes of processing" traced to roughly a dozen `fork`s per tick — including two
  subshells whose only purpose was deciding whether to print the letter `s`. `zsh/datetime`
  provides `$EPOCHSECONDS` and `strftime` with no fork.
- Terminal left in the alternate screen with the cursor hidden after ctrl-c, because zsh's
  `always` block does not run when the shell takes SIGINT.
- Line tails surviving a redraw, because `tput ed` clears to end of *screen* and nothing
  cleared each line.
- A list 23 lines tall on a 24-line terminal, scrolling the alternate screen so every
  subsequent cursor-home landed in the wrong place.
- A background sampler outliving the process that spawned it, printing
  `mv: rename …: No such file or directory` on the terminal after exit.
