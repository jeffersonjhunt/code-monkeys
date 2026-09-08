#!/usr/bin/env zsh
# tests/zoo-frame.zsh — assert the frame zoo renders, from fixtures.
#
# Hermetic by construction: ZOO_PS_SOURCE and ZOO_STATS_SOURCE replace both docker
# queries with files, so this needs no daemon, no images and no containers. That
# seam exists for exactly this and nothing else — zoo is not fleet-aware.
#
# The cases that matter are the ones that look fine when they are wrong: counts
# that double-count, a stopped container silently inheriting another's stats, and
# a failed query rendering as an empty table.

set -u
ZF="${0:A:h}/../zfuncs"
fails=0
FIX="$(mktemp -d)"
trap 'rm -rf "$FIX"' EXIT

source "$ZF" >/dev/null 2>&1

# id  name  image  status  labels
{
  printf 'aaa1\tvigilant_fox\tminion\tUp 4 minutes\tprimate.image=minion,primate.managed=\n'
  printf 'bbb2\tscratch\tclaude\tUp 2 hours\tprimate.image=claude,primate.managed=,primate.name=scratch,primate.session=\n'
  printf 'ccc3\tcold\topencode\tExited (0) 3 days ago\tprimate.image=opencode,primate.managed=,primate.name=cold,primate.session=\n'
  printf 'ddd4\told\tclaude\tUp 21 hours\tprimate.image=claude,primate.name=old,primate.session=\n'
} > "$FIX/ps"
{
  printf 'aaa1\t0.10%%\t12MiB / 31.29GiB\t0.04%%\t3\n'
  printf 'bbb2\t4.48%%\t407.6MiB / 31.29GiB\t1.27%%\t54\n'
  printf 'ddd4\t3.18%%\t476.4MiB / 31.29GiB\t1.49%%\t66\n'
} > "$FIX/stats"
printf '' > "$FIX/empty"

_out() { ZOO_PS_SOURCE="$1" ZOO_STATS_SOURCE="$2" zoo --once 2>&1 }

_want() {  # _want <desc> <output> <needle>
  if [[ "$2" == *"$3"* ]]; then print -r -- "  ok   $1"
  else print -r -- "  FAIL $1 — expected to contain: $3" >&2; (( fails++ )); fi
}
_wantnot() {
  if [[ "$2" != *"$3"* ]]; then print -r -- "  ok   $1"
  else print -r -- "  FAIL $1 — should NOT contain: $3" >&2; (( fails++ )); fi
}

print -r -- "mixed fixture (1 foreground, 3 sessions, one of them legacy):"
out="$(_out "$FIX/ps" "$FIX/stats")"
[[ -n "$out" ]] || { print -r -- "  FAIL rendered nothing" >&2; (( fails++ )); }
# The counter bug this caught: (( n++ )) returns the OLD value, so the first
# session was false-y and got counted as a primate as well.
_want "counts each container once"        "$out" "1 primate, 3 sessions"
_want "foreground row is KIND=primate"    "$out" "primate  vigilant_fox"
_want "session row is KIND=session"       "$out" "session  scratch"
_want "merges stats onto the right row"   "$out" "4.48%"
_want "stopped container shows no stats"  "$out" "—"
_wantnot "stopped row did not borrow stats" "${out#*cold}" "0.04%"
_want "flags the pre-primate.managed one" "$out" "predates primate.managed"
_want "offers the keys that exist"        "$out" "k kill"

print -r -- "selection marker:"
sel1="$(ZOO_PS_SOURCE="$FIX/ps" ZOO_STATS_SOURCE="$FIX/stats" _zoo_frame "$(cat "$FIX/ps")" "$(cat "$FIX/stats")" 0 3 1)"
sel3="$(_zoo_frame "$(cat "$FIX/ps")" "$(cat "$FIX/stats")" 0 3 3)"
_want "row 1 marked when selected"     "$sel1" "> primate  vigilant_fox"
_wantnot "row 3 not marked then"       "$sel1" "> session  cold"
_want "row 3 marked when selected"     "$sel3" "> session  cold"
_wantnot "row 1 not marked then"       "$sel3" "> primate  vigilant_fox"
_want "no marker at all with 0"        "$(_zoo_frame "$(cat "$FIX/ps")" "" -1 3 0)" "  primate  vigilant_fox"

print -r -- "row parsing agrees with what the frame shows:"
rows="$(_zoo_rows "$(cat "$FIX/ps")")"
_want "row 1 is the foreground primate" "${rows%%$'\n'*}" "primate	vigilant_fox"
n=$(print -r -- "$rows" | grep -c .)
if (( n == 4 )); then print -r -- "  ok   four rows parsed"
else print -r -- "  FAIL parsed $n rows, wanted 4" >&2; (( fails++ )); fi

print -r -- "all-managed fixture:"
grep -v 'ddd4' "$FIX/ps" > "$FIX/ps2"
out2="$(_out "$FIX/ps2" "$FIX/stats")"
_wantnot "no legacy note when none are legacy" "$out2" "predates primate.managed"
_want "counts adjust"                          "$out2" "1 primate, 2 sessions"

print -r -- "empty fixture:"
out3="$(_out "$FIX/empty" "$FIX/empty")"
_want "says none rather than rendering blank" "$out3" "no primates"
_want "counts are zero"                       "$out3" "0 primates, 0 sessions"

print -r -- "failed query is not an empty one:"
out4="$(ZOO_PS_SOURCE="$FIX/does-not-exist" ZOO_STATS_SOURCE="$FIX/empty" zoo --once 2>&1)"; rc=$?
if (( rc != 0 )); then print -r -- "  ok   exits non-zero"
else print -r -- "  FAIL exited 0 on a failed query" >&2; (( fails++ )); fi
_want "says the query failed"          "$out4" "could not query docker"
_wantnot "does not claim none running" "$out4" "no primates"

if (( fails )); then print -r -- "FAILED ($fails)" >&2; exit 1; fi
print -r -- "PASSED"
