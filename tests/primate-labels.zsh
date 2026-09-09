#!/usr/bin/env zsh
# tests/primate-labels.zsh — assert primate() and primate-session() label the containers they start.
#
# zoo finds primates by asking docker for a label, never by matching image names against the roster
# (a guess, and the guess is what once let primate-session-kill remove the wrong container). That
# only works if the labels are actually applied, so this asserts the `docker run` each launcher
# builds — without starting anything.
#
# Hermetic: no daemon, no images, no volumes, no TTY, no cleanup. `docker` is shadowed so `run` is
# captured and every other subcommand fails quietly, and the two helpers that reach outside the
# process — _primate_ensure_image (pulls from ECR) and _primate_first_run_sync (seeds a volume) — are
# stubbed. Only argument construction is under test, which is the whole of what labelling is.
#
# The first version of this pinned IMAGE=minion and let the real client through. That passes on a
# machine where minion happens to be local and, on one where it is not, primate() returns at the
# pull and never builds a docker run at all. Caught on intel-nuc by the "nothing was asserted"
# guard below, which is the only reason it did not read as a clean pass.

set -u
ZF="${0:A:h}/../zfuncs"
# Deliberately not a real image: nothing here may depend on what is local to this machine.
IMAGE=zoo-test-not-a-real-image
fails=0

_capture=""
docker() {
  if [[ "${1:-}" == "run" ]]; then
    _capture="$*"
    return 0
  fi
  return 1
}

source "$ZF" >/dev/null 2>&1

# Neither reaches a registry or a volume under test; both would otherwise abort primate() on a
# machine that does not already have the image.
_primate_ensure_image()   { return 0 }
_primate_first_run_sync() { return 0 }

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
