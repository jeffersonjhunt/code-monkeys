#!/usr/bin/env python3
"""
bench.py — concurrent-client throughput benchmark for the spark-cluster.

Hits the HAProxy endpoint (or a single replica) with N concurrent requests.
Discovers the served model id from /v1/models so it works against whatever's
deployed. stdlib only — no external deps.

Usage:
  python3 bench.py [--target HOST:PORT] [--concurrency N] [--requests R] [--max-tokens T]

Defaults: target=starsky:8080, concurrency=8, requests=32, max-tokens=256.
"""

import argparse
import concurrent.futures
import json
import statistics
import sys
import time
import urllib.request


def discover_model(base: str) -> str:
    with urllib.request.urlopen(f"{base}/v1/models", timeout=10) as r:
        return json.load(r)["data"][0]["id"]


def make_request(base: str, model: str, max_tokens: int, prompt: str) -> dict:
    payload = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": 0,
        "stream": False,
    }).encode()
    req = urllib.request.Request(
        f"{base}/v1/chat/completions",
        data=payload,
        headers={"content-type": "application/json"},
    )
    t0 = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            data = json.loads(resp.read())
        t1 = time.monotonic()
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}
    usage = data.get("usage", {})
    completion = usage.get("completion_tokens", 0)
    latency = t1 - t0
    return {
        "ok": True,
        "latency": latency,
        "completion_tokens": completion,
        "prompt_tokens": usage.get("prompt_tokens", 0),
        "tps": completion / latency if latency > 0 else 0,
    }


def percentile(sorted_xs: list, p: float) -> float:
    if not sorted_xs:
        return 0.0
    idx = max(0, min(len(sorted_xs) - 1, int(round(p * (len(sorted_xs) - 1)))))
    return sorted_xs[idx]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", default="starsky:8080")
    ap.add_argument("--concurrency", type=int, default=8)
    ap.add_argument("--requests", type=int, default=32)
    ap.add_argument("--max-tokens", type=int, default=256)
    ap.add_argument("--prompt", default=(
        "Write a Python function that computes the nth Fibonacci number using "
        "memoization. Include type hints, a clear docstring, and a small unit test."
    ))
    ap.add_argument("--warmup", type=int, default=2,
                    help="Discarded warmup requests before timing")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    base = f"http://{args.target}"
    model = discover_model(base)
    if not args.quiet:
        print(f"target      : {base}")
        print(f"model       : {model}")
        print(f"concurrency : {args.concurrency}")
        print(f"requests    : {args.requests}")
        print(f"max_tokens  : {args.max_tokens}")

    if args.warmup > 0:
        if not args.quiet:
            print(f"warmup      : {args.warmup} requests (discarded)...", flush=True)
        for _ in range(args.warmup):
            make_request(base, model, args.max_tokens, args.prompt)

    t_start = time.monotonic()
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        futs = [pool.submit(make_request, base, model, args.max_tokens, args.prompt)
                for _ in range(args.requests)]
        for f in concurrent.futures.as_completed(futs):
            r = f.result()
            results.append(r)
            if not r["ok"] and not args.quiet:
                print(f"  FAIL: {r['error']}", file=sys.stderr)
    t_total = time.monotonic() - t_start

    ok = [r for r in results if r["ok"]]
    if not ok:
        print("all requests failed", file=sys.stderr)
        return 1

    latencies = sorted(r["latency"] for r in ok)
    completion_total = sum(r["completion_tokens"] for r in ok)
    per_req_tps = [r["tps"] for r in ok]

    if not args.quiet:
        print()
    print(
        f"c={args.concurrency:>3}  "
        f"ok={len(ok)}/{len(results)}  "
        f"wall={t_total:6.2f}s  "
        f"req/s={len(ok)/t_total:5.2f}  "
        f"total_tok={completion_total}  "
        f"agg_tok/s={completion_total/t_total:6.1f}  "
        f"p50={percentile(latencies, 0.5):5.2f}s  "
        f"p90={percentile(latencies, 0.9):5.2f}s  "
        f"max={max(latencies):5.2f}s  "
        f"avg_per_req_tok/s={statistics.mean(per_req_tps):5.1f}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
