#!/usr/bin/env python3
"""
LiveCodeBench v6 runner — wraps lcb_runner.runner.main with two patches:
  1. Registers our spark-cluster model (default: qwen3-coder-next) in LCB's
     hard-coded LanguageModelList as an OpenAIChat-style model so the existing
     OpenAI client path is used.
  2. Chdir's to /opt/livecodebench before invoking main, because lcb_runner
     looks up prompt files via relative paths (./lcb_runner/prompts/...).

Defaults run a 30-problem subset of the v6 codegeneration scenario with
--evaluate (executes generated code in subprocess sandboxes locally on the
bench host). Pass --n 0 for the full ~300-problem set.

Usage:
    spark-bench python /opt/skill/scripts/run-lcb.py \\
        [--n N] [--release_version release_v6] [--scenario codegeneration]
        [-- ... any other lcb_runner.runner.main flags]
"""
import argparse
import datetime as dt
import os
import shutil
import sys
from pathlib import Path


def register_spark_model(model_name: str):
    """Inject our cluster model into lcb_runner's hard-coded LanguageModelList
    AND LanguageModelStore (the dict is built at import time from the list, so
    appending to the list alone doesn't propagate)."""
    from lcb_runner import lm_styles
    if model_name in lm_styles.LanguageModelStore:
        return
    lm = lm_styles.LanguageModel(
        model_name=model_name,
        model_repr=model_name,
        model_style=lm_styles.LMStyle.OpenAIChat,
        release_date=dt.datetime(2026, 5, 8),
        link=None,
    )
    lm_styles.LanguageModelList.append(lm)
    lm_styles.LanguageModelStore[model_name] = lm


def main():
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("--spark-model", default=os.environ.get("SPARK_BENCH_MODEL", "qwen3-coder-next"),
                    help="cluster-served model name to register in lcb_runner (default from $SPARK_BENCH_MODEL)")
    ap.add_argument("--lcb-dir", default="/opt/livecodebench",
                    help="path to the LiveCodeBench source clone (cwd for relative prompt paths)")
    ap.add_argument("-h", "--help", action="store_true")
    # Parse only our wrapper-specific flags; the rest fall through to lcb_runner
    args, passthrough = ap.parse_known_args()

    if args.help:
        print(__doc__)
        print()
        os.chdir(args.lcb_dir)
        # Show LCB's own help so users see all options
        sys.argv = ["lcb_runner.runner.main", "--help"]
        from lcb_runner.runner import main as lcb_main
        lcb_main.main()
        return

    register_spark_model(args.spark_model)

    # If no --model was passed through, supply it (the LCB default points at a
    # different model that isn't in our endpoint).
    if not any(a == "--model" or a.startswith("--model=") for a in passthrough):
        passthrough = ["--model", args.spark_model] + passthrough

    # LCB-side defaults sensible for our setup if not overridden
    def has(flag):
        return any(a == flag or a.startswith(flag + "=") for a in passthrough)
    defaults = []
    if not has("--scenario"):
        defaults += ["--scenario", "codegeneration"]
    if not has("--release_version"):
        defaults += ["--release_version", "release_v6"]
    if not has("--evaluate"):
        defaults += ["--evaluate"]
    if not has("--n"):
        defaults += ["--n", "1"]
    if not has("--max_tokens"):
        defaults += ["--max_tokens", "16384"]
    if not has("--multiprocess"):
        defaults += ["--multiprocess", "8"]
    passthrough = defaults + passthrough

    # LCB writes to `./output/<model_repr>/...` relative to cwd. Replace the
    # in-image `output/` with a symlink to a bind-mounted /results subdir so
    # generations + eval results persist across `--rm` container exits.
    results_lcb = Path("/results/lcb-runs")
    results_lcb.mkdir(parents=True, exist_ok=True)
    in_image_output = Path(args.lcb_dir) / "output"
    if in_image_output.is_symlink():
        in_image_output.unlink()
    elif in_image_output.exists():
        shutil.rmtree(in_image_output)
    in_image_output.symlink_to(results_lcb)
    print(f"[run-lcb] output -> {results_lcb}")

    os.chdir(args.lcb_dir)
    sys.argv = ["lcb_runner.runner.main"] + passthrough
    print(f"[run-lcb] cwd={os.getcwd()}")
    print(f"[run-lcb] argv={sys.argv}")
    from lcb_runner.runner import main as lcb_main
    lcb_main.main()


if __name__ == "__main__":
    main()
