#!/usr/bin/env bash
# smoke-test.sh — verify a vLLM endpoint is serving correctly.
#
# Auto-discovers the served model id from /v1/models, so the script always
# tests whatever is actually deployed — no need to keep model names in sync.
#
# Default target comes from cluster.env ($LB_HOST:$LB_PORT — through HAProxy).
# Bare hostnames get $VLLM_PORT appended for direct-replica testing.
#
# Usage:
#   ./smoke-test.sh                 # → $LB_HOST:$LB_PORT (through HAProxy)
#   ./smoke-test.sh starsky         # → starsky:$VLLM_PORT (direct replica)
#   ./smoke-test.sh host:port       # explicit
#
# Exits non-zero on any failure.

set -euo pipefail

script_dir="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=lib/load-config.sh
. "$script_dir/lib/load-config.sh"

target="${1:-${LB_HOST}:${LB_PORT}}"
if [[ "$target" != *:* ]]; then
  target="$target:$VLLM_PORT"
fi
base="http://$target"

echo ">> [$target] GET /health"
curl -fsS --max-time 10 "$base/health" >/dev/null && echo "OK"

echo ">> [$target] GET /v1/models"
model_id=$(curl -fsS --max-time 10 "$base/v1/models" \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["data"][0]["id"])')
echo "served: $model_id"

echo ">> [$target] POST /v1/chat/completions (model=$model_id)"
# max_tokens generous so reasoning models (Qwen3) have room for both <think> and the final answer.
# `chat_template_kwargs.enable_thinking: false` is the documented way to suppress thinking on
# Qwen3 — most chat templates honor it; if not, the parser still puts the thought in `reasoning`.
resp=$(curl -fsS --max-time 60 "$base/v1/chat/completions" \
  -H 'content-type: application/json' \
  -d "{\"model\":\"$model_id\",\"messages\":[{\"role\":\"user\",\"content\":\"reply with exactly one word: hello\"}],\"max_tokens\":256,\"temperature\":0,\"chat_template_kwargs\":{\"enable_thinking\":false}}")
echo "$resp" | python3 -c 'import json,sys
m=json.load(sys.stdin)["choices"][0]["message"]
out=m.get("content") or m.get("reasoning") or "<empty>"
print("response:", out.strip().splitlines()[0][:80] if out!="<empty>" else out)'

echo "PASS"
