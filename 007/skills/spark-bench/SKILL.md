---
name: spark-bench
description: Run LLM evaluation harnesses (AIME 25, GPQA, LiveCodeBench v6, tau2-bench, SWE-Bench Verified via SWE-agent) against the spark-cluster from a dedicated x86 bench host (intel-nuc.tworivers). The harness runs in the spark-bench primate; only the OpenAI-compatible endpoint URL needs to change between baseline (cluster LB) and test (ad-hoc model server) runs.
license: Apache-2.0
metadata:
  author: ooe
  version: "1.0"
---

# spark-bench

Benchmark orchestration for the spark-cluster.

Three things matter and the rest follows:

1. **Bench host is x86** (intel-nuc.tworivers). SWE-Bench's testbed Docker images are published as `swebench/sweb.eval.x86_64.*` — they qemu-emulate badly on aarch64. The bench harness runs here; vLLM stays on the GPU cluster (hutch / starsky).
2. **Bench host needs the host Docker daemon** for SWE-Bench's sandbox spawning. Pattern is Docker-out-of-Docker — mount `/var/run/docker.sock`, add the matching group GID. The `spark-bench` wrapper does this automatically.
3. **Endpoint URL switches the model under test.** Default points at the cluster LB (`http://starsky.tworivers:8080/v1`, currently serving `qwen3-coder-next`). Override `VLLM_BASE_URL` and `SPARK_BENCH_MODEL` to point at any other OpenAI-compatible endpoint (e.g. an ad-hoc `vllm serve` on `http://hutch.tworivers:8001/v1`).

## When to Use

- Establishing a baseline before swapping a served model.
- A/B-testing a candidate model against the production pin.
- One-off bench runs (single harness, single model) for investigations.

Do NOT use for:
- Training/fine-tuning (this image only orchestrates evals, no GPU).
- Running anything on the bench host that needs CUDA — intel-nuc is CPU-only.

## Prerequisites

- Passwordless SSH to `intel-nuc.tworivers` as `jhunt`, with NOPASSWD sudo.
- `codemonkey:latest`, `miniforge3:latest`, `spark-bench:latest` built on the bench host (see [Build](#build)).
- Cluster reachable from bench host (`curl http://starsky.tworivers:8080/v1/models` returns JSON).
- The `bin/spark-bench` workstation shim on PATH (the `setup` script symlinks this into `~/.local/bin/` automatically).

## Build

The spark-bench primate extends `miniforge3` which extends `codemonkey`. Build all three on the bench host (intel-nuc), in order:

```bash
ssh jhunt@intel-nuc.tworivers '
  cd ~/Source/Edda/code-monkeys/primates
  sudo make codemonkey.build FRESH=false   # ~4 min  (skip freshclam)
  sudo make miniforge3.build               # ~1 min
  sudo make spark-bench.build              # ~10-15 min (harness installs)
'
```

`FRESH=false` skips the ClamAV signature update during codemonkey's build — saves ~10-15 min and is fine for a bench host that never sees external content.

## Usage

The `spark-bench` shim on the workstation runs commands inside the spark-bench primate on intel-nuc, with the cluster endpoint pre-wired:

```bash
# Interactive shell inside the container (default endpoint = cluster LB)
spark-bench

# One-shot: hello completion smoke test
spark-bench python -c '
import os, openai
c = openai.OpenAI(base_url=os.environ["OPENAI_API_BASE"], api_key=os.environ["OPENAI_API_KEY"])
r = c.chat.completions.create(
    model=os.environ["SPARK_BENCH_MODEL"],
    messages=[{"role": "user", "content": "Say hello in one word."}],
    max_tokens=8,
)
print(r.choices[0].message.content)
'

# Point at the GLM test endpoint instead of the cluster LB
VLLM_BASE_URL=http://hutch.tworivers:8001/v1 SPARK_BENCH_MODEL=glm-4.7-flash \
  spark-bench python -c '...'
```

Results land in `/results/` inside the container, which is bind-mounted from `~/spark-bench/results/` on the bench host. Cache (HF datasets, SWE-Bench testbed metadata, pip cache) lives at `/cache/` → `~/spark-bench/cache/`.

## Harness Invocations

All commands assume `spark-bench` shim on PATH; replace `VLLM_BASE_URL` + `SPARK_BENCH_MODEL` to switch endpoints.

### AIME 25 (math, 30 problems, ~30 min)

```bash
spark-bench python -m <runner>
```

*(harness runner TBD — likely a custom 30-problem script vs lighteval; pin once first run validates.)*

### GPQA Diamond (no tools, 198 questions, ~1 h)

```bash
spark-bench python -m <runner>
```

### LiveCodeBench v6

```bash
spark-bench python -m lcb_runner.runner.main --model "$SPARK_BENCH_MODEL" --scenario codegeneration
```

### tau2-bench

```bash
spark-bench python -m tau2.run --domain retail --num_tasks 20 --model "$SPARK_BENCH_MODEL"
```

### SWE-Bench Verified (via SWE-agent)

```bash
spark-bench sweagent run-batch \
  --instances.type swe_bench --instances.subset verified --instances.split test \
  --instances.shuffle=True --instances.evaluate=True --instances.deployment.docker_args=--privileged \
  --agent.model.name "openai/$SPARK_BENCH_MODEL" --agent.model.api_base "$OPENAI_API_BASE" \
  --num_workers 1
```

(`--num_workers 1` because intel-nuc has 4 cores; bumping to 2 is OK but expect saturation. Full Verified set on intel-nuc serial ≈ 2-3 days; use `--instances.slice=:20` for a subset first.)

## Recovery / Common Pitfalls

- **`docker: permission denied`** — `--group-add` failed. Run `stat -c '%g' /var/run/docker.sock` on the host to find the actual GID; export `SPARK_BENCH_DOCKER_GID` (not implemented yet) or fall back to `sudo` inside the container.
- **SWE-Bench testbed image pull is slow/fails** — first run downloads ~50-100 GB of `swebench/sweb.eval.x86_64.*` images. Pre-pull manually on the bench host with `docker pull swebench/sweb.eval.x86_64.<problem_id>` if needed.
- **Cluster endpoint 502/503 mid-bench** — HAProxy returned no healthy backend (one replica is draining for a build, etc.). The bench harness should retry with backoff; if it doesn't, abort the bench and resume after the cluster is back to 2/2 UP.
- **Out of disk on intel-nuc** — SWE-Bench testbed cache + cloned repos can grow to ~150 GB. `rm -rf ~/spark-bench/cache/swebench` to reset.

## Results Layout

```
~/spark-bench/results/
  <YYYYMMDD-HHMMSS>-<model>-<harness>/
    summary.json   # one-line headline metric
    raw/           # per-problem outputs, logs
```

For analysis, `rsync` snapshots back to the workstation:

```bash
rsync -av jhunt@intel-nuc.tworivers:~/spark-bench/results/ ./bench-results/
```

## Dependencies

- Build-time: docker (≥24), git
- Runtime: bash, ssh, the `bin/spark-bench` shim, intel-nuc reachable on the LAN

## Agent Instructions

When the user asks to run a benchmark or compare two models:

1. Confirm which endpoint(s) and model name(s) — production LB (`starsky:8080`, model `qwen3-coder-next`) is the default baseline; test endpoints are ad-hoc per investigation.
2. Default to **subsets first** (e.g. `--instances.slice=:20` for SWE-Bench, `--num_tasks 20` for tau2-bench) — full runs take hours-to-days on the 4-core bench host.
3. After each run, summarise the headline metric and save raw output for rsync-back. Do not commit raw output to the repo.
4. For A/B comparisons, run the **same harness invocation** against both endpoints back-to-back so sampling parameters and prompt templates are identical.
