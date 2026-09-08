#!/usr/bin/env zsh
# tests/zoo-tty.zsh — the interactive loop needs a pty, so it gets its own test.
#
# What this exists to catch: zsh's `always` block does NOT run when the shell
# takes SIGINT. zoo originally relied on `always` alone, so ctrl-c left the
# terminal in the alternate screen with the cursor hidden — the defect a user
# remembers longest. The hermetic frame tests cannot see this at all; only a real
# pty can.

set -u
ZF="${0:A:h}/../zfuncs"
fails=0

# Forced, not inherited. tput emits NOTHING without a terminfo entry, so with TERM
# unset zoo never enters the alternate screen and every escape-sequence assertion
# below fails — which is what happened on intel-nuc, where a non-interactive ssh
# session has no TERM. It passed here only because this shell happens to have one.
# A test whose result depends on ambient environment tests a different thing on
# every machine. script(1) propagates TERM, so setting it here is enough.
export TERM=xterm-256color

if ! command -v script >/dev/null 2>&1; then
  print -r -- "SKIPPED — script(1) not installed, so no pty can be allocated here."
  print -r -- "          The interactive loop and terminal restore were NOT tested."
  exit 0
fi

OUT="$(mktemp)"
trap 'rm -f "$OUT"' EXIT
RUN="zsh -c 'source ${ZF:A} >/dev/null 2>&1; zoo -i 1'"

# grep -c prints 0 AND exits 1 on no match, so a `|| print 0` fallback appends a
# second 0 and the caller does arithmetic on "0\n0". Take the count, default only
# if it is genuinely empty.
_count() { local __n; __n=$(LC_ALL=C grep -acF -- "$1" "$OUT" 2>/dev/null); print -r -- "${__n:-0}" }
_esc_smcup=$'\e[?1049h'; _esc_rmcup=$'\e[?1049l'
_esc_civis=$'\e[?25l';   _esc_cnorm=$'\e[?25h'

_assert_ge() {  # _assert_ge <desc> <actual> <want>
  if (( $2 >= $3 )); then print -r -- "  ok   $1 ($2)"
  else print -r -- "  FAIL $1 — got $2, wanted at least $3" >&2; (( fails++ )); fi
}

print -r -- "quit with q:"
( sleep 2; printf 'q' ) | timeout 20 script -qec "$RUN" /dev/null > "$OUT" 2>&1
_assert_ge "rendered at least one frame" "$(_count 'zoo ')" 1
_assert_ge "entered the alternate screen"  "$(_count "$_esc_smcup")" 1
_assert_ge "left the alternate screen"     "$(_count "$_esc_rmcup")" 1
_assert_ge "restored the cursor"           "$(_count "$_esc_cnorm")" 1

print -r -- "interrupt with ctrl-c:"
( sleep 3; printf '\003'; sleep 2 ) | timeout 20 script -qec "$RUN" /dev/null > "$OUT" 2>&1
_assert_ge "rendered at least one frame" "$(_count 'zoo ')" 1
_assert_ge "hid the cursor while running"  "$(_count "$_esc_civis")" 1
_assert_ge "left the alternate screen"     "$(_count "$_esc_rmcup")" 1
_assert_ge "restored the cursor"           "$(_count "$_esc_cnorm")" 1

# The selected row must be the row the confirm prompt names. When the field split
# in the loop used a literal backslash-t instead of a tab, every field came out
# empty, the prompt named nothing, and the empty id made the self-guard refuse the
# kill — three symptoms of one bug, none visible without a pty.
#
# Driven from fixtures, not the live daemon. The first version pressed k on row 1
# of whatever was actually running and relied on the cancel keystroke to spare it;
# when sessions began sorting first, row 1 became a real session. A test whose
# safety depends on one keystroke working is not a safe test. With fixtures the
# only container it can name does not exist.
print -r -- "selection reaches the confirm prompt:"
FIXD="$(mktemp -d)"
US=$'\x1f'
print -r -- "fix1${US}fixturebox${US}minion${US}Up 4 minutes" > "$FIXD/managed"
: > "$FIXD/sessions"
: > "$FIXD/stats"
FRUN="zsh -c 'source ${ZF:A} >/dev/null 2>&1
  export ZOO_PS_SESSION_SOURCE=$FIXD/sessions ZOO_PS_MANAGED_SOURCE=$FIXD/managed ZOO_STATS_SOURCE=$FIXD/stats
  zoo -i 1'"
( sleep 2; printf 'k'; sleep 1; printf 'n'; sleep 1; printf 'q'; sleep 1 ) \
  | timeout 25 script -qec "$FRUN" /dev/null > "$OUT" 2>&1
_assert_ge "the fixture row is listed"        "$(_count 'fixturebox')" 1
_assert_ge "confirm prompt appears"           "$(_count 'zoo — confirm')" 1
_assert_ge "prompt names kind AND container"  "$(_count 'kill primate fixturebox')" 1
_assert_ge "no internal-error from a bad row" "$(( 1 - $(_count 'internal error') ))" 1
rm -rf "$FIXD"

# A CONFIRMED kill, end to end. The section above presses n and stops one keystroke
# short of the thing the feature exists for — which is exactly how a kill branch
# that referenced a variable removed three commits earlier shipped "verified": the
# prompt rendered correctly and nothing ever pressed y.
#
# Safe by construction: the fixture row carries the id of a container this test
# created, so the only thing it can kill is its own. kind=primate, so _zoo_kill
# removes it by id and no name resolution is involved.
if command -v docker >/dev/null 2>&1 && docker version >/dev/null 2>&1; then
  print -r -- "a confirmed kill actually kills:"
  docker rm -f zoo-killtest >/dev/null 2>&1
  if docker run -d --name zoo-killtest --label primate.managed --label primate.image=minion \
       minion sleep 120 >/dev/null 2>&1; then
    KID="$(docker ps --filter name=zoo-killtest --format '{{.ID}}')"
    KD="$(mktemp -d)"
    print -r -- "${KID}\x1fzoo-killtest\x1fminion\x1fUp 1 minute" \
      | sed 's/\\x1f/\x1f/g' > "$KD/managed"
    : > "$KD/sessions"; : > "$KD/stats"
    KRUN="zsh -c 'source ${ZF:A} >/dev/null 2>&1
      export ZOO_PS_SESSION_SOURCE=$KD/sessions ZOO_PS_MANAGED_SOURCE=$KD/managed ZOO_STATS_SOURCE=$KD/stats
      zoo -i 1'"
    ( sleep 2; printf 'k'; sleep 1; printf 'y'; sleep 2; printf ' '; sleep 1; printf 'q'; sleep 1 ) \
      | timeout 30 script -qec "$KRUN" /dev/null > "$OUT" 2>&1
    _assert_ge "the kill ran"                  "$(_count 'so this is the kill')" 1
    _assert_ge "no internal error"             "$(( 1 - $(_count 'internal error') ))" 1
    _assert_ge "no bogus refusal"              "$(( 1 - $(_count 'refusing') ))" 1
    if docker ps -a --format '{{.Names}}' | grep -qx zoo-killtest; then
      print -r -- "  FAIL the container is still there — the kill did nothing" >&2; (( fails++ ))
      docker rm -f zoo-killtest >/dev/null 2>&1
    else
      print -r -- "  ok   the container is gone"
    fi
    rm -rf "$KD"
  else
    print -r -- "  SKIPPED — could not start a throwaway container (is the minion image local?)"
  fi
else
  print -r -- "  SKIPPED — no reachable docker daemon; a confirmed kill was NOT tested."
fi

# The a and e keys, through the real loop. Unit tests cannot see this layer: F1
# was a kill branch calling a variable that had been removed, and every unit test
# of _zoo_kill passed while the key did nothing. So each action key gets one pass
# through the loop, driving the actual keystroke.
if command -v docker >/dev/null 2>&1 && docker version >/dev/null 2>&1; then
  print -r -- "the e key opens a real shell in the container:"
  docker rm -f zoo-exectest >/dev/null 2>&1
  if docker run -d --name zoo-exectest --label primate.managed --label primate.image=minion \
       minion sleep 180 >/dev/null 2>&1; then
    EID="$(docker ps --filter name=zoo-exectest --format '{{.ID}}')"
    ED="$(mktemp -d)"
    printf '%s\x1fzoo-exectest\x1fminion\x1fUp 1 minute\n' "$EID" > "$ED/managed"
    : > "$ED/sessions"; : > "$ED/stats"
    ERUN="zsh -c 'source ${ZF:A} >/dev/null 2>&1
      export ZOO_PS_SESSION_SOURCE=$ED/sessions ZOO_PS_MANAGED_SOURCE=$ED/managed ZOO_STATS_SOURCE=$ED/stats
      zoo -i 1'"
    ( sleep 2; printf 'e'; sleep 4; printf 'print -r -- ZOO${:-}EXEC_OK\n'; sleep 2
      printf 'exit\n'; sleep 2; printf 'q'; sleep 1 ) \
      | timeout 40 script -qec "$ERUN" /dev/null > "$OUT" 2>&1
    # The marker must be something the terminal's ECHO of the typed line cannot
    # produce. With `echo ZOOEXEC_MARKER` the echoed keystrokes alone satisfied
    # this, so it passed even with the e wiring broken. The line TYPED contains
    # ZOO${:-}EXEC_OK; only the shell's OUTPUT is the bare ZOOEXEC_OK.
    _assert_ge "a shell really ran inside the container" "$(_count 'ZOOEXEC_OK')" 1
    _assert_ge "no internal error"                       "$(( 1 - $(_count 'internal error') ))" 1
    _assert_ge "no refusal"                              "$(( 1 - $(_count 'refusing') ))" 1
    docker rm -f zoo-exectest >/dev/null 2>&1
    rm -rf "$ED"
  else
    print -r -- "  SKIPPED — could not start a throwaway container (is the minion image local?)"
  fi

  # The a key's refusal path, which needs no tmux and destroys nothing: a
  # foreground primate has no session to re-attach to and must say so.
  print -r -- "the a key refuses a foreground primate, through the loop:"
  AD="$(mktemp -d)"
  printf 'fix1\x1ffixturebox\x1fminion\x1fUp 4 minutes\n' > "$AD/managed"
  : > "$AD/sessions"; : > "$AD/stats"
  ARUN="zsh -c 'source ${ZF:A} >/dev/null 2>&1
    export ZOO_PS_SESSION_SOURCE=$AD/sessions ZOO_PS_MANAGED_SOURCE=$AD/managed ZOO_STATS_SOURCE=$AD/stats
    zoo -i 1'"
  ( sleep 2; printf 'a'; sleep 2; printf ' '; sleep 1; printf 'q'; sleep 1 ) \
    | timeout 25 script -qec "$ARUN" /dev/null > "$OUT" 2>&1
  _assert_ge "explains there is no tmux"  "$(_count 'no tmux to re-attach to')" 1
  _assert_ge "points at e instead"        "$(_count 'opens a NEW shell')" 1
  rm -rf "$AD"
else
  print -r -- "  SKIPPED — no reachable docker daemon; the a and e keys were NOT tested."
fi

# The n and N keys, through the real loop, with the launchers stubbed INSIDE the
# pty run. That exercises loop -> picker -> launcher without starting a container,
# which is the layer unit tests cannot see and the one F1 lived in. Nothing here
# needs a daemon, so it runs wherever script(1) does.
print -r -- "n and N pick an image and hand it to the right launcher:"
ND="$(mktemp -d)"
: > "$ND/sessions"; : > "$ND/managed"; : > "$ND/stats"
# The roster is stubbed for two reasons, both found by running this on intel-nuc.
# _primate_roster reads primates/*.dockerfile NEXT TO zfuncs, so anywhere zfuncs is
# staged alone the picker correctly says "no roster here" and every assertion below
# fails for a reason that is not a bug. And asserting on the real roster couples
# these tests to its contents — "aichat is the second entry" breaks the day someone
# adds a dockerfile that sorts earlier. Two fixed names, deterministic everywhere.
NRUN="zsh -c 'source ${ZF:A} >/dev/null 2>&1
  _primate_roster() { print -r -- zoo-img-one; print -r -- zoo-img-two }
  primate-session() { print -r -- \"STUBSESSION \$*\" }
  primate() { print -r -- \"STUBPRIMATE \$*\" }
  export ZOO_PS_SESSION_SOURCE=$ND/sessions ZOO_PS_MANAGED_SOURCE=$ND/managed ZOO_STATS_SOURCE=$ND/stats
  zoo -i 1'"

# n, enter on row 1 -> codemonkey, the first roster entry
( sleep 2; printf 'n'; sleep 2; printf '\n'; sleep 2; printf 'q'; sleep 1 ) \
  | timeout 25 script -qec "$NRUN" /dev/null > "$OUT" 2>&1
_assert_ge "the picker offers the roster"      "$(_count 'workspace to mount')" 1
_assert_ge "n starts a SESSION with the pick"  "$(_count 'STUBSESSION zoo-img-one')" 1
_assert_ge "n did not start a foreground one"  "$(( 1 - $(_count 'STUBPRIMATE') ))" 1

# down-arrow then enter -> the second entry, so the cursor is real
( sleep 2; printf 'n'; sleep 2; printf '\033[B'; sleep 1; printf '\n'; sleep 2; printf 'q'; sleep 1 ) \
  | timeout 25 script -qec "$NRUN" /dev/null > "$OUT" 2>&1
_assert_ge "the picker cursor moves"           "$(_count 'STUBSESSION zoo-img-two')" 1

# N -> the foreground launcher instead
( sleep 2; printf 'N'; sleep 2; printf '\n'; sleep 2; printf 'q'; sleep 1 ) \
  | timeout 25 script -qec "$NRUN" /dev/null > "$OUT" 2>&1
_assert_ge "N starts a FOREGROUND primate"     "$(_count 'STUBPRIMATE zoo-img-one')" 1
_assert_ge "N did not start a session"         "$(( 1 - $(_count 'STUBSESSION') ))" 1

# esc cancels and starts nothing
( sleep 2; printf 'n'; sleep 2; printf '\033'; sleep 2; printf 'q'; sleep 1 ) \
  | timeout 25 script -qec "$NRUN" /dev/null > "$OUT" 2>&1
# Paired with positive evidence: "nothing was started" alone also passes if the
# picker never opened, which is the vacuous shape that has already let two bugs
# through in this feature.
_assert_ge "the picker did open"               "$(_count 'workspace to mount')" 1
_assert_ge "esc cancels it"                    "$(( 1 - $(_count 'STUBSESSION') ))" 1
_assert_ge "and starts nothing at all"         "$(( 1 - $(_count 'STUBPRIMATE') ))" 1
rm -rf "$ND"

# The degraded path, which the intel-nuc run exposed by accident: with no TERM,
# every tput is a silent no-op and zoo runs without the alternate screen or a
# hidden cursor. That is a real configuration — any non-interactive or minimal
# environment — and it must still render and still quit rather than wedge.
print -r -- "no TERM: degrades instead of breaking:"
( sleep 2; printf 'q' ) | timeout 20 env -u TERM script -qec "$RUN" /dev/null > "$OUT" 2>&1
rc=$?
_assert_ge "still renders a frame"      "$(_count 'zoo ')" 1
_assert_ge "emits no alternate screen"  "$(( 1 - $(_count "$_esc_smcup") ))" 1
if (( rc == 0 )); then print -r -- "  ok   still quits cleanly on q"
else print -r -- "  FAIL exited $rc with no TERM" >&2; (( fails++ )); fi

if (( fails )); then print -r -- "FAILED ($fails)" >&2; exit 1; fi
print -r -- "PASSED"
