#!/usr/bin/env python3
"""
AIME 25 runner — sends each of the 30 AIME 2025 problems (AIME I + AIME II)
through an OpenAI-compatible endpoint, extracts the final integer answer
(typically inside \\boxed{}), compares to ground truth, reports score.

Designed to live in the spark-bench primate and run via the `spark-bench`
shim. Defaults to the env vars the shim injects (OPENAI_API_BASE,
OPENAI_API_KEY, SPARK_BENCH_MODEL). Results land under /results/.

Usage:
    spark-bench python /opt/skills/spark-bench/scripts/run-aime25.py \\
        [--n-samples N] [--workers N] [--max-tokens N] [--temperature T] [--top-p P]
"""
import argparse
import datetime as dt
import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import openai
from datasets import load_dataset


PROMPT_TEMPLATE = (
    "Solve the following AIME problem. Show your reasoning step by step, "
    "then put your final integer answer (an integer between 0 and 999) "
    "inside \\boxed{{}}.\n\n"
    "Problem: {problem}\n\n"
)


def extract_answer(text):
    """Pull the final integer answer out of model output.
    Strategy: last \\boxed{N}, else last 'Answer: N', else last integer."""
    if not text:
        return None
    boxed = re.findall(r"\\boxed\{\s*(-?\d+)\s*\}", text)
    if boxed:
        try:
            return int(boxed[-1])
        except ValueError:
            pass
    ans = re.findall(r"(?:final\s+)?answer\s*(?:is|=|:)?\s*\**\s*(-?\d+)", text, re.IGNORECASE)
    if ans:
        try:
            return int(ans[-1])
        except ValueError:
            pass
    ints = re.findall(r"-?\d+", text)
    if ints:
        try:
            return int(ints[-1])
        except ValueError:
            return None
    return None


def normalize_ground_truth(answer):
    """Coerce a dataset answer into an integer. Handles values like '336^\\circ'
    by extracting the first signed integer. Returns None if no integer found
    (the problem will simply never score correct)."""
    if isinstance(answer, int):
        return answer
    s = str(answer).strip()
    m = re.search(r"-?\d+", s)
    return int(m.group(0)) if m else None


def run_one(client, model, problem, n_samples, max_tokens, temperature, top_p):
    """Run a single problem n_samples times; return list of (answer, raw_text, completion_tokens, latency)."""
    out = []
    for _ in range(n_samples):
        t0 = time.time()
        try:
            r = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": PROMPT_TEMPLATE.format(problem=problem)}],
                max_tokens=max_tokens,
                temperature=temperature,
                top_p=top_p,
            )
            content = r.choices[0].message.content or ""
            ans = extract_answer(content)
            out.append((ans, content, r.usage.completion_tokens, time.time() - t0))
        except Exception as e:
            out.append((None, f"ERROR: {type(e).__name__}: {e}", 0, time.time() - t0))
    return out


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--model", default=os.environ.get("SPARK_BENCH_MODEL"))
    p.add_argument("--endpoint", default=os.environ.get("OPENAI_API_BASE"))
    p.add_argument("--api-key", default=os.environ.get("OPENAI_API_KEY", "EMPTY"))
    p.add_argument("--n-samples", type=int, default=1, help="samples per problem (1 = pass@1)")
    p.add_argument("--workers", type=int, default=8, help="concurrent problems in flight")
    p.add_argument("--max-tokens", type=int, default=16384)
    p.add_argument("--temperature", type=float, default=1.0)
    p.add_argument("--top-p", type=float, default=0.95)
    p.add_argument("--results-dir", default="/results")
    p.add_argument("--name", default="aime25", help="run name suffix for output dir")
    args = p.parse_args()

    if not args.model or not args.endpoint:
        sys.exit("error: --model and --endpoint required (or SPARK_BENCH_MODEL + OPENAI_API_BASE env)")

    print(f"endpoint:  {args.endpoint}")
    print(f"model:     {args.model}")
    print(f"samples:   {args.n_samples}/problem   workers: {args.workers}   "
          f"max_tokens: {args.max_tokens}   temp: {args.temperature}   top_p: {args.top_p}")

    print("\nloading AIME 25 dataset...")
    ds_i = load_dataset("opencompass/AIME2025", split="train", data_files="aime2025-I.jsonl")
    ds_ii = load_dataset("opencompass/AIME2025", split="train", data_files="aime2025-II.jsonl")
    problems = [{"id": f"I-{i+1:02d}", **dict(r)} for i, r in enumerate(ds_i)]
    problems += [{"id": f"II-{i+1:02d}", **dict(r)} for i, r in enumerate(ds_ii)]
    print(f"loaded {len(problems)} problems")

    client = openai.OpenAI(base_url=args.endpoint, api_key=args.api_key, timeout=900)

    ts = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    model_slug = re.sub(r"[^A-Za-z0-9._-]", "-", args.model)
    outdir = Path(args.results_dir) / f"{ts}-{model_slug}-{args.name}"
    outdir.mkdir(parents=True, exist_ok=True)
    raw_dir = outdir / "raw"
    raw_dir.mkdir(exist_ok=True)
    print(f"results -> {outdir}\n")

    t0 = time.time()
    results = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {
            pool.submit(run_one, client, args.model, prob["question"],
                        args.n_samples, args.max_tokens, args.temperature, args.top_p): prob
            for prob in problems
        }
        for fut in as_completed(futures):
            prob = futures[fut]
            samples = fut.result()
            correct = normalize_ground_truth(prob["answer"])
            preds = [s[0] for s in samples]
            n_correct = sum(1 for a in preds if a == correct)
            pass_at_1 = n_correct / len(preds) if preds else 0.0
            results.append({
                "id": prob["id"],
                "ground_truth": correct,
                "predictions": preds,
                "n_samples": len(preds),
                "n_correct": n_correct,
                "pass@1": pass_at_1,
                "completion_tokens_avg": sum(s[2] for s in samples) / max(1, len(samples)),
                "latency_avg_s": sum(s[3] for s in samples) / max(1, len(samples)),
            })
            with (raw_dir / f"{prob['id']}.json").open("w") as f:
                json.dump({
                    "problem": dict(prob),
                    "samples": [{"answer": a, "text": t, "completion_tokens": c, "latency_s": lt}
                                for a, t, c, lt in samples],
                }, f, indent=2)
            mark = "OK" if pass_at_1 == 1.0 else ("XX" if pass_at_1 == 0.0 else "~~")
            print(f"  [{prob['id']:>5s}] gt={correct if correct is not None else '?':>3}  preds={preds}  {mark}")

    elapsed = time.time() - t0
    total_correct = sum(r["n_correct"] for r in results)
    total_samples = sum(r["n_samples"] for r in results)
    avg_pass = sum(r["pass@1"] for r in results) / len(results) if results else 0.0

    summary = {
        "model": args.model,
        "endpoint": args.endpoint,
        "benchmark": "AIME 25",
        "n_problems": len(problems),
        "n_samples_per_problem": args.n_samples,
        "n_correct": total_correct,
        "n_total": total_samples,
        "accuracy": total_correct / total_samples if total_samples else 0.0,
        "avg_pass@1": avg_pass,
        "elapsed_seconds": elapsed,
        "temperature": args.temperature,
        "top_p": args.top_p,
        "max_tokens": args.max_tokens,
        "workers": args.workers,
        "timestamp": ts,
    }
    with (outdir / "summary.json").open("w") as f:
        json.dump(summary, f, indent=2)
    with (outdir / "per_problem.json").open("w") as f:
        json.dump(sorted(results, key=lambda r: r["id"]), f, indent=2)

    print()
    print(f"=== AIME 25 ({args.model}) ===")
    print(f"score:    {summary['n_correct']} / {summary['n_total']}  "
          f"({100*summary['accuracy']:.1f}% accuracy, {100*summary['avg_pass@1']:.1f}% avg pass@1)")
    print(f"elapsed:  {elapsed:.1f}s  ({elapsed/len(problems):.1f}s/problem avg)")
    print(f"results:  {outdir}")


if __name__ == "__main__":
    main()
