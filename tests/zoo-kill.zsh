#!/usr/bin/env zsh
# tests/zoo-kill.zsh — the destructive path. Hermetic: primate-session-kill,
# docker and _primate_self_container_id are all stubbed, so nothing is killed.
#
# The case worth the most here is the self-guard's PREFIX comparison. docker ps
# reports a 12-char id and _primate_self_container_id a 64-char one, so an
# equality test would never match and the guard would look present in the source
# while doing nothing at all. Both directions are asserted: it must refuse self,
# and it must NOT refuse a different container that merely shares the daemon.

set -u
ZF="${0:A:h}/../zfuncs"
fails=0

SELF64=aaaa1111bbbb2222cccc3333dddd4444eeee5555ffff6666aaaa7777bbbb8888
SELF12=aaaa1111bbbb
OTHER12=99998888777

source "$ZF" >/dev/null 2>&1

# Recorded to a file, not a variable: the assertions below run _zoo_kill inside
# $( ) to capture its output, and a subshell's variable assignments do not survive.
# The first version of this test asserted on a variable and reported two false
# failures for exactly that reason.
CALLS="$(mktemp)"
trap 'rm -f "$CALLS"' EXIT
primate-session-kill() { print -r -- "session-kill $*" >> "$CALLS"; print -r -- "removing $1 (home volume persists)" }
docker() { print -r -- "docker $*" >> "$CALLS"; return 0 }
_called() { cat "$CALLS" 2>/dev/null }
_reset()  { : > "$CALLS" }
_primate_self_container_id() { print -r -- "$SELF64" }

_want() {
  if [[ "$2" == *"$3"* ]]; then print -r -- "  ok   $1"
  else print -r -- "  FAIL $1 — expected to contain: $3" >&2; (( fails++ )); fi
}
_wantnot() {
  if [[ "$2" != *"$3"* ]]; then print -r -- "  ok   $1"
  else print -r -- "  FAIL $1 — should NOT contain: $3" >&2; (( fails++ )); fi
}

print -r -- "self-guard:"
_reset
out="$(_zoo_kill session mine "$SELF12" 2>&1)"; rc=$?
_want "refuses the container zoo runs in" "$out" "refusing"
(( rc != 0 )) && print -r -- "  ok   returns non-zero" \
  || { print -r -- "  FAIL returned 0 while refusing" >&2; (( fails++ )); }
[[ -z "$(_called)" ]] && print -r -- "  ok   killed nothing" \
  || { print -r -- "  FAIL it still called: $(_called)" >&2; (( fails++ )); }

print -r -- "self-guard does not over-match:"
_reset
out="$(_zoo_kill session other "$OTHER12" 2>&1)"
_wantnot "a different container is not refused" "$out" "refusing"
_want "and is actually killed" "$(_called)" "session-kill other"

print -r -- "dispatch:"
_reset; _zoo_kill session sess1 bbbb2222cccc >/dev/null 2>&1
_want "session goes through primate-session-kill" "$(_called)" "session-kill sess1"
_wantnot "session does not use docker rm"         "$(_called)" "docker rm"

_reset; out="$(_zoo_kill primate vigilant_fox cccc3333dddd 2>&1)"
_want "foreground uses docker rm -f"    "$(_called)" "docker rm -f cccc3333dddd"
_want "and says why that is the kill"   "$out"     "--rm, so this is the kill"

print -r -- "empty id is refused, not treated as a prefix match:"
# Every string starts with the empty string, so `$self == ""*` is true and an
# unparsed row made zoo refuse EVERY kill while blaming the self-guard. That is
# how the tab-split bug presented, so it is asserted here rather than inferred.
_reset
out="$(_zoo_kill primate "" "" 2>&1)"; rc=$?
_want "says it is an internal error" "$out" "internal error"
_wantnot "does not blame the self-guard" "$out" "is the container zoo is running in"
(( rc == 2 )) && print -r -- "  ok   returns 2" \
  || { print -r -- "  FAIL returned $rc, wanted 2" >&2; (( fails++ )); }
[[ -z "$(_called)" ]] && print -r -- "  ok   killed nothing" \
  || { print -r -- "  FAIL it still called: $(_called)" >&2; (( fails++ )); }

print -r -- "guard is not bypassed when self id is unavailable (on a host):"
_primate_self_container_id() { print -r -- "" }
_reset; _zoo_kill session anything aaaa1111bbbb >/dev/null 2>&1
_want "kills normally when not in a container" "$(_called)" "session-kill anything"

if (( fails )); then print -r -- "FAILED ($fails)" >&2; exit 1; fi
print -r -- "PASSED"
