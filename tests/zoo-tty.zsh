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

if (( fails )); then print -r -- "FAILED ($fails)" >&2; exit 1; fi
print -r -- "PASSED"
