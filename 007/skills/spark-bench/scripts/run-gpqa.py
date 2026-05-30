#!/usr/bin/env python3
"""
GPQA Diamond runner — sends each GPQA Diamond multiple-choice question
(graduate-level physics/chemistry/biology, 198 total) through an
OpenAI-compatible endpoint, extracts the boxed letter (A/B/C/D), compares
to ground truth, reports score.

Uses the ungated mirror `di-zhang-fdu/gpqa_diamond_multi_choice` since the
canonical `Idavidrein/gpqa` is gated and requires a per-user signed terms
acceptance. The mirror is the same set, pre-randomized choice order, with
the answer encoded as a single letter.

Defaults to a 50-question subset; pass --n 0 (or --n 198) for the full set.

Usage:
    spark-bench python /opt/skill/scripts/run-gpqa.py \\
        [--n N] [--workers N] [--max-tokens N] [--temperature T] [--top-p P]
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


def extract_letter(text):
    """Pull the boxed letter (A/B/C/D) out of model output.
    Strategy: last \\boxed{X}, else last 'Answer: X', else last bare letter."""
    if not text:
        return None
    boxed = re.findall(r"\\boxed\{\s*\(?\s*([A-D])\s*\)?\s*\}", text, re.IGNORECASE)
    if boxed:
        return boxed[-1].upper()
    ans = re.findall(r"(?:final\s+)?answer\s*(?:is|=|:)?\s*\**\s*\(?\s*([A-D])\s*\)?\s*\**", text, re.IGNORECASE)
    if ans:
        return ans[-1].upper()
    letters = re.findall(r"\b([A-D])\b", text)
    if letters:
        return letters[-1].upper()
    return None


def run_one(client, model, question, n_samples, max_tokens, temperature, top_p):
    out = []
    for _ in range(n_samples):
        t0 = time.time()
        try:
            r = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": question}],
                max_tokens=max_tokens,
                temperature=temperature,
                top_p=top_p,
            )
            content = r.choices[0].message.content or ""
            ans = extract_letter(content)
            out.append((ans, content, r.usage.completion_tokens, time.time() - t0))
        except Exception as e:
            out.append((None, f"ERROR: {type(e).__name__}: {e}", 0, time.time() - t0))
    return out


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--model", default=os.environ.get("SPARK_BENCH_MODEL"))
    p.add_argument("--endpoint", default=os.environ.get("OPENAI_API_BASE"))
    p.add_argument("--api-key", default=os.environ.get("OPENAI_API_KEY", "EMPTY"))
    p.add_argument("--n", type=int, default=50, help="number of questions (0 = all 198)")
    p.add_argument("--n-samples", type=int, default=1, help="samples per question (1 = pass@1)")
    p.add_argument("--workers", type=int, default=8)
    p.add_argument("--max-tokens", type=int, default=16384)
    p.add_argument("--temperature", type=float, default=0.7)
    p.add_argument("--top-p", type=float, default=1.0)
    p.add_argument("--results-dir", default="/results")
    p.add_argument("--name", default="gpqa-diamond")
    p.add_argument("--seed", type=int, default=0, help="seed for the subset selection (reproducible)")
    args = p.parse_args()

    if not args.model or not args.endpoint:
        sys.exit("error: --model and --endpoint required (or SPARK_BENCH_MODEL + OPENAI_API_BASE env)")

    print(f"endpoint:  {args.endpoint}")
    print(f"model:     {args.model}")
    print(f"samples:   {args.n_samples}/question   workers: {args.workers}   "
          f"max_tokens: {args.max_tokens}   temp: {args.temperature}   top_p: {args.top_p}")

    print("\nloading GPQA Diamond (di-zhang-fdu/gpqa_diamond_multi_choice)...")
    ds = load_dataset("di-zhang-fdu/gpqa_diamond_multi_choice", split="train")
    if args.n and args.n < len(ds):
        # Reproducible subset selection by seed-based permutation
        import random
        rng = random.Random(args.seed)
        indices = rng.sample(range(len(ds)), args.n)
        problems = [{"idx": i, **dict(ds[i])} for i in indices]
        print(f"loaded {len(ds)} questions, selected subset of {len(problems)} (seed={args.seed})")
    else:
        problems = [{"idx": i, **dict(ds[i])} for i in range(len(ds))]
        print(f"loaded {len(problems)} questions (full set)")

    client = openai.OpenAI(base_url=args.endpoint, api_key=args.api_key, timeout=1700)

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
            correct = str(prob["answer"]).strip().upper()
            preds = [s[0] for s in samples]
            n_correct = sum(1 for a in preds if a == correct)
            pass_at_1 = n_correct / len(preds) if preds else 0.0
            results.append({
                "idx": prob["idx"],
                "ground_truth": correct,
                "predictions": preds,
                "n_samples": len(preds),
                "n_correct": n_correct,
                "pass@1": pass_at_1,
                "completion_tokens_avg": sum(s[2] for s in samples) / max(1, len(samples)),
                "latency_avg_s": sum(s[3] for s in samples) / max(1, len(samples)),
            })
            with (raw_dir / f"q{prob['idx']:03d}.json").open("w") as f:
                json.dump({
                    "problem": {k: v for k, v in prob.items() if k != "question"},
                    "question": prob["question"],
                    "samples": [{"answer": a, "text": t, "completion_tokens": c, "latency_s": lt}
                                for a, t, c, lt in samples],
                }, f, indent=2)
            mark = "OK" if pass_at_1 == 1.0 else ("XX" if pass_at_1 == 0.0 else "~~")
            print(f"  [q{prob['idx']:03d}] gt={correct}  preds={preds}  {mark}")

    elapsed = time.time() - t0
    total_correct = sum(r["n_correct"] for r in results)
    total_samples = sum(r["n_samples"] for r in results)
    avg_pass = sum(r["pass@1"] for r in results) / len(results) if results else 0.0

    summary = {
        "model": args.model,
        "endpoint": args.endpoint,
        "benchmark": "GPQA Diamond",
        "dataset": "di-zhang-fdu/gpqa_diamond_multi_choice (ungated mirror of Idavidrein/gpqa diamond split)",
        "n_problems": len(problems),
        "subset_seed": args.seed if args.n and args.n < 198 else None,
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
        json.dump(sorted(results, key=lambda r: r["idx"]), f, indent=2)

    print()
    print(f"=== GPQA Diamond ({args.model}) ===")
    print(f"score:    {summary['n_correct']} / {summary['n_total']}  "
          f"({100*summary['accuracy']:.1f}% accuracy, {100*summary['avg_pass@1']:.1f}% avg pass@1)")
    print(f"elapsed:  {elapsed:.1f}s  ({elapsed/len(problems):.1f}s/question avg)")
    print(f"results:  {outdir}")


if __name__ == "__main__":
    main()
