"""
backend/main.py
FastAPI application — Redrob AI Candidate Ranking Engine API

Routes:
  GET  /health                              — Health check
  GET  /api/candidates                      — List candidates (paginated, filtered)
  GET  /api/candidates/{candidate_id}       — Full candidate profile
  GET  /api/candidates/{candidate_id}/features — ML feature analysis

  GET  /api/jobs                            — List all jobs
  POST /api/jobs                            — Create a new job posting
  GET  /api/jobs/{job_id}                   — Get a single job
  GET  /api/jobs/{job_id}/rankings          — Get paginated rankings for a job
  GET  /api/jobs/{job_id}/rankings/{cid}    — Single candidate ranking for a job

  POST /api/pipeline/run                    — Trigger a full pipeline run (async)
  GET  /api/pipeline/runs                   — List all pipeline runs
  GET  /api/pipeline/runs/{run_id}          — Get pipeline run status

Run with:
  uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
"""
from __future__ import annotations

import logging
import os
import sys
import threading
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import List, Optional

from fastapi import Depends, FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware

# ─── Ensure project root is on path ──────────────────────────────────────────
ROOT_DIR = Path(__file__).parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

# ─── Local imports ────────────────────────────────────────────────────────────
from backend.database import get_db, init_db
from backend.schemas import (
    CandidateBase,
    CandidateDetail,
    CandidateFeatures,
    ErrorResponse,
    JobCreate,
    JobResponse,
    MessageResponse,
    PaginatedCandidates,
    PaginatedRankings,
    PipelineRunRequest,
    PipelineRunStatus,
    RankedCandidateDetail,
    RankingResult,
)
from backend import crud

import sqlite3

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


# ─── App ──────────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize the SQLite database on startup."""
    init_db()
    logger.info("Database initialized successfully.")
    yield


app = FastAPI(
    title="Redrob AI Candidate Ranking Engine",
    description=(
        "REST API for the AI Candidate Ranking Engine. "
        "Provides access to candidate profiles, ML-generated rankings, "
        "and pipeline management endpoints."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(","),
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ═══════════════════════════════════════════════════════════════════════════════
# Health
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/health", tags=["Health"], response_model=MessageResponse)
def health_check():
    """Returns 200 OK if the service is alive."""
    return {"message": "Redrob Ranking Engine API is running."}


# ═══════════════════════════════════════════════════════════════════════════════
# Candidates
# ═══════════════════════════════════════════════════════════════════════════════

@app.get(
    "/api/candidates",
    tags=["Candidates"],
    response_model=PaginatedCandidates,
    summary="List candidates with optional filters",
)
def list_candidates(
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    size: int = Query(50, ge=1, le=500, description="Results per page"),
    country: Optional[str] = Query(None, description="Filter by country (case-insensitive)"),
    search: Optional[str] = Query(None, max_length=200, description="Search name, title or company"),
    open_to_work: Optional[bool] = Query(None, description="Filter by open-to-work flag"),
    min_yoe: Optional[float] = Query(None, ge=0, description="Minimum years of experience"),
    max_yoe: Optional[float] = Query(None, ge=0, description="Maximum years of experience"),
    conn: sqlite3.Connection = Depends(get_db),
):
    if min_yoe is not None and max_yoe is not None and min_yoe > max_yoe:
        raise HTTPException(status_code=422, detail="Minimum experience must not exceed maximum experience")
    offset = (page - 1) * size
    total, candidates = crud.list_candidates(
        conn,
        limit=size,
        offset=offset,
        country=country,
        search=search,
        open_to_work=open_to_work,
        min_yoe=min_yoe,
        max_yoe=max_yoe,
    )
    return {
        "total": total,
        "page": page,
        "size": size,
        "candidates": candidates,
    }


@app.get(
    "/api/candidates/{candidate_id}",
    tags=["Candidates"],
    response_model=CandidateDetail,
    summary="Get full candidate profile (career, education, skills)",
    responses={404: {"model": ErrorResponse}},
)
def get_candidate(candidate_id: str, conn: sqlite3.Connection = Depends(get_db)):
    data = crud.get_candidate_full(conn, candidate_id)
    if not data:
        raise HTTPException(status_code=404, detail=f"Candidate '{candidate_id}' not found.")
    return data


@app.get(
    "/api/candidates/{candidate_id}/features",
    tags=["Candidates"],
    response_model=CandidateFeatures,
    summary="Run feature extraction on a single candidate (live, no precomputed needed)",
    responses={404: {"model": ErrorResponse}},
)
def get_candidate_features(candidate_id: str, conn: sqlite3.Connection = Depends(get_db)):
    """
    Fetches the candidate's raw_json blob from the DB and runs the 
    feature extraction pipeline live to return all 50+ features.
    """
    import json as _json

    row = crud.get_candidate(conn, candidate_id)
    if not row:
        raise HTTPException(status_code=404, detail=f"Candidate '{candidate_id}' not found.")

    raw_json = row.get("raw_json")
    if not raw_json:
        raise HTTPException(
            status_code=422,
            detail="Candidate exists in DB but has no raw JSON blob for feature extraction."
        )

    try:
        candidate = _json.loads(raw_json)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to parse raw_json: {exc}")

    try:
        from src.data_cleaner import clean_candidate_dict
        from src.feature_extractor import extract_all_features

        cleaned = clean_candidate_dict(candidate)
        features = extract_all_features(cleaned)
    except Exception as exc:
        logger.exception(f"Feature extraction failed for {candidate_id}")
        raise HTTPException(status_code=500, detail=f"Feature extraction error: {exc}")

    return {
        "candidate_id": candidate_id,
        "features": features,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Jobs
# ═══════════════════════════════════════════════════════════════════════════════

@app.get(
    "/api/jobs",
    tags=["Jobs"],
    response_model=List[JobResponse],
    summary="List all job postings",
)
def list_jobs(conn: sqlite3.Connection = Depends(get_db)):
    return crud.list_jobs(conn)


@app.post(
    "/api/jobs",
    tags=["Jobs"],
    response_model=JobResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new job posting",
)
def create_job(body: JobCreate, conn: sqlite3.Connection = Depends(get_db)):
    if crud.get_job(conn, body.job_id):
        raise HTTPException(
            status_code=409,
            detail=f"Job '{body.job_id}' already exists. Use a unique job_id.",
        )
    job = crud.create_job(conn, body.job_id, body.title, body.description)
    return job


@app.get(
    "/api/jobs/{job_id}",
    tags=["Jobs"],
    response_model=JobResponse,
    summary="Get a single job posting",
    responses={404: {"model": ErrorResponse}},
)
def get_job(job_id: str, conn: sqlite3.Connection = Depends(get_db)):
    job = crud.get_job(conn, job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")
    return job


# ═══════════════════════════════════════════════════════════════════════════════
# Rankings
# ═══════════════════════════════════════════════════════════════════════════════

@app.get(
    "/api/jobs/{job_id}/rankings",
    tags=["Rankings"],
    response_model=PaginatedRankings,
    summary="Get paginated rankings for a job",
    responses={404: {"model": ErrorResponse}},
)
def get_rankings(
    job_id: str,
    page: int = Query(1, ge=1),
    size: int = Query(100, ge=1, le=500),
    min_score: Optional[float] = Query(None, ge=0.0, le=1.0),
    honeypots_only: bool = Query(False),
    conn: sqlite3.Connection = Depends(get_db),
):
    if not crud.get_job(conn, job_id):
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")

    offset = (page - 1) * size
    total, rankings = crud.get_rankings(
        conn,
        job_id=job_id,
        limit=size,
        offset=offset,
        min_score=min_score,
        honeypots_only=honeypots_only,
    )
    return {
        "total": total,
        "page": page,
        "size": size,
        "job_id": job_id,
        "rankings": rankings,
    }


@app.get(
    "/api/jobs/{job_id}/rankings/{candidate_id}",
    tags=["Rankings"],
    response_model=RankingResult,
    summary="Get ranking detail for a specific candidate in a job",
    responses={404: {"model": ErrorResponse}},
)
def get_ranking_detail(
    job_id: str,
    candidate_id: str,
    conn: sqlite3.Connection = Depends(get_db),
):
    result = crud.get_ranking_for_candidate(conn, job_id, candidate_id)
    if not result:
        raise HTTPException(
            status_code=404,
            detail=f"No ranking for candidate '{candidate_id}' in job '{job_id}'.",
        )
    return result


# ═══════════════════════════════════════════════════════════════════════════════
# Pipeline
# ═══════════════════════════════════════════════════════════════════════════════

@app.post(
    "/api/pipeline/run",
    tags=["Pipeline"],
    response_model=PipelineRunStatus,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Trigger a full ML ranking pipeline run (runs in background)",
)
def trigger_pipeline(body: PipelineRunRequest, conn: sqlite3.Connection = Depends(get_db)):
    """
    Kicks off the full ML pipeline in a background thread:
    1. Loads candidates from the JSONL file
    2. Runs feature extraction + embeddings
    3. Ranks candidates
    4. Saves results to SQLite

    Returns a run_id immediately. Poll GET /api/pipeline/runs/{run_id} for status.
    """
    job = crud.get_job(conn, body.job_id)
    if not job:
        raise HTTPException(
            status_code=404,
            detail=f"Job '{body.job_id}' not found. Create it first via POST /api/jobs.",
        )

    from backend.database import get_candidates_path, get_data_dir
    candidates_path = Path(body.candidates_path).expanduser()
    if body.candidates_path == "./candidates.jsonl":
        candidates_path = get_candidates_path()
    elif not candidates_path.is_absolute():
        candidates_path = ROOT_DIR / candidates_path
    candidates_path = candidates_path.resolve()
    roots = (ROOT_DIR.resolve(), get_data_dir().resolve())
    if not any(candidates_path.is_relative_to(root) for root in roots):
        raise HTTPException(status_code=422, detail="Dataset must be inside the project or DATA_DIR")
    if not candidates_path.is_file():
        raise HTTPException(status_code=422, detail="Candidate dataset not found. Configure CANDIDATES_PATH or add a JSONL dataset.")

    # Reserve the worker atomically across concurrent requests and API processes.
    conn.execute("BEGIN IMMEDIATE")
    if conn.execute("SELECT 1 FROM pipeline_runs WHERE status = 'running' LIMIT 1").fetchone():
        conn.rollback()
        raise HTTPException(status_code=409, detail="A pipeline is already running. Wait for it to finish.")
    run_id = str(uuid.uuid4())
    conn.execute("INSERT INTO pipeline_runs (run_id, job_id) VALUES (?, ?)", (run_id, body.job_id))
    conn.execute("UPDATE jobs SET status = 'running' WHERE job_id = ?", (body.job_id,))
    conn.commit()

    # Launch pipeline in background thread so the API responds immediately
    def _run():
        from backend.pipeline import run_full_pipeline
        run_full_pipeline(
            run_id=run_id,
            job_id=body.job_id,
            candidates_path=str(candidates_path),
            top_k=body.top_k,
            embedding_mode=body.embedding_mode,
        )

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    logger.info(f"Pipeline run {run_id} started in background thread.")

    return crud.get_pipeline_run(conn, run_id)


@app.get(
    "/api/pipeline/runs",
    tags=["Pipeline"],
    response_model=List[PipelineRunStatus],
    summary="List all pipeline runs",
)
def list_pipeline_runs(
    job_id: Optional[str] = Query(None),
    conn: sqlite3.Connection = Depends(get_db),
):
    return crud.list_pipeline_runs(conn, job_id=job_id)


@app.get(
    "/api/pipeline/runs/{run_id}",
    tags=["Pipeline"],
    response_model=PipelineRunStatus,
    summary="Get the status of a specific pipeline run",
    responses={404: {"model": ErrorResponse}},
)
def get_pipeline_run(run_id: str, conn: sqlite3.Connection = Depends(get_db)):
    run = crud.get_pipeline_run(conn, run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Pipeline run '{run_id}' not found.")
    return run
