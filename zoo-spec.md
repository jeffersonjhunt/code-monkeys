# zoo — specification

`zoo` is an interactive manager for primates: the containers `primate` and
`primate-session` start. It shows what is running and lets the user act on it without
leaving the tool.

---

## 1. Terms

| term | meaning |
|---|---|
| **primate** | a foreground container from `primate <image>`. Tied to the terminal that started it; `--rm`, so it is gone when it exits. |
| **session** | a detached container from `primate-session <image> [name]`. PID 1 is `sleep infinity`; a `tmux` server runs inside it, so work survives disconnection. |
| **home volume** | `<image>-home`, the persistent `/home/codemonkey` for an image. Shared by every container of that image and outlives all of them. |
| **roster** | the available images: `codemonkey` plus every `primates/*.dockerfile`. |

---

## 2. Viewing

1. List every primate and every session on the local docker daemon.
2. List **stopped** sessions as well as running ones — they still hold a home volume and
   can still be resumed.
3. Show, per container: kind (primate or session), name, image, status, uptime, CPU
   percentage, memory used and total, and process count.
4. Show live figures, refreshed on an interval the user can set.
5. Indicate clearly when figures are unavailable or stale, distinguishably from a container
   that is genuinely idle.
6. Remain correct when the list is longer or wider than the terminal.

## 3. Lifecycle

7. **Start a primate** from an image chosen out of the roster.
8. **Start a session** from a chosen image, optionally naming it.
9. **Support multiple sessions per image**, each independently named, listed, selectable and
   actionable. `claude` may have `scratch`, `review` and `build` sessions at once.
10. **Stop a primate** — the container is removed.
11. **Stop a session** — the container is removed, **the home volume is preserved**.
12. **Reattach to a running session**, entering its `tmux`.
13. **Resume a stopped session** — start it, then attach.
14. **Open a shell** in any running container. This is a new shell, not the original
    terminal, and must be presented as such.
15. Return to `zoo` when an attached session or shell ends.

## 4. Interaction

16. Select a row; act on the selection.
17. Confirm before anything destructive, showing what will be destroyed and what will
    survive (for a session: that the home volume remains).
18. Offer only actions that exist. An advertised key that does nothing is worse than an
    absent one.
19. Provide help listing the keys.
20. Exit on the user's terminating keys, and restore the terminal exactly as found —
    including after an interrupt.
21. Print no stray output: no job-control notices, no messages from background work, no
    residue after exit.
22. Render without visible flicker or churn.

## 5. Safety

23. Act only on primates and sessions. Other containers on the daemon must be invisible and
    unreachable.
24. Never act on the container `zoo` is itself running in.
25. Verify the selected container is still the intended one at the moment of action, not
    only at the moment of selection.
26. Refuse and explain rather than guessing when a target is ambiguous, gone, or of the
    wrong kind.

## 6. Non-goals

- Not a general docker UI.
- Not multi-host: one daemon.
- Not a process viewer *inside* a primate.
- Not a replacement for `primate-session-list`, the scriptable listing.

---

## 7. The system it runs in

### 7.1 Identification

Containers carry labels, set by the launchers and already present in `zfuncs`:

| label | on | value |
|---|---|---|
| `primate.managed` | both | empty |
| `primate.image` | both | the image name |
| `primate.session` | sessions | empty |
| `primate.name` | sessions | the session name |

Identify containers by these labels. Image names are not sufficient: `spark-bench` is both a
roster image and the image of unrelated eval containers, so matching on image selects
containers `zoo` must not touch.

Sessions created before `primate.managed` existed carry only `primate.session`. Docker ANDs
repeated `--filter label=`, so selecting both sets takes more than one query.

### 7.2 The launchers

Currently the primates are managed with `primate()`, `primate-session()`,
`primate-session-resume()`, `primate-session-kill()` and `primate-session-list()` are
zsh functions in `zfuncs`. The launchers own the workspace mount, the refusal to mount `$HOME`,
the docker socket gid, the home volume, and the first-run sync that places vault-managed
configs into a new volume.

Using the existing launchers is not a requirement for the future design. The functions can be
reused or entirely replaced by the new zoo feature using any language (zsh, python, c++,
etc...).

### 7.3 Container identity

`docker ps` reports a 12-character id. A process's own container id is 64 characters, read
from `/proc/self/mountinfo` (`/proc/self/cgroup` is empty under cgroup v2 in Docker
Desktop). Comparisons between the two are prefix comparisons. On a host, rather than inside
a container, there is no such id.

Session **names are reusable** — a session may be destroyed and another created with the
same name.

### 7.4 Data sources

| source | returns | cost |
|---|---|---|
| `docker ps -a --filter label=… --format …` | container rows | 15–30 ms |
| API `/containers/json?all=true` | container rows, JSON, 64-character ids | ~13 ms |
| `docker stats --no-stream` | one sample | ~1.6 s |
| API `/containers/{id}/stats?stream=false` | one sample, JSON, raw numeric fields | ~2.0 s |
| API `/containers/{id}/stats?stream=false&one-shot=true` | one reading, no CPU% (the client keeps the previous reading and computes the delta) | **~6 ms** |
| `docker stats` streamed | a full set every ~500 ms after a ~2 s first sample | — |
| API `/containers/{id}/stats` streamed | JSON samples, raw numeric fields | — |

The ~2 s for a single sample is the daemon computing CPU% from two readings; it is not
client overhead, and it applies to the CLI and the API alike. `one-shot=true` (API ≥ 1.41,
Docker ≥ 20.10) skips that wait by returning a single reading; CPU% is then the caller's
delta between two of its own readings, which is what `docker stats` computes internally.
Measured 2026-09-09 on Docker Desktop 29.7 (arm64): 6 ms per container against 1009 ms for
the two-reading form. It is what lets a viewer refresh every container per tick with no
streaming sampler at all.

Streamed `docker stats` emits terminal control sequences even when stdout is not a terminal.
The API returns bytes and nanoseconds rather than strings like `686MiB / 31.29GiB`.

### 7.5 Environment

- Hosts: macOS (Docker Desktop, arm64) and Linux (x86_64 and arm64).
- `jq` is installed on every machine, including the Mac.
- `zsh/curses` is available on every machine, including the Mac. It provides windows,
  refresh, attributes, colour, timed input and resize, and supports leaving curses to run a
  normal command and re-entering. It does not name special keys — arrows arrive as raw
  escape sequences.
- tmux is installed on every machine, including the Mac. **Correction (2026-09-10): this was
  false on the `intel-nuc.tworivers` host — tmux was not installed there (only inside the primate
  images). Since the implementation now requires tmux on the host (see §7.6), tmux is a host
  prerequisite, not a given; verify it per host.**
- `~/.zfuncs` is a symlink into the repository, so the checked-out branch is the user's live
  environment. Develop in a git worktree.

### 7.6 The tmux-window model (the shipped implementation)

The requirements above prescribe no architecture. The implementation on `master` chose this one,
and it is recorded here because it changes the *mechanism* of requirements 12–15 (attach, resume,
shell, return), not the contract:

- **zoo runs as window 0 of a tmux session it owns.** Launched outside tmux it re-execs itself
  via `tmux new-session -A -s zoo` (`-A` re-attaches an existing `zoo` session). `--once` is never
  wrapped — it stays the plain, scriptable frame.
- **Actions open tmux windows** instead of the process lending its terminal to a child. This
  removes the single-terminal hand-off entirely (endwin/re-enter, the SIGINT dance, the ctrl-c
  and ctrl-z edge cases from §6) — the list keeps refreshing while a window runs. Returning is a
  tmux concern: `ctrl-b w` / `ctrl-b 0`.
- **tmux is now a hard prerequisite on the host** (no in-terminal fallback — a fallback would be
  the deleted hand-off). Absent tmux, zoo exits with a message.
- **Nesting is accepted, not worked around.** A `primate-session` runs tmux inside the container,
  so attaching nests tmux; the inner prefix becomes `ctrl-b ctrl-b`.
- **A window is targeted at the session with a trailing colon** (`new-window -t zoo:`): window 0
  is also named `zoo`, and a bare `-t zoo` resolves to that window (index 0) and fails. This was
  invisible to a stubbed tmux and only a real server caught it — hence a real-tmux test alongside
  the stubbed ones.

### 7.7 UX (v0.3.0)

Cosmetic and ergonomic decisions layered on the model above, all backed by pure, unit-tested
functions so the logic is testable without a terminal:

- Rows are coloured by state, degrading to plain attributes where the terminal has no colour, so
  colour only ever decorates a state that already reads in the text.
- The title carries host facts (cpu count, total RAM from the daemon's `/info`) and Σ, the summed
  CPU%/memory of the running primates.
- The launch picker is **platform-aware**: images this host cannot run are greyed and refused with
  a reason. The requirements table (cuda-* need an NVIDIA GPU; spark-bench is amd64-only) lives in
  zoo, not derived from the dockerfiles. Inside a primate the capability view is the container's,
  which is correct.
- The picker, session-name prompt and kill confirm are centered curses popup boxes over the list.
- A letter in the picker is type-ahead (jump to the next matching image, cycling). The main list
  keeps its single-key actions, so type-ahead is picker-only.

---

## 8. Verification

27. Behaviour must be verified in a shell with **job control enabled** — one reading
    commands from a terminal. `zsh -c`, `zsh -i -c` and `zsh -i script.zsh` all run without
    it and cannot observe background-process notices or interrupt handling.
28. Cover both sides of each environment split: `TERM` set and unset, inside a container and
    on a host, macOS daemon and Linux daemon.
29. Tests must not depend on ambient state — which images happen to be local, whether a
    roster is on disk, whether `TERM` happens to be set.
30. Tests that create or attach to sessions must be opt-in and skip loudly by default, so a
    test run never disturbs live sessions.
31. Confirm each assertion can fail: break the behaviour it covers and see it go red.
