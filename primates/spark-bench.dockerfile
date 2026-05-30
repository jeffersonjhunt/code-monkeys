# docker buildx build -t spark-bench:latest -f ./spark-bench.dockerfile .
#
# Benchmark orchestration primate. Runs LLM evals (AIME, GPQA, LiveCodeBench,
# tau2-bench, SWE-Bench Verified via SWE-agent) against an OpenAI-compatible
# endpoint — by default the spark-cluster LB on starsky.tworivers:8080.
#
# x86_64-only: SWE-Bench's testbed images are published as
# `swebench/sweb.eval.x86_64.*` — qemu-emulating them on aarch64 is slow and
# unreliable. Build and run this image on an x86 box (intel-nuc.tworivers).
#
# Docker-out-of-Docker: SWE-Bench spawns test sandbox containers per problem.
# Launch with `--volume /var/run/docker.sock:/var/run/docker.sock` and
# `--group-add $(stat -c %g /var/run/docker.sock)` so codemonkey can drive
# the host's daemon without sudo.

FROM miniforge3:latest
LABEL maintainer="Jefferson J. Hunt <jeffersonjhunt@gmail.com>"

ARG IMAGE_NAME=spark-bench
ARG UNSAFE_SSL=false

# Create the per-image conda env (overrides miniforge3-env as the login default)
RUN if [ "$UNSAFE_SSL" = "true" ]; then /opt/miniforge3/bin/conda config --set ssl_verify false; fi \
    && /opt/miniforge3/bin/conda create -y -n ${IMAGE_NAME}-env python=3.12 \
    && echo "${IMAGE_NAME}-env" > /opt/miniforge3/.default-env \
    && if [ "$UNSAFE_SSL" = "true" ]; then /opt/miniforge3/bin/conda config --remove-key ssl_verify; fi

# Pin versions where available; pull active git refs for the rest.
ARG SWEBENCH_VERSION=4.1.0
ARG SWEAGENT_REF=v1.1.0
ARG TAU2_REF=main
ARG LCB_REF=main

# Install harness packages into spark-bench-env via uv (much faster resolver
# than pip). uv is already on PATH from miniforge3 (symlinked to /usr/local/bin).
#
# All three of SWE-agent, LiveCodeBench, and tau2-bench have packaging quirks
# that need an editable install from a clone — not a `pip install <git+url>`:
#
#   SWE-agent: __init__.py asserts CONFIG_DIR / TOOLS_DIR / TRAJECTORY_DIR
#     exist as siblings of its package — none of which ship in the wheel.
#   LiveCodeBench: pip-from-git ships only `lcb_runner/lm_styles.py`; the
#     whole `lcb_runner.runner` subpackage is missing. -e from the clone
#     exposes the source tree via .pth so all submodules import.
#   tau2-bench: imports fine, but expects domain data at a sibling `data/`
#     dir under TAU2_DATA_DIR; data isn't in the wheel.
#
# Clone all three, install editable from the clones, and set the env vars
# that point each library at its cloned data/config tree.
RUN /opt/miniforge3/envs/${IMAGE_NAME}-env/bin/python -m pip install --upgrade pip \
    && git clone --depth 1 --branch ${SWEAGENT_REF} https://github.com/SWE-agent/SWE-agent.git /opt/sweagent \
    && git clone --depth 1 --branch ${LCB_REF}      https://github.com/LiveCodeBench/LiveCodeBench.git /opt/livecodebench \
    && git clone --depth 1 --branch ${TAU2_REF}     https://github.com/sierra-research/tau2-bench.git /opt/tau2-bench \
    && uv pip install --python /opt/miniforge3/envs/${IMAGE_NAME}-env/bin/python \
        $([ "$UNSAFE_SSL" = "true" ] && echo "--native-tls --allow-insecure-host pypi.org --allow-insecure-host files.pythonhosted.org") \
        "swebench==${SWEBENCH_VERSION}" \
        -e "/opt/sweagent" \
        -e "/opt/livecodebench" \
        -e "/opt/tau2-bench" \
        "openai>=2.0" \
        "datasets" \
        "huggingface_hub" \
        "tiktoken" \
        "jsonlines" \
        "pandas" \
        "rich" \
        "tenacity" \
        "httpx"

# Point SWE-agent at the cloned repo for its CONFIG/TOOLS dirs.
# Trajectory dir must exist at import time (sweagent asserts is_dir() in
# __init__.py); default to in-image, override at run-time (-e
# SWE_AGENT_TRAJECTORY_DIR=/results/...) when you want results to persist.
RUN mkdir -p /opt/sweagent/trajectories \
    && chown -R codemonkey:codemonkey /opt/sweagent/trajectories /opt/sweagent /opt/livecodebench /opt/tau2-bench
ENV SWE_AGENT_CONFIG_DIR=/opt/sweagent/config
ENV SWE_AGENT_TOOLS_DIR=/opt/sweagent/tools
ENV SWE_AGENT_TRAJECTORY_DIR=/opt/sweagent/trajectories
# tau2 looks here for its airline/retail/telecom task data
ENV TAU2_DATA_DIR=/opt/tau2-bench/data
# LiveCodeBench's runner expects to be invoked as `python -m lcb_runner.runner.main`

# Bench result + cache layout — bind-mount these from the host so results
# survive container restarts and SWE-Bench's testbed Docker images are
# pulled once per host (not per container instance).
RUN mkdir -p /results /cache \
    && chown -R codemonkey:codemonkey /results /cache

# SWE-Bench respects this for its dataset / testbed cache.
ENV SWE_BENCH_CACHE_DIR=/cache/swebench
ENV HF_HOME=/cache/hf
ENV PIP_CACHE_DIR=/cache/pip
# Default endpoint — override at run time with -e VLLM_BASE_URL=...
ENV VLLM_BASE_URL=http://starsky.tworivers:8080/v1
ENV OPENAI_API_BASE=${VLLM_BASE_URL}
ENV OPENAI_API_KEY=spark-cluster-no-auth

WORKDIR /work
USER codemonkey

# Default: drop the user into an interactive shell. The bin/spark-bench
# launcher invokes specific harness commands instead.
# Fin
