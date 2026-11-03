#!/usr/bin/env bash
set -euo pipefail
project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$project_dir"
app_venv="${APP_VENV:-$project_dir/venv}"
if [[ ! -x "$app_venv/bin/python" ]]; then
  python3 -m venv "$app_venv"
fi
"$app_venv/bin/python" -m pip install -r requirements.lock
npm ci --prefix frontend --no-audit --no-fund
VITE_API_BASE_URL= npm run build --prefix frontend
"$app_venv/bin/python" -m backend.manage prepare-demo
exec "$app_venv/bin/python" -m uvicorn backend.main:app --host 0.0.0.0 --port "${PORT:-8000}" --workers 1
