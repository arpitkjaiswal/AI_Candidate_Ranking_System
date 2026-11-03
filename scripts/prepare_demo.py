"""Create an explicitly labeled demo dataset from the application's built-in examples."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from backend.database import _build_fallback_candidates

path = Path(__file__).resolve().parent.parent / "precomputed" / "demo-candidates.jsonl"
if not path.exists():
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(c) for c in _build_fallback_candidates()) + "\n")
print(f"Demo dataset: {path} (2 example profiles; not the full challenge dataset)")
