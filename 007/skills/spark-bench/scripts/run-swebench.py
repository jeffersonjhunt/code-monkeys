#!/usr/bin/env python3
"""
SWE-Bench Verified runner — wraps `sweagent run-batch` with our cluster
endpoint, sensible defaults, and a /results-mounted output dir.

LiteLLM provider naming: pass --agent-llm-name `openai/<served-model-name>`
and the existing OPENAI_BASE_URL / OPENAI_API_KEY env vars (set by the
spark-bench shim) route requests to our vLLM endpoint.

SWE-Bench Verified is 500 problems. Each problem spawns a per-instance
testbed Docker container locally (`swebench/sweb.eval.x86_64.*`, x86 only)
that SWE-agent drives end-to-end. On intel-nuc (4 cores) with workers=1
this takes hours per 20-problem subset; the full 500-problem set is a
multi-day commitment.

Defaults:
  --n 20         (subset)
  --workers 1    (4-core box, sandbox-heavy)
  --shuffle      (fixed seed)
  --agent-config config/default.yaml  (SWE-agent's default)

Usage:
    spark-bench python /opt/skill/scripts/run-swebench.py \\
        [--n N] [--workers N] [--split test|dev] [-- ...sweagent flags]
"""
import argparse
import datetime as dt
import os
import re
import subprocess
import sys
from pathlib import Path


def main():
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("--spark-model", default=os.environ.get("SPARK_BENCH_MODEL", "qwen3-coder-next"))
    ap.add_argument("--endpoint", default=os.environ.get("OPENAI_API_BASE"))
    ap.add_argument("--n", type=int, default=20, help="number of problems (0 for all 500)")
    ap.add_argument("--workers", type=int, default=1, help="concurrent problems (keep low on 4-core box)")
    ap.add_argument("--split", default="test", help="swebench split: test (canonical Verified) or dev")
    ap.add_argument("--subset", default="verified", help="swebench subset: verified | lite | full | multimodal")
    ap.add_argument("--agent-config", default="config/default_backticks.yaml",
                    help="SWE-agent config (relative to /opt/sweagent). Default is "
                         "default_backticks.yaml — its parse_function=thought_action "
                         "works with models LiteLLM doesn't auto-detect as supporting "
                         "function calling (which is our locally-served vLLM endpoint). "
                         "Use default.yaml if your model name is in LiteLLM's "
                         "function-calling allowlist.")
    ap.add_argument("--results-dir", default="/results")
    ap.add_argument("--name", default=None)
    # NOTE: temperature is set inside the agent config (default 0.0); passing
    # it via --agent.model.completion_kwargs collides with sweagent's own
    # kwarg, producing `litellm.main.completion() got multiple values for
    # keyword argument 'temperature'`. To change temperature, edit the
    # agent config or fork it.
    ap.add_argument("-h", "--help", action="store_true")
    args, passthrough = ap.parse_known_args()

    if args.help:
        print(__doc__)
        print()
        print("---")
        subprocess.run(["/opt/miniforge3/envs/spark-bench-env/bin/sweagent", "run-batch", "--help"])
        return

    ts = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    model_slug = re.sub(r"[^A-Za-z0-9._-]", "-", args.spark_model)
    name = args.name or f"{model_slug}-swebench-{args.subset}"
    outdir = Path(args.results_dir) / f"{ts}-{name}"
    outdir.mkdir(parents=True, exist_ok=True)
    print(f"[run-swebench] results -> {outdir}")

    sweagent_bin = "/opt/miniforge3/envs/spark-bench-env/bin/sweagent"
    slice_arg = f":{args.n}" if args.n > 0 else ":"

    # Resolve agent-config relative to /opt/sweagent
    cfg = args.agent_config
    if not cfg.startswith("/"):
        cfg = f"/opt/sweagent/{cfg}"

    # NOTE: --instances.evaluate=True is intentionally OMITTED. That hook
    # auto-runs `sb-cli submit` which uploads predictions to the SWE-bench
    # leaderboard API; we want local scoring instead. After predictions
    # complete we invoke `swebench.harness.run_evaluation` directly below.
    cmd = [
        sweagent_bin, "run-batch",
        "--instances.type", "swe_bench",
        "--instances.subset", args.subset,
        "--instances.split", args.split,
        "--instances.slice", slice_arg,
        "--instances.shuffle=True",
        "--instances.deployment.docker_args=--privileged",
        "--config", cfg,
        "--agent.model.name", f"openai/{args.spark_model}",
        "--agent.model.api_base", args.endpoint,
        "--num_workers", str(args.workers),
        "--output_dir", str(outdir),
    ] + passthrough

    print(f"[run-swebench] generate predictions: {' '.join(cmd)}")
    rc = subprocess.run(cmd).returncode
    print(f"[run-swebench] generation exit {rc}")
    if rc != 0:
        sys.exit(rc)

    preds_path = outdir / "preds.json"
    if not preds_path.exists():
        print(f"[run-swebench] WARNING: {preds_path} does not exist; cannot evaluate")
        sys.exit(2)

    # Local evaluation via swebench harness: runs the per-instance testbed
    # containers (swebench/sweb.eval.x86_64.*) against the predictions and
    # writes a report file alongside.
    subset_dataset = {
        "verified": "SWE-bench/SWE-bench_Verified",
        "lite":     "SWE-bench/SWE-bench_Lite",
        "full":     "SWE-bench/SWE-bench",
        "multimodal": "SWE-bench/SWE-bench_Multimodal",
    }.get(args.subset, "SWE-bench/SWE-bench_Verified")

    py_bin = "/opt/miniforge3/envs/spark-bench-env/bin/python"
    eval_cmd = [
        py_bin, "-m", "swebench.harness.run_evaluation",
        "--dataset_name", subset_dataset,
        "--split", args.split,
        "--predictions_path", str(preds_path),
        "--max_workers", str(args.workers),
        "--run_id", outdir.name,
        "--report_dir", str(outdir),
    ]
    print(f"[run-swebench] evaluate locally: {' '.join(eval_cmd)}")
    eval_rc = subprocess.run(eval_cmd, cwd=outdir).returncode
    print(f"[run-swebench] eval exit {eval_rc}")
    sys.exit(eval_rc)


if __name__ == "__main__":
    main()
