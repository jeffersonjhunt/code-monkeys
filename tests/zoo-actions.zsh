#!/usr/bin/env zsh
# tests/zoo-actions.zsh — the a (resume) and e (exec) keys. Hermetic: nothing is
# attached to, exec'd into, or started; primate-session-resume, docker and
# _primate_self_container_id are stubbed.
#
# The refusals matter more than the successes here. 'a' on a foreground primate
# and 'e' on a stopped container are both things a user will try, and both have to
# explain themselves rather than fail obscurely.

set -u
ZF="${0:A:h}/../zfuncs"
fails=0
SELF64=aaaa1111bbbb2222cccc3333dddd4444eeee5555ffff6666aaaa7777bbbb8888
SELF12=aaaa1111bbbb
ID12=bbbb2222cccc

source "$ZF" >/dev/null 2>&1

CALLS="$(mktemp)"; trap 'rm -f "$CALLS"' EXIT
INSPECT_ID=""
primate-session-resume() { print -r -- "resume $*" >> "$CALLS" }
docker() {
  print -r -- "docker $*" >> "$CALLS"
  if [[ "${1:-}" == inspect ]]; then
    [[ -n "$INSPECT_ID" ]] || return 1
    print -r -- "$INSPECT_ID"
  fi
  return 0
}
_primate_self_container_id() { print -r -- "$SELF64" }
_called() { cat "$CALLS" 2>/dev/null }
_reset()  { : > "$CALLS" }
_expect_id() { INSPECT_ID="${1}$(printf '0%.0s' {1..$(( 64 - ${#1} ))})" }

_want()    { if [[ "$2" == *"$3"* ]]; then print -r -- "  ok   $1"
             else print -r -- "  FAIL $1 — expected: $3" >&2; (( fails++ )); fi }
_wantnot() { if [[ "$2" != *"$3"* ]]; then print -r -- "  ok   $1"
             else print -r -- "  FAIL $1 — should not contain: $3" >&2; (( fails++ )); fi }
# "did not act", not "made no calls": the preflight legitimately runs
# `docker inspect` to decide, so asserting silence would fail for the right reason
# happening. Name the call that must not have occurred.
_didnot() { # _didnot <desc> <needle>
  if [[ "$(_called)" != *"$2"* ]]; then print -r -- "  ok   $1"
  else print -r -- "  FAIL $1 — it called: $(_called)" >&2; (( fails++ )); fi }

print -r -- "a (resume):"
_reset; _expect_id "$ID12"
out="$(_zoo_attach primate vigilant_fox "$ID12" 2>&1)"
_want "refuses a foreground primate"      "$out" "no tmux to re-attach to"
_want "and says what e does instead"      "$out" "opens a NEW shell"
_didnot "did not resume" resume

_reset; _expect_id "$SELF12"
out="$(_zoo_attach session mine "$SELF12" 2>&1)"
_want "refuses the container zoo runs in" "$out" "is the container zoo is running in"
_didnot "did not resume" resume

_reset; INSPECT_ID=""
out="$(_zoo_attach session vanished "$ID12" 2>&1)"
_want "refuses a session that is gone"    "$out" "no longer exists"
_didnot "did not resume" resume

_reset; _expect_id 9999deadbeef
out="$(_zoo_attach session recycled "$ID12" 2>&1)"
_want "refuses a reused session name"     "$out" "different container than the one selected"
_didnot "did not resume" resume

_reset; _expect_id "$ID12"
_zoo_attach session good "$ID12" >/dev/null 2>&1
_want "resumes a live session"            "$(_called)" "resume good"

print -r -- "e (exec):"
_reset; _expect_id "$SELF12"
out="$(_zoo_exec session mine "$SELF12" "Up 2 hours" 2>&1)"
_want "refuses the container zoo runs in" "$out" "is the container zoo is running in"
_didnot "did not exec" "docker exec"

_reset; _expect_id "$ID12"
out="$(_zoo_exec session cold "$ID12" "Exited (0) 3 days ago" 2>&1)"
_want "refuses a stopped container"       "$out" "is not running"
_want "and points at a for a session"     "$out" "starts a stopped session"
_wantnot "did not exec"                   "$(_called)" "exec"

_reset; _expect_id "$ID12"
out="$(_zoo_exec primate cold_fg "$ID12" "Exited (0) 1 hour ago" 2>&1)"
_want "refuses a stopped foreground too"  "$out" "is not running"
_wantnot "no session-only advice there"   "$out" "starts a stopped session"

_reset; _expect_id "$ID12"
_zoo_exec session live "$ID12" "Up 2 hours" >/dev/null 2>&1
_want "execs into a running container by id" "$(_called)" "docker exec -it ${ID12} zsh"

# A foreground primate is addressed by id, so it needs no name re-check — and must
# not be refused for failing one.
_reset; INSPECT_ID=""
_zoo_exec primate fg_live "$ID12" "Up 5 minutes" >/dev/null 2>&1
_want "foreground exec needs no name lookup" "$(_called)" "docker exec -it ${ID12} zsh"

if (( fails )); then print -r -- "FAILED ($fails)" >&2; exit 1; fi
print -r -- "PASSED"
