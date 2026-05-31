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
    ap.add_argument("--agent-config", default="config/default.yaml",
                    help="SWE-agent config (path resolved relative to /opt/sweagent)")
    ap.add_argument("--results-dir", default="/results")
    ap.add_argument("--name", default=None)
    ap.add_argument("--temperature", type=float, default=0.0,
                    help="0.0 matches GLM-4.7-Flash card SWE-Bench eval params")
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

    cmd = [
        sweagent_bin, "run-batch",
        "--instances.type", "swe_bench",
        "--instances.subset", args.subset,
        "--instances.split", args.split,
        "--instances.slice", slice_arg,
        "--instances.shuffle=True",
        "--instances.evaluate=True",
        "--instances.deployment.docker_args=--privileged",
        "--config", cfg,
        "--agent.model.name", f"openai/{args.spark_model}",
        "--agent.model.api_base", args.endpoint,
        "--agent.model.completion_kwargs", f'{{"temperature": {args.temperature}}}',
        "--num_workers", str(args.workers),
        "--output_dir", str(outdir),
    ] + passthrough

    print(f"[run-swebench] cmd={' '.join(cmd)}")
    rc = subprocess.run(cmd).returncode
    print(f"[run-swebench] exit {rc}")
    sys.exit(rc)


if __name__ == "__main__":
    main()
