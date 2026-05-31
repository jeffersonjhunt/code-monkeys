#!/usr/bin/env python3
"""
τ²-Bench runner — wraps the `tau2 run` CLI for our spark-cluster setup.

tau2 uses LiteLLM under the hood for LLM dispatch. To target a local
OpenAI-compatible endpoint (our vLLM via HAProxy), pass the model name as
`openai/<served-model-name>` and rely on OPENAI_BASE_URL / OPENAI_API_KEY in
env — both are set by the `bin/spark-bench` shim.

For the user simulator we use the same model by default (we only have one
model served at a time). The model card eval setups typically use a separate
user-simulator model; downgrade-and-rerun is left as a future option.

Defaults:
  --domain retail        (the most common tau2 domain)
  --num-tasks 20         (subset)
  --max-steps 30         (per task)
  agent-llm = user-llm = openai/$SPARK_BENCH_MODEL

Usage:
    spark-bench python /opt/skill/scripts/run-tau2.py \\
        [--domain DOMAIN] [--num-tasks N] [-- ...other tau2 run flags]
"""
import argparse
import datetime as dt
import os
import subprocess
import sys
from pathlib import Path


def main():
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("--spark-model", default=os.environ.get("SPARK_BENCH_MODEL", "qwen3-coder-next"))
    ap.add_argument("--domain", default="retail")
    ap.add_argument("--num-tasks", type=int, default=20)
    ap.add_argument("--max-steps", type=int, default=30)
    ap.add_argument("--temperature", type=float, default=0.0,
                    help="tau2-bench eval default is 0 per GLM-4.7-Flash card")
    ap.add_argument("--results-dir", default="/results")
    ap.add_argument("--name", default=None,
                    help="output subdir name (default: <model>-tau2-<domain>)")
    ap.add_argument("-h", "--help", action="store_true")
    args, passthrough = ap.parse_known_args()

    if args.help:
        print(__doc__)
        print()
        print("---")
        subprocess.run(["tau2", "run", "--help"])
        return

    llm = f"openai/{args.spark_model}"
    llm_args = '{"temperature": ' + str(args.temperature) + '}'

    ts = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    name = args.name or f"{args.spark_model}-tau2-{args.domain}"
    outdir = Path(args.results_dir) / f"{ts}-{name}"
    outdir.mkdir(parents=True, exist_ok=True)
    print(f"[run-tau2] results -> {outdir}")

    # Full path: subprocess does not inherit the conda env's PATH when
    # invoked from a script started via /opt/.../bin/python directly.
    tau2_bin = "/opt/miniforge3/envs/spark-bench-env/bin/tau2"
    cmd = [
        tau2_bin, "run",
        "--domain", args.domain,
        "--agent-llm", llm,
        "--agent-llm-args", llm_args,
        "--user-llm", llm,
        "--user-llm-args", llm_args,
        "--num-tasks", str(args.num_tasks),
        "--max-steps", str(args.max_steps),
        "--auto-resume",
    ] + passthrough

    # tau2 writes results under cwd (it has its own output layout); chdir
    # into outdir so everything lands in the bind-mounted /results subdir.
    os.chdir(outdir)
    print(f"[run-tau2] cwd={os.getcwd()}")
    print(f"[run-tau2] cmd={' '.join(cmd)}")
    rc = subprocess.run(cmd).returncode
    print(f"[run-tau2] exit {rc}")
    sys.exit(rc)


if __name__ == "__main__":
    main()
