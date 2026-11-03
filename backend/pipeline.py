"""
backend/pipeline.py
Background pipeline runner that integrates the ML ranking engine with the API.

This module:
1. Accepts a pipeline run request (job_id + candidates path)
2. Runs data preparation (feature extraction + embeddings) via src/
3. Runs the ranking engine
4. Persists results to SQLite via backend/crud.py
"""
from __future__ import annotations

import json
import logging
import sys
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Ensure the project root is on sys.path so we can import src.*
ROOT_DIR = Path(__file__).parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend.database import get_data_dir, get_db_path

PRECOMPUTED_DIR = get_data_dir()


def _populate_candidates_to_db(conn, candidates_path: str, *, commit: bool = True) -> int:
    """
    Stream candidates from JSONL and populate the SQLite candidates/skills/
    career/education tables using the backend crud module.
    Returns the count of inserted candidates.
    """
    from backend.database import _seed_database_from_records
    from backend.datasets import records_from_dataset
    return _seed_database_from_records(conn, records_from_dataset(Path(candidates_path)), commit=commit)


def _snapshot_dataset(source_path: Path, target_path: Path) -> int:
    """Validate a stable per-run dataset, including gzipped local JSONL sources."""
    from backend.datasets import records_from_dataset
    target_path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with target_path.open("w", encoding="utf-8") as target:
        for record in records_from_dataset(source_path):
            target.write(json.dumps(record, ensure_ascii=False, allow_nan=False) + "\n")
            count += 1
    return count


def _invalidate_changed_profile_rankings(conn, candidates_path: str, current_job_id: str) -> None:
    """Remove other jobs' stale scores only when a profile actually changes."""
    from backend.datasets import records_from_dataset, validate_record
    for record in records_from_dataset(Path(candidates_path)):
        old = conn.execute("SELECT raw_json FROM candidates WHERE candidate_id = ?", (record["candidate_id"],)).fetchone()
        if old is None:
            continue
        try:
            existing = validate_record(json.loads(old["raw_json"]))
        except (ValueError, TypeError, AttributeError, KeyError, OverflowError, RecursionError):
            existing = None
        if existing == record:
            continue
        conn.execute(
            "UPDATE jobs SET status='pending' WHERE job_id != ? AND job_id IN "
            "(SELECT job_id FROM rankings WHERE candidate_id=?)",
            (current_job_id, record["candidate_id"]),
        )
        conn.execute("DELETE FROM rankings WHERE candidate_id=? AND job_id != ?", (record["candidate_id"], current_job_id))


def run_full_pipeline(
    run_id: str,
    job_id: str,
    candidates_path: str,
    top_k: int = 100,
    embedding_mode: str = "tfidf",
    db_path: Optional[Path] = None,
) -> None:
    """
    Execute the full ML pipeline in the background and store results to DB.
    
    Steps:
    1. Prepare data (feature extraction + embeddings) — writes to precomputed/
    2. Rank candidates using the precomputed artifacts
    3. Generate human-readable reasoning
    4. Persist ranked results to SQLite
    """
    from backend.database import get_connection
    from backend.crud import get_job
    from backend.crud import (
        upsert_rankings_batch,
        finish_pipeline_run,
        update_job_status,
    )

    db = db_path or get_db_path()
    conn = None
    artifacts_dir = PRECOMPUTED_DIR / "runs" / run_id

    start = time.time()
    logger.info(f"[run_id={run_id}] Pipeline starting for job_id={job_id}")

    try:
        conn = get_connection(db)
        job = get_job(conn, job_id)
        if not job:
            raise ValueError("Job does not exist")
        # ── Step 1: Validate a stable dataset snapshot ────────────────────────────────
        if not Path(candidates_path).exists():
            raise FileNotFoundError(f"candidates file not found: {candidates_path}")

        if embedding_mode == "sentence_transformers":
            try:
                from sentence_transformers import SentenceTransformer  # noqa: F401
            except ImportError as exc:
                raise ValueError(
                    "Sentence Transformers is unavailable. Use TF-IDF or install the optional sentence-transformers dependencies."
                ) from exc

        snapshot_path = artifacts_dir / "candidates.jsonl"
        source_path = Path(candidates_path)
        _snapshot_dataset(source_path, snapshot_path)
        # The API's database snapshot is disposable once the canonical per-run
        # copy exists. Never remove an uploaded or externally supplied dataset.
        expected_source = get_data_dir() / "snapshots" / f"{run_id}.jsonl"
        if source_path.resolve() == expected_source.resolve():
            source_path.unlink(missing_ok=True)
        candidates_path = str(snapshot_path)

        # ── Step 2: Run data preparation (src pipeline) ───────────────────
        logger.info("[Pipeline] Running feature extraction & embeddings...")
        from src.data_preparation import prepare_all_data

        prepared = prepare_all_data(
            candidates_path=candidates_path,
            output_dir=str(artifacts_dir),
            embedding_mode=embedding_mode,
            job_description=f"{job['title']}\n{job['description']}",
            populate_sqlite=False,
        )
        if embedding_mode == "sentence_transformers":
            from src.embedding_engine import EmbeddingEngine
            if EmbeddingEngine.load(prepared["engine"]).mode != embedding_mode:
                raise ValueError("Sentence Transformers failed; this run will not silently switch to TF-IDF.")

        # ── Step 3: Load tuned weights if available ───────────────────────
        weights = None
        weights_path = PRECOMPUTED_DIR / "best_weights.json"
        if weights_path.exists():
            with open(weights_path) as f:
                weights = json.load(f)
            logger.info(f"[Pipeline] Using tuned weights: {weights}")

        # ── Step 4: Rank candidates ───────────────────────────────────────
        logger.info("[Pipeline] Ranking candidates...")
        from src.ranking_engine import rank_candidates

        ranked = rank_candidates(
            precomputed_dir=str(artifacts_dir),
            weights=weights,
            top_k=top_k,
        )

        # ── Step 5: Generate reasoning ────────────────────────────────────
        logger.info("[Pipeline] Generating reasoning strings...")
        from src.reasoning_generator import generate_all_reasoning

        ranked = generate_all_reasoning(ranked, str(artifacts_dir))

        # ── Step 6: Persist rankings ──────────────────────────────────────
        logger.info("[Pipeline] Saving rankings to SQLite...")
        # Publish profiles, relations, rankings and success status together. A failure
        # anywhere in this transaction preserves the previous successful result.
        conn.execute("BEGIN IMMEDIATE")
        _invalidate_changed_profile_rankings(conn, candidates_path, job_id)
        total = _populate_candidates_to_db(conn, candidates_path, commit=False)
        upsert_rankings_batch(conn, job_id, ranked, commit=False)
        update_job_status(conn, job_id, "done", commit=False)
        finish_pipeline_run(conn, run_id, status="done", total_candidates=total, commit=False)
        conn.commit()

        elapsed = time.time() - start
        logger.info(
            f"[run_id={run_id}] Pipeline done in {elapsed:.1f}s. "
            f"Ranked {len(ranked)} candidates."
        )

    except Exception as exc:
        logger.exception(f"[run_id={run_id}] Pipeline FAILED: {exc}")
        try:
            if conn is None:
                conn = get_connection(db)
            conn.rollback()
            update_job_status(conn, job_id, "failed", commit=False)
            finish_pipeline_run(conn, run_id, status="failed", error_message=str(exc), commit=False)
            conn.commit()
        except Exception:
            logger.exception("Could not persist failure status for run %s", run_id)
        # The error is persisted for polling; do not crash the worker thread.

    finally:
        if conn is not None:
            conn.close()
