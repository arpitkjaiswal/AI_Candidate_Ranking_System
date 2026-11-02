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
import os
import sys
import time
import uuid
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Ensure the project root is on sys.path so we can import src.*
ROOT_DIR = Path(__file__).parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend.database import get_data_dir, get_db_path

PRECOMPUTED_DIR = get_data_dir()


def _populate_candidates_to_db(conn, candidates_path: str) -> int:
    """
    Stream candidates from JSONL and populate the SQLite candidates/skills/
    career/education tables using the backend crud module.
    Returns the count of inserted candidates.
    """
    import json as _json
    from backend.crud import upsert_candidate

    count = 0
    with open(candidates_path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                raw = _json.loads(line)
            except Exception:
                continue

            cid = raw.get("candidate_id", "")
            if not cid:
                continue

            profile = raw.get("profile", {}) or {}
            signals = raw.get("redrob_signals", {}) or {}

            row = {
                "candidate_id": cid,
                "anonymized_name": raw.get("anonymized_name", ""),
                "headline": profile.get("headline"),
                "summary": profile.get("summary"),
                "location": profile.get("location"),
                "country": profile.get("country"),
                "years_of_experience": float(profile.get("years_of_experience") or 0),
                "current_title": profile.get("current_title"),
                "current_company": profile.get("current_company"),
                "current_company_size": profile.get("current_company_size"),
                "current_industry": profile.get("current_industry"),
                "open_to_work": int(bool(signals.get("open_to_work_flag", False))),
                "willing_to_relocate": int(bool(signals.get("willing_to_relocate", False))),
                "preferred_work_mode": signals.get("preferred_work_mode", "flexible"),
                "notice_period_days": signals.get("notice_period_days"),
                "expected_salary_min": signals.get("expected_salary_min_lpa"),
                "expected_salary_max": signals.get("expected_salary_max_lpa"),
                "github_activity_score": signals.get("github_activity_score"),
                "profile_completeness_score": float(signals.get("profile_completeness_score") or 0),
                "linkedin_connected": int(bool(signals.get("linkedin_connected", False))),
                "verified_email": int(bool(signals.get("verified_email", False))),
                "verified_phone": int(bool(signals.get("verified_phone", False))),
                "last_active_date": signals.get("last_active_date"),
                "signup_date": signals.get("signup_date"),
                "raw_json": _json.dumps(raw),
            }
            upsert_candidate(conn, row)

            for table in ("candidate_skills", "candidate_education", "candidate_career"):
                conn.execute(f"DELETE FROM {table} WHERE candidate_id = ?", (cid,))

            # Skills
            for sk in (raw.get("skills") or []):
                conn.execute(
                    """
                    INSERT INTO candidate_skills
                        (candidate_id, skill_name, proficiency, endorsements, duration_months, cluster)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        cid,
                        sk.get("name", ""),
                        sk.get("proficiency", "beginner"),
                        int(sk.get("endorsements") or 0),
                        int(sk.get("duration_months") or 0),
                        None,  # cluster will be mapped below if needed
                    ),
                )

            # Education
            for edu in (raw.get("education") or []):
                conn.execute(
                    """
                    INSERT INTO candidate_education
                        (candidate_id, institution, degree, field_of_study,
                         start_year, end_year, grade, tier)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        cid,
                        edu.get("institution"),
                        edu.get("degree"),
                        edu.get("field_of_study"),
                        edu.get("start_year"),
                        edu.get("end_year"),
                        edu.get("grade"),
                        edu.get("tier", "unknown"),
                    ),
                )

            # Career
            for job in (raw.get("career_history") or []):
                conn.execute(
                    """
                    INSERT INTO candidate_career
                        (candidate_id, company, title, start_date, end_date,
                         duration_months, is_current, industry, company_size, description)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        cid,
                        job.get("company"),
                        job.get("title"),
                        job.get("start_date"),
                        job.get("end_date"),
                        int(job.get("duration_months") or 0),
                        int(bool(job.get("is_current", False))),
                        job.get("industry"),
                        job.get("company_size"),
                        job.get("description"),
                    ),
                )

            count += 1
            if count % 5000 == 0:
                conn.commit()
                logger.info(f"  Inserted {count} candidates so far...")

    conn.commit()
    logger.info(f"Candidate population complete: {count} rows inserted.")
    return count


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
    from backend.database import get_connection, init_db
    from backend.crud import (
        upsert_rankings_batch,
        finish_pipeline_run,
        update_job_status,
    )

    db = db_path or get_db_path()
    conn = get_connection(db)

    start = time.time()
    logger.info(f"[run_id={run_id}] Pipeline starting for job_id={job_id}")

    artifact_dir = PRECOMPUTED_DIR / "runs" / run_id
    try:
        from backend.crud import get_job
        job = get_job(conn, job_id)
        if not job:
            raise ValueError("Job does not exist")
        # ── Step 1: Populate candidates table ────────────────────────────────
        if not Path(candidates_path).exists():
            raise FileNotFoundError(f"candidates file not found: {candidates_path}")

        logger.info("[Pipeline] Populating candidates table...")
        total = _populate_candidates_to_db(conn, candidates_path)

        # ── Step 2: Run data preparation (src pipeline) ───────────────────
        logger.info("[Pipeline] Running feature extraction & embeddings...")
        from src.data_preparation import prepare_all_data

        prepare_all_data(
            candidates_path=candidates_path,
            output_dir=str(artifact_dir),
            job_description=f"{job['title']}\n{job['description']}",
            embedding_mode=embedding_mode,
            populate_sqlite=False,  # We already handled it above
        )

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
            precomputed_dir=str(artifact_dir),
            weights=weights,
            top_k=top_k,
        )

        # ── Step 5: Generate reasoning ────────────────────────────────────
        logger.info("[Pipeline] Generating reasoning strings...")
        from src.reasoning_generator import generate_all_reasoning

        ranked = generate_all_reasoning(ranked, str(artifact_dir))

        # ── Step 6: Persist rankings ──────────────────────────────────────
        logger.info("[Pipeline] Saving rankings to SQLite...")
        upsert_rankings_batch(conn, job_id, ranked)

        # ── Step 7: Mark job as done ──────────────────────────────────────
        update_job_status(conn, job_id, "done")
        finish_pipeline_run(conn, run_id, status="done", total_candidates=total)

        elapsed = time.time() - start
        logger.info(
            f"[run_id={run_id}] Pipeline done in {elapsed:.1f}s. "
            f"Ranked {len(ranked)} candidates."
        )

    except Exception as exc:
        conn.rollback()
        logger.exception(f"[run_id={run_id}] Pipeline FAILED: {exc}")
        try:
            update_job_status(conn, job_id, "failed")
            finish_pipeline_run(conn, run_id, status="failed", error_message=str(exc))
        except Exception:
            pass
        raise

    finally:
        conn.close()
