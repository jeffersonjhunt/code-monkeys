#!/usr/bin/env zsh
# tests/primate-labels.zsh — assert primate() and primate-session() label the containers they start.
#
# zoo finds primates by asking docker for a label, never by matching image names against the roster
# (a guess, and the guess is what once let primate-session-kill remove the wrong container). That
# only works if the labels are actually applied, so this asserts the `docker run` each launcher
# builds — without starting anything.
#
# `docker` is shadowed by a function that captures `run` and passes every other subcommand through
# to the real client, so image/volume/inspect lookups behave normally and only the launch is faked.
# That means this runs anywhere the repo is checked out: no TTY, no daemon-side mounts, no cleanup.

set -u
ZF="${0:A:h}/../zfuncs"
IMAGE=minion
fails=0

_capture=""
docker() {
  if [[ "${1:-}" == "run" ]]; then
    _capture="$*"
    return 0
  fi
  command docker "$@"
}

source "$ZF" >/dev/null 2>&1

_check() {  # _check <description> <needle>
  if [[ "$_capture" == *"$2"* ]]; then
    print -r -- "  ok   $1"
  else
    print -r -- "  FAIL $1 — expected: $2" >&2
    (( fails++ ))
  fi
}

print -r -- "primate() labels:"
_capture=""
primate "$IMAGE" --no-workspace >/dev/null 2>&1
if [[ -z "$_capture" ]]; then
  print -r -- "  FAIL primate() never reached docker run — nothing was asserted" >&2
  (( fails++ ))
else
  _check "carries primate.managed"        "--label primate.managed"
  _check "carries primate.image=$IMAGE"   "--label primate.image=$IMAGE"
fi

print -r -- "primate-session() labels:"
_capture=""
primate-session "$IMAGE" zoo-label-test --no-workspace >/dev/null 2>&1
if [[ -z "$_capture" ]]; then
  print -r -- "  FAIL primate-session() never reached docker run — nothing was asserted" >&2
  (( fails++ ))
else
  _check "carries primate.managed"                 "--label primate.managed"
  _check "keeps primate.session"                   "--label primate.session"
  _check "keeps primate.image=$IMAGE"              "--label primate.image=$IMAGE"
  _check "keeps primate.name=zoo-label-test"       "--label primate.name=zoo-label-test"
fi

if (( fails )); then
  print -r -- "FAILED ($fails)" >&2
  exit 1
fi
print -r -- "PASSED"
