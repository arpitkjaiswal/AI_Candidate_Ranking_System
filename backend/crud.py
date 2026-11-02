"""
backend/crud.py
All SQLite read/write operations used by the API routes.
"""
from __future__ import annotations

import json
import logging
import sqlite3
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════════

def _row_to_dict(row: sqlite3.Row) -> dict:
    return dict(row) if row is not None else {}


def _rows_to_list(rows) -> List[dict]:
    return [dict(r) for r in rows]


# ═══════════════════════════════════════════════════════════════════════════════
# CANDIDATES
# ═══════════════════════════════════════════════════════════════════════════════

def get_candidate(conn: sqlite3.Connection, candidate_id: str) -> Optional[dict]:
    cur = conn.execute(
        "SELECT * FROM candidates WHERE candidate_id = ?", (candidate_id,)
    )
    row = cur.fetchone()
    return dict(row) if row is not None else None


def list_candidates(
    conn: sqlite3.Connection,
    limit: int = 50,
    offset: int = 0,
    country: Optional[str] = None,
    open_to_work: Optional[bool] = None,
    min_yoe: Optional[float] = None,
    max_yoe: Optional[float] = None,
    search: Optional[str] = None,
) -> Tuple[int, List[dict]]:
    """Return (total_count, page_of_candidates)."""
    filters: list[str] = []
    params: list[Any] = []

    if search and search.strip():
        term = search.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        filters.append("(anonymized_name LIKE ? ESCAPE '\\' OR current_title LIKE ? ESCAPE '\\' OR current_company LIKE ? ESCAPE '\\')")
        params.extend([f"%{term}%"] * 3)

    if country:
        filters.append("LOWER(country) = LOWER(?)")
        params.append(country)
    if open_to_work is not None:
        filters.append("open_to_work = ?")
        params.append(int(open_to_work))
    if min_yoe is not None:
        filters.append("years_of_experience >= ?")
        params.append(min_yoe)
    if max_yoe is not None:
        filters.append("years_of_experience <= ?")
        params.append(max_yoe)

    where = ("WHERE " + " AND ".join(filters)) if filters else ""

    total = conn.execute(
        f"SELECT COUNT(*) FROM candidates {where}", params
    ).fetchone()[0]

    rows = conn.execute(
        f"SELECT * FROM candidates {where} ORDER BY candidate_id LIMIT ? OFFSET ?",
        params + [limit, offset],
    ).fetchall()

    return total, _rows_to_list(rows)


def get_candidate_skills(conn: sqlite3.Connection, candidate_id: str) -> List[dict]:
    rows = conn.execute(
        "SELECT * FROM candidate_skills WHERE candidate_id = ?", (candidate_id,)
    ).fetchall()
    return _rows_to_list(rows)


def get_candidate_education(conn: sqlite3.Connection, candidate_id: str) -> List[dict]:
    rows = conn.execute(
        "SELECT * FROM candidate_education WHERE candidate_id = ?", (candidate_id,)
    ).fetchall()
    return _rows_to_list(rows)


def get_candidate_career(conn: sqlite3.Connection, candidate_id: str) -> List[dict]:
    rows = conn.execute(
        "SELECT * FROM candidate_career WHERE candidate_id = ? ORDER BY start_date DESC",
        (candidate_id,),
    ).fetchall()
    return _rows_to_list(rows)


def get_candidate_full(conn: sqlite3.Connection, candidate_id: str) -> Optional[dict]:
    """Return full candidate profile with nested skills/education/career."""
    cand = get_candidate(conn, candidate_id)
    if not cand:
        return None
    cand["skills"] = get_candidate_skills(conn, candidate_id)
    cand["education"] = get_candidate_education(conn, candidate_id)
    cand["career"] = get_candidate_career(conn, candidate_id)
    return cand


def upsert_candidate(conn: sqlite3.Connection, candidate: dict) -> None:
    """Insert or replace a single candidate row (without relations)."""
    conn.execute(
        """
        INSERT INTO candidates (
            candidate_id, anonymized_name, headline, summary,
            location, country, years_of_experience,
            current_title, current_company, current_company_size, current_industry,
            open_to_work, willing_to_relocate, preferred_work_mode,
            notice_period_days, expected_salary_min, expected_salary_max,
            github_activity_score, profile_completeness_score,
            linkedin_connected, verified_email, verified_phone,
            last_active_date, signup_date, raw_json
        ) VALUES (
            :candidate_id, :anonymized_name, :headline, :summary,
            :location, :country, :years_of_experience,
            :current_title, :current_company, :current_company_size, :current_industry,
            :open_to_work, :willing_to_relocate, :preferred_work_mode,
            :notice_period_days, :expected_salary_min, :expected_salary_max,
            :github_activity_score, :profile_completeness_score,
            :linkedin_connected, :verified_email, :verified_phone,
            :last_active_date, :signup_date, :raw_json
        ) ON CONFLICT(candidate_id) DO UPDATE SET
            anonymized_name = excluded.anonymized_name,
            headline = excluded.headline,
            summary = excluded.summary,
            location = excluded.location,
            country = excluded.country,
            years_of_experience = excluded.years_of_experience,
            current_title = excluded.current_title,
            current_company = excluded.current_company,
            current_company_size = excluded.current_company_size,
            current_industry = excluded.current_industry,
            open_to_work = excluded.open_to_work,
            willing_to_relocate = excluded.willing_to_relocate,
            preferred_work_mode = excluded.preferred_work_mode,
            notice_period_days = excluded.notice_period_days,
            expected_salary_min = excluded.expected_salary_min,
            expected_salary_max = excluded.expected_salary_max,
            github_activity_score = excluded.github_activity_score,
            profile_completeness_score = excluded.profile_completeness_score,
            linkedin_connected = excluded.linkedin_connected,
            verified_email = excluded.verified_email,
            verified_phone = excluded.verified_phone,
            last_active_date = excluded.last_active_date,
            signup_date = excluded.signup_date,
            raw_json = excluded.raw_json
        """,
        candidate,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# RANKINGS
# ═══════════════════════════════════════════════════════════════════════════════

def get_rankings(
    conn: sqlite3.Connection,
    job_id: str,
    limit: int = 100,
    offset: int = 0,
    min_score: Optional[float] = None,
    honeypots_only: bool = False,
) -> Tuple[int, List[dict]]:
    """
    Return (total, list of ranking rows joined with candidate info).
    """
    filters = ["r.job_id = ?"]
    params: list[Any] = [job_id]

    if min_score is not None:
        filters.append("r.score >= ?")
        params.append(min_score)
    if honeypots_only:
        filters.append("r.is_honeypot = 1")

    where = "WHERE " + " AND ".join(filters)

    total = conn.execute(
        f"SELECT COUNT(*) FROM rankings r {where}", params
    ).fetchone()[0]

    query = f"""
        SELECT
            r.*,
            c.anonymized_name, c.headline, c.location, c.country,
            c.years_of_experience, c.current_title, c.current_company,
            c.open_to_work, c.willing_to_relocate, c.preferred_work_mode,
            c.notice_period_days, c.github_activity_score
        FROM rankings r
        JOIN candidates c ON r.candidate_id = c.candidate_id
        {where}
        ORDER BY r.rank ASC
        LIMIT ? OFFSET ?
    """
    rows = conn.execute(query, params + [limit, offset]).fetchall()
    return total, _rows_to_list(rows)


def get_ranking_for_candidate(
    conn: sqlite3.Connection, job_id: str, candidate_id: str
) -> Optional[dict]:
    row = conn.execute(
        "SELECT * FROM rankings WHERE job_id = ? AND candidate_id = ?",
        (job_id, candidate_id),
    ).fetchone()
    return dict(row) if row is not None else None


def upsert_rankings_batch(
    conn: sqlite3.Connection, job_id: str, ranked: List[dict]
) -> None:
    """Bulk-insert/replace ranking results."""
    data = [
        (
            job_id,
            c["candidate_id"],
            c["rank"],
            c["score"],
            c.get("component_scores", {}).get("career_relevance"),
            c.get("component_scores", {}).get("skills_match"),
            c.get("component_scores", {}).get("behavioral_signals"),
            c.get("component_scores", {}).get("education_location"),
            c.get("component_scores", {}).get("semantic_similarity"),
            int(c.get("features", {}).get("is_likely_honeypot", 0) > 0.5),
            c.get("reasoning", ""),
        )
        for c in ranked
    ]
    conn.execute("DELETE FROM rankings WHERE job_id = ?", (job_id,))
    conn.executemany(
        """
        INSERT OR REPLACE INTO rankings
            (job_id, candidate_id, rank, score,
             career_score, skill_score, behavioral_score, education_score,
             embedding_sim, is_honeypot, reasoning)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        data,
    )
    conn.commit()
    logger.info(f"Upserted {len(data)} rankings for job_id={job_id}")


# ═══════════════════════════════════════════════════════════════════════════════
# JOBS
# ═══════════════════════════════════════════════════════════════════════════════

def get_job(conn: sqlite3.Connection, job_id: str) -> Optional[dict]:
    row = conn.execute(
        "SELECT * FROM jobs WHERE job_id = ?", (job_id,)
    ).fetchone()
    return dict(row) if row is not None else None


def list_jobs(conn: sqlite3.Connection) -> List[dict]:
    rows = conn.execute(
        "SELECT * FROM jobs ORDER BY created_at DESC"
    ).fetchall()
    return _rows_to_list(rows)


def create_job(conn: sqlite3.Connection, job_id: str, title: str, description: str) -> dict:
    conn.execute(
        "INSERT OR REPLACE INTO jobs (job_id, title, description) VALUES (?, ?, ?)",
        (job_id, title, description),
    )
    conn.commit()
    return get_job(conn, job_id)


def update_job_status(conn: sqlite3.Connection, job_id: str, status: str) -> None:
    conn.execute(
        "UPDATE jobs SET status = ? WHERE job_id = ?", (status, job_id)
    )
    conn.commit()


# ═══════════════════════════════════════════════════════════════════════════════
# PIPELINE RUNS
# ═══════════════════════════════════════════════════════════════════════════════

def create_pipeline_run(conn: sqlite3.Connection, run_id: str, job_id: str) -> None:
    conn.execute(
        "INSERT INTO pipeline_runs (run_id, job_id, status) VALUES (?, ?, 'running')",
        (run_id, job_id),
    )
    conn.commit()


def finish_pipeline_run(
    conn: sqlite3.Connection,
    run_id: str,
    status: str,
    total_candidates: Optional[int] = None,
    error_message: Optional[str] = None,
) -> None:
    conn.execute(
        """
        UPDATE pipeline_runs
        SET status = ?, finished_at = datetime('now'),
            total_candidates = ?, error_message = ?
        WHERE run_id = ?
        """,
        (status, total_candidates, error_message, run_id),
    )
    conn.commit()


def get_pipeline_run(conn: sqlite3.Connection, run_id: str) -> Optional[dict]:
    row = conn.execute(
        "SELECT * FROM pipeline_runs WHERE run_id = ?", (run_id,)
    ).fetchone()
    return dict(row) if row is not None else None


def list_pipeline_runs(conn: sqlite3.Connection, job_id: Optional[str] = None) -> List[dict]:
    if job_id:
        rows = conn.execute(
            "SELECT * FROM pipeline_runs WHERE job_id = ? ORDER BY started_at DESC",
            (job_id,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM pipeline_runs ORDER BY started_at DESC"
        ).fetchall()
    return _rows_to_list(rows)
