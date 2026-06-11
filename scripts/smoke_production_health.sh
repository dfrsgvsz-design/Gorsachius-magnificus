#!/usr/bin/env bash
# Smoke-test the public HTTPS endpoints after DNS + acme-companion have
# settled. Intended to be runnable from any shell (operator's laptop or
# the host itself) once the prod overlay is up. Exit code 0 = green.
#
# Usage:
#   scripts/smoke_production_health.sh
#   scripts/smoke_production_health.sh https://swdyx.eu.cc https://acoustic.swdyx.eu.cc
#
# Pre-conditions checked:
#   1. DNS A record resolves
#   2. HTTPS handshake succeeds (cert is valid + chained to a public CA)
#   3. /api/health/liveness returns 200
#   4. /api/health/readiness reports ready=true + deployment_ready=true
#   5. /api/health reports readiness.mode == "production" and
#      runtime_paths.mutable_runtime_externalized == true (= no demo mode)
#
# Failure on any of the above prints a verbose diagnostic and exits 1.

set -euo pipefail

DEFAULT_BASES=("https://swdyx.eu.cc" "https://acoustic.swdyx.eu.cc")
BASES=("${@:-${DEFAULT_BASES[@]}}")

# Allow operator to override with a single arg or a list. Filter out empty.
TARGETS=()
for base in "${BASES[@]}"; do
  if [[ -n "$base" ]]; then
    TARGETS+=("$base")
  fi
done
if [[ ${#TARGETS[@]} -eq 0 ]]; then
  TARGETS=("${DEFAULT_BASES[@]}")
fi

fail=0
fail_msg=""

red()    { printf "\033[31m%s\033[0m\n" "$1"; }
green()  { printf "\033[32m%s\033[0m\n" "$1"; }
yellow() { printf "\033[33m%s\033[0m\n" "$1"; }

check_one() {
  local base="$1"
  local host
  host=$(printf '%s' "$base" | sed -E 's#https?://##; s#/.*##')
  printf "\n== %s ==\n" "$base"

  # 1. DNS
  if ! ip=$(dig +short "$host" | head -n 1 2>/dev/null); then
    red "  DNS lookup tool 'dig' missing; falling back to getent."
    ip=$(getent hosts "$host" | awk '{print $1}' | head -n 1 || true)
  fi
  if [[ -z "${ip:-}" ]]; then
    red "  [FAIL] DNS: $host does not resolve"
    fail=1; fail_msg+=" $host:dns"
    return
  fi
  green "  [OK]   DNS  : $host -> $ip"

  # 2. HTTPS + cert validation (curl exits non-zero on bad cert)
  if ! curl -fsS -o /dev/null --max-time 10 "${base}/api/health/liveness"; then
    red "  [FAIL] HTTPS: ${base}/api/health/liveness — cert chain or TLS handshake broken"
    fail=1; fail_msg+=" $host:tls"
    return
  fi
  green "  [OK]   TLS  : public cert valid + 200 from /api/health/liveness"

  # 3. Readiness
  if ! ready_body=$(curl -fsS --max-time 10 "${base}/api/health/readiness"); then
    red "  [FAIL] READY: ${base}/api/health/readiness returned non-2xx"
    fail=1; fail_msg+=" $host:readiness"
    return
  fi
  if ! printf '%s' "$ready_body" | jq -e '.ready == true and .deployment_ready == true' > /dev/null 2>&1; then
    red "  [FAIL] READY: ready/deployment_ready not both true"
    printf "         payload: %s\n" "$ready_body"
    fail=1; fail_msg+=" $host:not_ready"
    return
  fi
  green "  [OK]   READY: ready=true, deployment_ready=true"

  # 4. Full /api/health for no-demo guard
  if ! health_body=$(curl -fsS --max-time 10 "${base}/api/health"); then
    red "  [FAIL] HEALTH: ${base}/api/health returned non-2xx"
    fail=1; fail_msg+=" $host:health"
    return
  fi
  if ! printf '%s' "$health_body" | jq -e '
        .deployment_ready == true and
        .readiness.mode == "production" and
        .readiness.blocking_codes == [] and
        .runtime_paths.mutable_runtime_externalized == true
      ' > /dev/null 2>&1; then
    red "  [FAIL] HEALTH: still in demo / degraded / fallback mode"
    printf "         readiness: %s\n" "$(printf '%s' "$health_body" | jq -c '.readiness')"
    printf "         runtime_paths externalized: %s\n" \
      "$(printf '%s' "$health_body" | jq -c '{data_dir_externalized: .runtime_paths.data_dir_externalized, checkpoints_dir_externalized: .runtime_paths.checkpoints_dir_externalized, frontend_dist_dir_externalized: .runtime_paths.frontend_dist_dir_externalized, mutable_runtime_externalized: .runtime_paths.mutable_runtime_externalized}')"
    fail=1; fail_msg+=" $host:demo_mode"
    return
  fi
  green "  [OK]   HEALTH: readiness.mode=production, deployment_ready=true, no demo guard tripped"
}

if ! command -v curl > /dev/null 2>&1; then
  red "FATAL: curl is required."
  exit 2
fi
if ! command -v jq > /dev/null 2>&1; then
  yellow "WARN: jq missing; install via 'apt install jq' for the no-demo assertion to work."
  exit 2
fi

for target in "${TARGETS[@]}"; do
  check_one "$target"
done

printf "\n"
if [[ $fail -eq 0 ]]; then
  green "ALL TARGETS GREEN — safe to hand off to C / publish AAB"
  exit 0
fi
red "SMOKE FAILED:$fail_msg"
exit 1
