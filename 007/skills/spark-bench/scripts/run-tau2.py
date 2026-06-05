#!/usr/bin/env python3
"""
τ²-Bench runner — wraps the `tau2 run` CLI for our spark-cluster setup.

tau2 uses LiteLLM under the hood for LLM dispatch. To target a local
OpenAI-compatible endpoint (our vLLM via HAProxy), pass the model name as
`openai/<served-model-name>` and rely on OPENAI_BASE_URL / OPENAI_API_KEY in
env — both are set by the `bin/spark-bench` shim.

tau2 has THREE LLM call sites beyond the agent and user-sim, all hardcoded
in `tau2/config.py`:
  - `DEFAULT_LLM_NL_ASSERTIONS` (gpt-4.1-2025-04-14) — used by the
    NLAssertionsEvaluator to grade whether user transcripts satisfy task
    natural-language constraints. This is the main reason our tau2 numbers
    were undermeasured (litellm.NotFoundError on every task that has NL
    assertions, which is most retail tasks).
  - `DEFAULT_LLM_ENV_INTERFACE` (gpt-4.1-2025-04-14) — used by the
    InterfaceAgent inside the environment.
  - `DEFAULT_LLM_EVAL_USER_SIMULATOR` (claude-opus-4-5) — the optional
    `--auto-review` judge. We don't enable auto-review, so this one doesn't
    fire today.

There's no CLI flag for any of these. This wrapper monkey-patches the first
two to our agent model BEFORE importing tau2.cli so the runtime picks them
up. By default the judge model is the agent model itself (self-grading, but
internally consistent); pass `--judge-llm openai/some-other-model` to use a
different endpoint.

For the user simulator we use the same model by default (we only have one
model served at a time).

Defaults:
  --domain retail        (the most common tau2 domain)
  --num-tasks 20         (subset)
  --max-steps 30         (per task)
  agent-llm = user-llm = judge-llm = openai/$SPARK_BENCH_MODEL

Usage:
    spark-bench python /opt/skill/scripts/run-tau2.py \\
        [--domain DOMAIN] [--num-tasks N] [--judge-llm MODEL] [-- ...other tau2 run flags]
"""
import argparse
import datetime as dt
import os
import sys
from pathlib import Path


def patch_tau2_judge_model(judge_llm: str, judge_temp: float):
    """Override tau2's hardcoded gpt-4.1 defaults for NL assertions + env
    interface. Must be called BEFORE any `tau2.cli` import so that downstream
    `from tau2.config import DEFAULT_LLM_NL_ASSERTIONS` bindings pick up the
    new value.

    Why both:
      - NLAssertionsEvaluator (tau2/evaluator/evaluator_nl_assertions.py:122)
        uses DEFAULT_LLM_NL_ASSERTIONS to LLM-check natural-language
        assertions on retail/airline tasks. Without this patch every retail
        task with NL assertions fails the assertion check with
        litellm.NotFoundError, which silently undermeasures rewards.
      - InterfaceAgent (tau2/environment/utils/interface_agent.py:37) uses
        DEFAULT_LLM_ENV_INTERFACE to drive environment-side LLM calls. Fewer
        tasks hit this but the failure mode is the same.
    """
    from tau2 import config as tau2_config
    tau2_config.DEFAULT_LLM_NL_ASSERTIONS = judge_llm
    tau2_config.DEFAULT_LLM_NL_ASSERTIONS_TEMPERATURE = judge_temp
    tau2_config.DEFAULT_LLM_NL_ASSERTIONS_ARGS = {"temperature": judge_temp}
    tau2_config.DEFAULT_LLM_ENV_INTERFACE = judge_llm
    tau2_config.DEFAULT_LLM_ENV_INTERFACE_TEMPERATURE = judge_temp
    tau2_config.DEFAULT_LLM_ENV_INTERFACE_ARGS = {"temperature": judge_temp}


def main():
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("--spark-model", default=os.environ.get("SPARK_BENCH_MODEL", "qwen3-coder-next"))
    ap.add_argument("--domain", default="retail")
    ap.add_argument("--num-tasks", type=int, default=20)
    ap.add_argument("--max-steps", type=int, default=30)
    ap.add_argument("--temperature", type=float, default=0.0,
                    help="tau2-bench eval default is 0 per GLM-4.7-Flash card")
    ap.add_argument("--judge-llm", default=None,
                    help="Override the LLM used for NL assertions + env interface. "
                         "Pass as e.g. 'openai/gpt-4o' or 'openai/<our-model>'. "
                         "Default: same as the agent model (self-grading; "
                         "internally consistent but absolute scores will be lower "
                         "than what a stronger judge would award).")
    ap.add_argument("--judge-temperature", type=float, default=0.0)
    ap.add_argument("--results-dir", default="/results")
    ap.add_argument("--name", default=None,
                    help="output subdir name (default: <model>-tau2-<domain>)")
    ap.add_argument("-h", "--help", action="store_true")
    args, passthrough = ap.parse_known_args()

    if args.help:
        print(__doc__)
        print()
        print("---")
        sys.argv = ["tau2", "run", "--help"]
        from tau2.cli import main as tau2_main
        return tau2_main()

    agent_llm = f"openai/{args.spark_model}"
    judge_llm = args.judge_llm or agent_llm

    # Patch BEFORE the tau2.cli import so downstream `from tau2.config import
    # DEFAULT_LLM_NL_ASSERTIONS` bindings see the new value.
    patch_tau2_judge_model(judge_llm, args.judge_temperature)

    llm_args = '{"temperature": ' + str(args.temperature) + '}'

    ts = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    name = args.name or f"{args.spark_model}-tau2-{args.domain}"
    outdir = Path(args.results_dir) / f"{ts}-{name}"
    outdir.mkdir(parents=True, exist_ok=True)
    print(f"[run-tau2] results -> {outdir}")
    print(f"[run-tau2] agent_llm = user_llm = {agent_llm}")
    print(f"[run-tau2] judge_llm (NL assertions + env interface) = {judge_llm}")

    cli_argv = [
        "tau2", "run",
        "--domain", args.domain,
        "--agent-llm", agent_llm,
        "--agent-llm-args", llm_args,
        "--user-llm", agent_llm,
        "--user-llm-args", llm_args,
        "--num-tasks", str(args.num_tasks),
        "--max-steps", str(args.max_steps),
        "--auto-resume",
    ] + passthrough

    os.chdir(outdir)
    print(f"[run-tau2] cwd={os.getcwd()}")
    print(f"[run-tau2] argv={cli_argv}")

    sys.argv = cli_argv
    from tau2.cli import main as tau2_main
    rc = tau2_main()
    print(f"[run-tau2] exit {rc}")
    sys.exit(rc if rc else 0)


if __name__ == "__main__":
    main()
