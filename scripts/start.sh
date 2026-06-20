#!/usr/bin/env bash
# Multi-Agent Code Review — start the PR watcher + Streamlit dashboard.
#
# Usage:
#     ./scripts/start.sh                            # watch rahulilla/airflow (default)
#     ./scripts/start.sh rahulilla/python-simple-webapp
#     ./scripts/start.sh rahulilla/airflow --interval 15
#
# Behavior:
#   - Resolves the repo root from this script's own location, so it works
#     no matter where you invoke it from.
#   - Reuses the project venv (.venv/) for both processes.
#   - Watcher runs with SKIP_CI_GATE=1 by default. Override by exporting
#     SKIP_CI_GATE=0 before invoking.
#   - Dashboard at http://localhost:8501.
#   - Both children write to logs/<name>.log; this script tails both with
#     a colored prefix into the terminal so you see live output.
#   - Ctrl-C (or Ctrl-Z then `kill %1`) shuts everything down cleanly.

set -uo pipefail

# ---------- resolve paths ----------
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd -P )"
REPO_ROOT="$( cd "${SCRIPT_DIR}/.." && pwd -P )"
cd "${REPO_ROOT}"

VENV_PYTHON="${REPO_ROOT}/.venv/bin/python"
VENV_STREAMLIT="${REPO_ROOT}/.venv/bin/streamlit"
LOG_DIR="${REPO_ROOT}/logs"

if [[ ! -x "${VENV_PYTHON}" ]]; then
    echo "ERROR: ${VENV_PYTHON} not found or not executable." >&2
    echo "Set up the venv first: python3 -m venv .venv && .venv/bin/pip install -r requirements.txt" >&2
    exit 1
fi

if [[ ! -f "${REPO_ROOT}/.env" ]]; then
    echo "WARNING: ${REPO_ROOT}/.env not found." >&2
    echo "         The watcher needs OPENAI_API_KEY + GITHUB_TOKEN to function." >&2
fi

mkdir -p "${LOG_DIR}"

# ---------- args ----------
REPO_ARG="${1:-rahulilla/airflow}"
shift || true   # remaining args (e.g. --interval 15) flow to the watcher
WATCHER_ARGS=( "${REPO_ARG}" "$@" )

SKIP_CI_GATE="${SKIP_CI_GATE:-1}"

# ---------- launch ----------
WATCHER_LOG="${LOG_DIR}/watcher.log"
DASHBOARD_LOG="${LOG_DIR}/dashboard.log"

# Truncate logs so the tail starts fresh.
: > "${WATCHER_LOG}"
: > "${DASHBOARD_LOG}"

# Children PIDs we manage in cleanup. Initialize empty so the trap is
# safe even if launching one of them fails.
WATCHER_PID=""
DASHBOARD_PID=""
TAIL_PID=""

cleanup() {
    local rc=$?
    echo
    echo "[start] shutting down…"
    # Stop tails first so we stop spamming logs into the terminal.
    for pid in ${TAIL_PID}; do
        kill -TERM "${pid}" 2>/dev/null || true
    done
    [[ -n "${WATCHER_PID}" ]]   && kill -TERM "${WATCHER_PID}"   2>/dev/null || true
    [[ -n "${DASHBOARD_PID}" ]] && kill -TERM "${DASHBOARD_PID}" 2>/dev/null || true
    sleep 0.5
    for pid in ${TAIL_PID} "${WATCHER_PID}" "${DASHBOARD_PID}"; do
        [[ -n "${pid}" ]] && kill -KILL "${pid}" 2>/dev/null || true
    done
    echo "[start] done. Logs preserved at ${LOG_DIR}/"
    exit "${rc}"
}
trap cleanup INT TERM EXIT

cat <<HEADER
╔══════════════════════════════════════════════════════════════════╗
║  Multi-Agent Code Review — running                              ║
╠══════════════════════════════════════════════════════════════════╣
║  watcher target: ${REPO_ARG}
║  dashboard URL:  http://localhost:8501
║  logs:           ${LOG_DIR}/
║  Ctrl-C to stop both.
╚══════════════════════════════════════════════════════════════════╝
HEADER

# Start each child redirecting straight to its log file. $! captures
# the python PID directly (no pipeline involvement), so the cleanup
# trap can target the right process.
SKIP_CI_GATE="${SKIP_CI_GATE}" PYTHONUNBUFFERED=1 \
    "${VENV_PYTHON}" -u watch_prs.py "${WATCHER_ARGS[@]}" \
    >>"${WATCHER_LOG}" 2>&1 &
WATCHER_PID=$!

"${VENV_STREAMLIT}" run dashboard/app.py \
    --server.headless true --browser.gatherUsageStats false \
    >>"${DASHBOARD_LOG}" 2>&1 &
DASHBOARD_PID=$!

# Tail both logs with a colored prefix so the operator sees live output
# from one terminal. tail -F handles log truncation/rotation gracefully.
( tail -F "${WATCHER_LOG}" 2>/dev/null \
    | awk -v c=$'\033[35m' -v r=$'\033[0m' \
        'BEGIN{ORS=""} { print c "[watch]" r " " $0 "\n"; fflush(); }' ) &
TAIL_WATCHER_PID=$!

( tail -F "${DASHBOARD_LOG}" 2>/dev/null \
    | awk -v c=$'\033[36m' -v r=$'\033[0m' \
        'BEGIN{ORS=""} { print c "[dash ]" r " " $0 "\n"; fflush(); }' ) &
TAIL_DASHBOARD_PID=$!
TAIL_PID="${TAIL_WATCHER_PID} ${TAIL_DASHBOARD_PID}"

# Block until either python process exits.
# (`wait -n` is bash 4.3+; macOS ships bash 3.2, so we poll instead.)
while true; do
    if ! kill -0 "${WATCHER_PID}" 2>/dev/null; then
        echo "[start] watcher exited — see ${WATCHER_LOG}"
        break
    fi
    if ! kill -0 "${DASHBOARD_PID}" 2>/dev/null; then
        echo "[start] dashboard exited — see ${DASHBOARD_LOG}"
        break
    fi
    sleep 1
done
