#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ ! -x venv/bin/python || ! -d frontend/node_modules ]]; then
  echo 'Run bash scripts/setup.sh first.' >&2
  exit 1
fi
if [[ -z "${CANDIDATES_PATH:-}" && -z "${CANDIDATES_URL:-}" && ! -f candidates.jsonl ]]; then
  venv/bin/python scripts/prepare_demo.py
  export CANDIDATES_PATH="$PWD/precomputed/demo-candidates.jsonl"
fi
venv/bin/python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 &
backend_pid=$!
frontend_pid=''
cleanup() {
  kill "$backend_pid" ${frontend_pid:+"$frontend_pid"} 2>/dev/null || true
  wait "$backend_pid" ${frontend_pid:+"$frontend_pid"} 2>/dev/null || true
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
(cd frontend && export VITE_API_BASE_URL="${VITE_API_BASE_URL-}" && exec node node_modules/vite/bin/vite.js --host 127.0.0.1 --strictPort) &
frontend_pid=$!
wait -n "$backend_pid" "$frontend_pid"
