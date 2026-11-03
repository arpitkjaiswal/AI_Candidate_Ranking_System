"""
backend/database.py
SQLite connection manager for the FastAPI backend.
Uses the schema defined in backend/schema.sql and the DB produced by the ML pipeline.
"""
import json
import logging
import os
import sqlite3
import tempfile
from pathlib import Path
from typing import Generator, Iterable
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)

# ─── Paths ────────────────────────────────────────────────────────────────────
# Root of the project (one level up from backend/)
ROOT_DIR = Path(__file__).parent.parent
# In Render, set DATA_DIR=/var/data and attach the persistent disk at /var/data.
# The local default keeps the existing development workflow unchanged.
DATA_DIR = Path(os.environ.get("DATA_DIR", ROOT_DIR / "precomputed")).expanduser()
DB_PATH = DATA_DIR / "redrob_candidates.db"
SCHEMA_PATH = Path(__file__).parent / "schema.sql"


def get_db_path() -> Path:
    return DB_PATH


def get_data_dir() -> Path:
    """Directory for persistent runtime data (SQLite, artifacts, and dataset)."""
    return DATA_DIR


def get_candidates_path() -> Path:
    """Return the configured dataset path, preferring the persistent data disk."""
    configured = os.environ.get("CANDIDATES_PATH")
    if configured:
        return Path(configured).expanduser()

    persistent_candidate_path = DATA_DIR / "candidates.jsonl"
    if persistent_candidate_path.exists() or os.environ.get("CANDIDATES_URL"):
        return persistent_candidate_path

    for candidate_path in (ROOT_DIR / "candidates.jsonl", ROOT_DIR / "data" / "candidates.jsonl"):
        if candidate_path.exists():
            return candidate_path
    return persistent_candidate_path


def ensure_candidates_dataset() -> Path | None:
    """Download the dataset once when CANDIDATES_URL is configured.

    The download is written atomically so an interrupted deploy never leaves a
    partial JSONL file on the persistent disk. Keep CANDIDATES_URL as a Render
    secret when the object-storage URL contains credentials.
    """
    candidate_path = get_candidates_path()
    if candidate_path.exists():
        return candidate_path

    dataset_url = os.environ.get("CANDIDATES_URL")
    if not dataset_url:
        if os.environ.get("CANDIDATES_PATH"):
            raise FileNotFoundError("Configured CANDIDATES_PATH does not exist.")
        return None

    candidate_path.parent.mkdir(parents=True, exist_ok=True)
    logger.info("Downloading candidate dataset to %s", candidate_path)
    temp_name = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", dir=candidate_path.parent, prefix=".candidates-", delete=False
        ) as temp_file:
            temp_name = temp_file.name
            request = Request(dataset_url, headers={"User-Agent": "redrob-ranking-engine/1.0"})
            with urlopen(request, timeout=60) as response:
                while chunk := response.read(1024 * 1024):
                    temp_file.write(chunk)
        os.replace(temp_name, candidate_path)
        logger.info("Candidate dataset download complete (%d bytes).", candidate_path.stat().st_size)
        return candidate_path
    except Exception:
        if temp_name:
            Path(temp_name).unlink(missing_ok=True)
        logger.exception("Candidate dataset download failed")
        raise


def _normalize_candidate(record: dict) -> dict:
    profile = record.get("profile") or {}
    signals = record.get("redrob_signals") or {}
    return {
        "candidate_id": record.get("candidate_id", ""),
        "anonymized_name": record.get("anonymized_name") or profile.get("anonymized_name") or record.get("candidate_id", ""),
        "headline": profile.get("headline") or record.get("headline"),
        "summary": profile.get("summary") or record.get("summary"),
        "location": profile.get("location"),
        "country": profile.get("country"),
        "years_of_experience": float(profile.get("years_of_experience") or 0),
        "current_title": profile.get("current_title"),
        "current_company": profile.get("current_company"),
        "current_company_size": profile.get("current_company_size"),
        "current_industry": profile.get("current_industry"),
        "open_to_work": int(bool(signals.get("open_to_work_flag", False) or record.get("open_to_work", False))),
        "willing_to_relocate": int(bool(signals.get("willing_to_relocate", False) or record.get("willing_to_relocate", False))),
        "preferred_work_mode": signals.get("preferred_work_mode") or record.get("preferred_work_mode"),
        "notice_period_days": signals.get("notice_period_days", 0),
        "expected_salary_min": signals.get("expected_salary_min_lpa", 0),
        "expected_salary_max": signals.get("expected_salary_max_lpa", 0),
        "github_activity_score": signals.get("github_activity_score", -1),
        "profile_completeness_score": float(signals.get("profile_completeness_score") or 0),
        "linkedin_connected": int(bool(signals.get("linkedin_connected", False))),
        "verified_email": int(bool(signals.get("verified_email", False))),
        "verified_phone": int(bool(signals.get("verified_phone", False))),
        "last_active_date": signals.get("last_active_date"),
        "signup_date": signals.get("signup_date"),
        "raw_json": json.dumps(record, ensure_ascii=False),
    }


def _build_fallback_candidates() -> list[dict]:
    return [
        {
            "candidate_id": "CAND_001",
            "anonymized_name": "Ava Sharma",
            "profile": {
                "headline": "Senior ML Engineer",
                "summary": "Builds ranking and recommendation systems for product teams.",
                "location": "Pune",
                "country": "India",
                "years_of_experience": 7,
                "current_title": "Senior ML Engineer",
                "current_company": "Redrob AI",
                "current_company_size": "11-50",
                "current_industry": "AI SaaS",
            },
            "career_history": [
                {
                    "company": "Redrob AI",
                    "title": "Senior ML Engineer",
                    "start_date": "2022-01-01",
                    "end_date": None,
                    "duration_months": 48,
                    "is_current": True,
                    "industry": "AI SaaS",
                    "company_size": "11-50",
                    "description": "Built ranking and retrieval systems.",
                }
            ],
            "education": [
                {
                    "institution": "IIT Delhi",
                    "degree": "B.Tech",
                    "field_of_study": "Computer Science",
                    "start_year": 2012,
                    "end_year": 2016,
                    "tier": "top",
                }
            ],
            "skills": [
                {"name": "Python", "proficiency": "expert", "endorsements": 30, "duration_months": 72},
                {"name": "PyTorch", "proficiency": "advanced", "endorsements": 20, "duration_months": 36},
                {"name": "Search Ranking", "proficiency": "advanced", "endorsements": 15, "duration_months": 24},
            ],
            "redrob_signals": {
                "open_to_work_flag": True,
                "willing_to_relocate": True,
                "preferred_work_mode": "hybrid",
                "notice_period_days": 30,
                "expected_salary_min_lpa": 45,
                "expected_salary_max_lpa": 60,
                "github_activity_score": 0.9,
                "profile_completeness_score": 0.92,
                "linkedin_connected": True,
                "verified_email": True,
                "verified_phone": True,
                "last_active_date": "2026-07-01",
                "signup_date": "2023-01-01",
            },
        },
        {
            "candidate_id": "CAND_002",
            "anonymized_name": "Rahul Mehta",
            "profile": {
                "headline": "Applied Scientist",
                "summary": "Works on NLP and semantic search for enterprise products.",
                "location": "Bangalore",
                "country": "India",
                "years_of_experience": 6,
                "current_title": "Applied Scientist",
                "current_company": "Netskope",
                "current_company_size": "1001-5000",
                "current_industry": "Cybersecurity",
            },
            "career_history": [
                {
                    "company": "Netskope",
                    "title": "Applied Scientist",
                    "start_date": "2021-02-01",
                    "end_date": None,
                    "duration_months": 64,
                    "is_current": True,
                    "industry": "Cybersecurity",
                    "company_size": "1001-5000",
                    "description": "Delivered semantic search and ranking models.",
                }
            ],
            "education": [
                {
                    "institution": "BITS Pilani",
                    "degree": "M.Tech",
                    "field_of_study": "Artificial Intelligence",
                    "start_year": 2014,
                    "end_year": 2018,
                    "tier": "top",
                }
            ],
            "skills": [
                {"name": "Python", "proficiency": "expert", "endorsements": 25, "duration_months": 60},
                {"name": "Sentence Transformers", "proficiency": "advanced", "endorsements": 18, "duration_months": 30},
                {"name": "Vector Databases", "proficiency": "advanced", "endorsements": 12, "duration_months": 24},
            ],
            "redrob_signals": {
                "open_to_work_flag": True,
                "willing_to_relocate": False,
                "preferred_work_mode": "remote",
                "notice_period_days": 45,
                "expected_salary_min_lpa": 40,
                "expected_salary_max_lpa": 55,
                "github_activity_score": 0.8,
                "profile_completeness_score": 0.88,
                "linkedin_connected": True,
                "verified_email": True,
                "verified_phone": False,
                "last_active_date": "2026-06-20",
                "signup_date": "2022-08-01",
            },
        },
    ]


def _seed_database_from_records(
    conn: sqlite3.Connection, records: Iterable[dict], *, commit: bool = True
) -> int:
    count = 0
    for record in records:
        candidate = _normalize_candidate(record)
        from backend.crud import upsert_candidate
        upsert_candidate(conn, candidate)

        candidate_id = candidate["candidate_id"]
        conn.execute("DELETE FROM candidate_skills WHERE candidate_id = ?", (candidate_id,))
        conn.execute("DELETE FROM candidate_education WHERE candidate_id = ?", (candidate_id,))
        conn.execute("DELETE FROM candidate_career WHERE candidate_id = ?", (candidate_id,))

        for skill in record.get("skills", []):
            conn.execute(
                """
                INSERT INTO candidate_skills (candidate_id, skill_name, proficiency, endorsements, duration_months, cluster)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    candidate_id,
                    skill.get("name"),
                    skill.get("proficiency", "beginner"),
                    skill.get("endorsements", 0),
                    skill.get("duration_months", 0),
                    skill.get("cluster"),
                ),
            )

        for education in record.get("education", []):
            conn.execute(
                """
                INSERT INTO candidate_education (
                    candidate_id, institution, degree, field_of_study, start_year, end_year, grade, tier
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    candidate_id,
                    education.get("institution"),
                    education.get("degree"),
                    education.get("field_of_study"),
                    education.get("start_year"),
                    education.get("end_year"),
                    education.get("grade"),
                    education.get("tier", "unknown"),
                ),
            )

        for experience in record.get("career_history", []):
            conn.execute(
                """
                INSERT INTO candidate_career (
                    candidate_id, company, title, start_date, end_date, duration_months, is_current, industry, company_size, description
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    candidate_id,
                    experience.get("company"),
                    experience.get("title"),
                    experience.get("start_date"),
                    experience.get("end_date"),
                    experience.get("duration_months", 0),
                    int(bool(experience.get("is_current", False))),
                    experience.get("industry"),
                    experience.get("company_size"),
                    experience.get("description"),
                ),
            )

        count += 1
        if count % 1000 == 0:
            if commit:
                conn.commit()
            logger.info("Seeded %d candidates so far...", count)

    if commit:
        conn.commit()
    return count


def seed_database_if_empty(db_path: Path | None = None) -> int:
    """Populate an empty DB from the persistent dataset, or demo records locally."""
    db_path = Path(db_path) if db_path is not None else get_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        count = conn.execute("SELECT COUNT(*) FROM candidates").fetchone()[0]
        if count > 0:
            return int(count)

        dataset_candidates: Iterable[dict] | None = None
        try:
            from backend.datasets import records_from_dataset

            candidate_path = ensure_candidates_dataset()
            if candidate_path:
                # Keep the 487 MB JSONL streaming; do not load 100K records into RAM.
                dataset_candidates = records_from_dataset(candidate_path)
        except Exception as exc:
            if os.environ.get("CANDIDATES_URL") or os.environ.get("CANDIDATES_PATH"):
                raise RuntimeError("Configured candidate dataset could not be loaded") from exc
            logger.warning("Dataset load skipped: %s", exc)

        if dataset_candidates is None:
            if os.getenv("DEMO_MODE", "true").lower() != "true":
                logger.info("No dataset configured; demo seeding is disabled.")
                return 0
            dataset_candidates = _build_fallback_candidates()
            demo_path = DATA_DIR / "candidates.jsonl" if db_path == DB_PATH else db_path.parent / "candidates.jsonl"
            if not demo_path.exists():
                demo_path.write_text("".join(json.dumps(c) + "\n" for c in dataset_candidates))

        seeded = _seed_database_from_records(conn, dataset_candidates, commit=False)
        conn.commit()
        logger.info("Seeded %d candidates into %s", seeded, db_path)
        return seeded
    finally:
        conn.close()


def init_db(db_path: Path | None = None, schema_path: Path | None = None) -> None:
    """
    Initialize the SQLite database with the backend schema if tables don't exist yet.
    Safe to run multiple times (uses CREATE TABLE IF NOT EXISTS).
    """
    db_path = Path(db_path) if db_path is not None else get_db_path()
    schema_path = Path(schema_path) if schema_path is not None else SCHEMA_PATH
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    with open(schema_path, "r") as f:
        conn.executescript(f.read())
    conn.commit()
    conn.close()
    seeded_count = seed_database_if_empty(db_path)
    logger.info(f"Database initialized at: {db_path} (seeded={seeded_count})")


def get_connection(db_path: Path | None = None) -> sqlite3.Connection:
    """Return a new SQLite connection with row_factory set."""
    db_path = Path(db_path) if db_path is not None else get_db_path()
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")   # Allow concurrent reads during writes
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def get_db() -> Generator[sqlite3.Connection, None, None]:
    """FastAPI dependency — yields a connection and closes it after the request."""
    conn = get_connection()
    try:
        yield conn
    finally:
        conn.close()
