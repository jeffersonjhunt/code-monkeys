#!/usr/bin/env zsh
# tests/zoo-frame.zsh — the collector and the renderer, from fixtures.
#
# Hermetic: ZOO_PS_SESSION_SOURCE / ZOO_PS_MANAGED_SOURCE / ZOO_STATS_SOURCE stand
# in for the three docker queries, so this needs no daemon, no images and no
# containers. The two ps seams are separate on purpose — `kind` is decided by
# WHICH query matched, and a single merged fixture could not exercise that.
#
# Fields are separated by 0x1F, which cannot occur in a container name, image or
# status. It replaced a tab plus a substring test against docker's comma-joined
# label blob; the "lookalike" fixture below is the case that broke.

set -u
ZF="${0:A:h}/../zfuncs"
fails=0
FIX="$(mktemp -d)"
trap 'rm -rf "$FIX"' EXIT
US=$'\x1f'

source "$ZF" >/dev/null 2>&1

# id US name US image US status
{
  print -r -- "bbb2${US}scratch${US}claude${US}Up 2 hours"
  print -r -- "ccc3${US}cold${US}opencode${US}Exited (0) 3 days ago"
  print -r -- "ddd4${US}old${US}claude${US}Up 21 hours"
} > "$FIX/sessions"
{
  print -r -- "aaa1${US}vigilant_fox${US}minion${US}Up 4 minutes"
  print -r -- "bbb2${US}scratch${US}claude${US}Up 2 hours"
  print -r -- "ccc3${US}cold${US}opencode${US}Exited (0) 3 days ago"
  print -r -- "eee5${US}weird primate.session= name${US}minion${US}Up 1 minute"
} > "$FIX/managed"
{
  print -r -- "aaa1${US}0.10%${US}12MiB / 31.29GiB${US}0.04%${US}3"
  print -r -- "bbb2${US}4.48%${US}407.6MiB / 31.29GiB${US}1.27%${US}54"
  print -r -- "ddd4${US}3.18%${US}476.4MiB / 31.29GiB${US}1.49%${US}66"
} > "$FIX/stats"
: > "$FIX/empty"

_out() { ZOO_PS_SESSION_SOURCE="$1" ZOO_PS_MANAGED_SOURCE="$2" ZOO_STATS_SOURCE="$3" zoo --once 2>&1 }
_want()    { if [[ "$2" == *"$3"* ]]; then print -r -- "  ok   $1"
             else print -r -- "  FAIL $1 — expected: $3" >&2; (( fails++ )); fi }
_wantnot() { if [[ "$2" != *"$3"* ]]; then print -r -- "  ok   $1"
             else print -r -- "  FAIL $1 — should not contain: $3" >&2; (( fails++ )); fi }

print -r -- "classification comes from the query, not from string-matching labels:"
rows="$(ZOO_PS_SESSION_SOURCE="$FIX/sessions" ZOO_PS_MANAGED_SOURCE="$FIX/managed" _zoo_ps)"
n=$(print -r -- "$rows" | grep -c .)
if (( n == 5 )); then print -r -- "  ok   5 rows, each container once (dedupe)"
else print -r -- "  FAIL got $n rows, wanted 5" >&2; (( fails++ )); fi
_want "in both queries -> session"        "$rows" "session${US}scratch${US}claude${US}Up 2 hours${US}bbb2${US}0"
_want "session only -> session + legacy"  "$rows" "session${US}old${US}claude${US}Up 21 hours${US}ddd4${US}1"
_want "managed only -> primate"           "$rows" "primate${US}vigilant_fox${US}minion${US}Up 4 minutes${US}aaa1${US}0"
# The whole point of the separator change: this name contains the exact text the
# old substring test looked for.
_want "a name containing 'primate.session=' is still a primate" \
      "$rows" "primate${US}weird primate.session= name${US}minion"
_wantnot "and is not classified as a session" \
      "$rows" "session${US}weird primate.session= name"

print -r -- "rendered frame:"
out="$(_out "$FIX/sessions" "$FIX/managed" "$FIX/stats")"
_want "counts each container once"        "$out" "2 primates, 3 sessions"
_want "foreground row is KIND=primate"    "$out" "primate  vigilant_fox"
_want "session row is KIND=session"       "$out" "session  scratch"
_want "merges stats onto the right row"   "$out" "4.48%"
_want "row with no stats shows a dash"    "$out" "—"
# Assert the cold ROW itself, not everything after it: sessions now sort before
# primates, so "text after cold" runs into another container's stats and the
# assertion passed or failed for reasons unrelated to cold.
coldrow="$(print -r -- "$out" | grep 'session  cold')"
_want    "stopped row shows dashes"         "$coldrow" "—"
_wantnot "stopped row borrowed no stats"    "$coldrow" "0.04%"
_wantnot "stopped row borrowed no stats(2)" "$coldrow" "4.48%"
_want "flags the pre-primate.managed one" "$out" "predates primate.managed"
_want "offers the keys that exist"        "$out" "k kill"

print -r -- "selection marker:"
sel1="$(_zoo_frame "$rows" "$(cat "$FIX/stats")" 0 3 1)"
sel3="$(_zoo_frame "$rows" "$(cat "$FIX/stats")" 0 3 3)"
_want "row 1 marked when selected"   "$sel1" "> session  scratch"
_wantnot "row 3 not marked then"     "$sel1" "> session  old"
_want "row 3 marked when selected"   "$sel3" "> session  old"
_want "no marker with 0"             "$(_zoo_frame "$rows" "" -1 3 0)" "  session  scratch"

print -r -- "the table windows to the terminal, following the cursor:"
# More primates than fit would scroll the alternate screen, after which every
# cup 0 0 lands wrong — the same failure the image picker hit at 17 images on a
# 24-line terminal. Reported from real use for the picker; this is the same bug
# one screen over.
many=""
for i in 1 2 3 4 5 6; do many+="primate${US}box${i}${US}minion${US}Up 1 min${US}id${i}${US}0"$'\n'; done
w="$(_zoo_frame "$many" "" -1 3 5 3)"
_want    "shows the selected row"        "$w" "> primate  box5"
_want    "and its neighbours"            "$w" "primate  box4"
_wantnot "not rows outside the window"   "$w" "box1"
_want    "marks what is above"           "$w" "⋯ 2 more above"
_want    "marks what is below"           "$w" "⋯ 1 more below"
_want    "counts ALL rows, not the window" "$w" "6 primates"
n=$(print -r -- "$w" | grep -c "primate  box")
if (( n == 3 )); then print -r -- "  ok   exactly 3 rows rendered"
else print -r -- "  FAIL rendered $n rows, wanted 3" >&2; (( fails++ )); fi

# max 0 means no window: --once and a pipe must still get everything.
full="$(_zoo_frame "$many" "" -1 3 0 0)"
nf=$(print -r -- "$full" | grep -c "primate  box")
if (( nf == 6 )); then print -r -- "  ok   unwindowed when max is 0"
else print -r -- "  FAIL unwindowed render gave $nf rows, wanted 6" >&2; (( fails++ )); fi
_wantnot "and no markers then"           "$full" "more above"

print -r -- "no legacy containers:"
grep -v 'ddd4' "$FIX/sessions" > "$FIX/sessions2"
out2="$(_out "$FIX/sessions2" "$FIX/managed" "$FIX/stats")"
_wantnot "no legacy note when none are legacy" "$out2" "predates primate.managed"
_want "counts adjust"                          "$out2" "2 primates, 2 sessions"

print -r -- "empty:"
out3="$(_out "$FIX/empty" "$FIX/empty" "$FIX/empty")"
_want "says none rather than rendering blank" "$out3" "no primates"
_want "counts are zero"                       "$out3" "0 primates, 0 sessions"

print -r -- "_zoo_field is the only place a row is taken apart:"
local_ok=0
(
  ZOO_KIND=; ZOO_NAME=; ZOO_ID=
  _zoo_field "primate${US}box${US}minion${US}Up 1m${US}abc123${US}0" \
    && print -r -- "  ok   a good row sets fields by name: ${ZOO_KIND}/${ZOO_NAME}/${ZOO_ID}" \
    || print -r -- "  FAIL a good row was rejected"
)
# A row split on the wrong separator collapses to ONE field. That must fail at the
# split, not yield empty fields that surface later as a self-guard refusal — which
# is exactly how the U2 bug presented and why it was hunted in the wrong place.
if _zoo_field "primate\tbox\tminion\tUp 1m\tabc123\t0" 2>/dev/null; then
  print -r -- "  FAIL a tab-separated row was accepted" >&2; (( fails++ ))
else
  print -r -- "  ok   a row split on the wrong separator is rejected"
fi
if _zoo_field "onlyonefield" 2>/dev/null; then
  print -r -- "  FAIL a 1-field row was accepted" >&2; (( fails++ ))
else
  print -r -- "  ok   a 1-field row is rejected"
fi

print -r -- "short rows are dropped, not half-parsed:"
print -r -- "zzz9${US}truncated" > "$FIX/short"
_wantnot "a 2-field row does not become a container" \
  "$(_zoo_rows "$(cat "$FIX/short")")" "truncated"

print -r -- "the background sampler is silent and leaves nothing behind:"
# zoo's teardown removes the sample directory while the detached sampler may still
# be running. That used to print
#   mv: rename /var/.../tmp.XXX.new to /var/.../tmp.XXX: No such file or directory
# on the user's terminal AFTER zoo had exited, and — when the sample landed just
# after the files were deleted — leave an orphan in /tmp. Found by running zoo, not
# by any test here, which is why it is a test here now.
_zoo_stats() { print -r -- "aaa1${US}0.10%${US}12MiB / 31.29GiB${US}0.04%${US}3" }

sd="$(mktemp -d)"
noise="$( _zoo_sample "$sd/stats" 2>&1 )"; rc=$?
if [[ -s "$sd/stats" ]]; then print -r -- "  ok   writes a sample when the dir exists"
else print -r -- "  FAIL wrote no sample" >&2; (( fails++ )); fi
[[ -z "$noise" ]] && print -r -- "  ok   silent on success" \
  || { print -r -- "  FAIL said: $noise" >&2; (( fails++ )); }
[[ ! -e "$sd/stats.new" ]] && print -r -- "  ok   no .new left over" \
  || { print -r -- "  FAIL left a .new behind" >&2; (( fails++ )); }
rm -rf "$sd"

# The race, deterministically: the directory is gone before the sampler runs.
sd2="$(mktemp -d)"; gone="$sd2/stats"; rm -rf "$sd2"
noise2="$( _zoo_sample "$gone" 2>&1 )"
[[ -z "$noise2" ]] && print -r -- "  ok   silent when its directory is gone" \
  || { print -r -- "  FAIL said: $noise2" >&2; (( fails++ )); }
[[ ! -e "$sd2" ]] && print -r -- "  ok   recreated nothing" \
  || { print -r -- "  FAIL recreated $sd2" >&2; (( fails++ )); rm -rf "$sd2"; }

print -r -- "failed query is not an empty one:"
out4="$( docker() { return 1 }
         ZOO_PS_SESSION_SOURCE="" ZOO_PS_MANAGED_SOURCE="" ZOO_STATS_SOURCE="$FIX/empty" \
           zoo --once 2>&1 )"; rc=$?
if (( rc != 0 )); then print -r -- "  ok   exits non-zero"
else print -r -- "  FAIL exited 0 on a failed query" >&2; (( fails++ )); fi
_want "says the query failed"          "$out4" "could not query docker"
_wantnot "does not claim none running" "$out4" "no primates"

if (( fails )); then print -r -- "FAILED ($fails)" >&2; exit 1; fi
print -r -- "PASSED"
