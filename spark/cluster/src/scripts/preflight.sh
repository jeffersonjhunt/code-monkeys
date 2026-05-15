#!/usr/bin/env bash
# preflight.sh — read-only host discovery for vLLM cluster nodes.
#
# Run on each box and capture stdout. Makes no changes. Safe to re-run.
#
# Usage (locally on the box):
#   bash preflight.sh
#
# Usage (remote, recommended — leaves nothing on the host):
#   ssh jhunt@<host> 'bash -s' < src/scripts/preflight.sh > docs/inventory-<host>.md

set -uo pipefail

section() { printf '\n=== %s ===\n' "$1"; }
run() {
    local cmd="$*"
    printf '$ %s\n' "$cmd"
    bash -c "$cmd" 2>&1 || true
    printf '\n'
}

section "Identity"
run "hostname -f"
run "id"
run "uname -a"
run "cat /etc/os-release"

section "CPU and memory"
run "lscpu | head -25"
run "free -h"

section "Storage"
run "df -h /"
run "df -h /srv 2>/dev/null || echo '(no /srv mount)'"
run "lsblk"

section "GPU"
run "nvidia-smi"
run "nvidia-smi -L"
run "nvidia-smi topo -m"
run "nvcc --version 2>/dev/null || echo '(nvcc not in PATH)'"

section "Container runtime"
run "docker --version 2>/dev/null || echo '(docker not installed)'"
run "docker info 2>/dev/null | head -40"
run "(dpkg -l 2>/dev/null | grep -i nvidia-container) || (rpm -qa 2>/dev/null | grep -i nvidia-container) || echo '(no nvidia-container-toolkit packages found)'"

section "Python"
run "python3 --version"
run "which python3"

section "Network interfaces"
run "ip -br addr"
run "ip -br link"
run "lspci 2>/dev/null | grep -iE 'mellanox|connectx|ethernet'"

section "Listening ports"
run "ss -tlnp 2>/dev/null | head -30"

section "Firewall"
run "sudo -n firewall-cmd --state 2>/dev/null || echo '(firewalld not active or no NOPASSWD)'"
run "sudo -n ufw status 2>/dev/null || echo '(ufw not active or no NOPASSWD)'"
run "sudo -n iptables -S 2>/dev/null | head -30 || echo '(could not read iptables)'"

section "Done"
