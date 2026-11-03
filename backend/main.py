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
from contextlib import asynccontextmanager, closing
from pathlib import Path
from typing import List, Optional

from fastapi import Depends, FastAPI, HTTPException, Query, Request, status
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
    from backend.database import get_connection
    with closing(get_connection()) as conn:
        conn.execute("UPDATE jobs SET status='failed' WHERE status='running'")
        conn.execute("UPDATE pipeline_runs SET status='failed', finished_at=datetime('now'), error_message='Server restarted before this run completed. Please retry.' WHERE status='running'")
        conn.commit()
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
    allow_origins=[s.strip() for s in os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",") if s.strip()],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Optional HTTP Basic protection for private deployments. TLS must terminate at the host.
# The browser supplies credentials for both the SPA and same-origin API requests.
@app.middleware("http")
async def protect_deployment(request, call_next):
    import base64
    import secrets
    from fastapi.responses import JSONResponse
    password = os.getenv("APP_PASSWORD")
    if password and request.url.path != "/health":
        authorized = False
        try:
            scheme, encoded = request.headers.get("authorization", "").split(" ", 1)
            username, supplied = base64.b64decode(encoded, validate=True).decode("utf-8").split(":", 1)
            authorized = scheme.lower() == "basic" and secrets.compare_digest(username.encode(), os.getenv("APP_USERNAME", "admin").encode()) and secrets.compare_digest(supplied.encode(), password.encode())
        except (ValueError, UnicodeDecodeError):
            pass
        if not authorized:
            return JSONResponse({"detail": "Authentication required."}, status_code=401, headers={"WWW-Authenticate": 'Basic realm="Redrob", charset="UTF-8"'})
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "same-origin"
    return response


# ═══════════════════════════════════════════════════════════════════════════════
# Health
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/health", tags=["Health"], response_model=MessageResponse)
def health_check():
    """Returns 200 OK if the service is alive."""
    from backend.database import get_connection
    with closing(get_connection()) as conn:
        conn.execute("SELECT 1 FROM candidates LIMIT 1").fetchone()
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
    open_to_work: Optional[bool] = Query(None, description="Filter by open-to-work flag"),
    min_yoe: Optional[float] = Query(None, ge=0, description="Minimum years of experience"),
    max_yoe: Optional[float] = Query(None, ge=0, description="Maximum years of experience"),
    conn: sqlite3.Connection = Depends(get_db),
):
    if min_yoe is not None and max_yoe is not None and min_yoe > max_yoe:
        raise HTTPException(status_code=422, detail="Minimum experience cannot exceed maximum experience.")
    offset = (page - 1) * size
    total, candidates = crud.list_candidates(
        conn,
        limit=size,
        offset=offset,
        country=country,
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
    try:
        job = crud.create_job(conn, body.job_id, body.title, body.description)
    except sqlite3.IntegrityError:
        conn.rollback()
        raise HTTPException(status_code=409, detail="Job ID already exists.")
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


# Candidate data is imported locally; no cloud/model credentials are needed.
@app.get("/api/system", tags=["System"])
def system_status(conn: sqlite3.Connection = Depends(get_db)):
    import importlib.util
    from backend.database import get_candidates_path
    counts = {name: conn.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
              for name in ("candidates", "jobs", "rankings")}
    modes = ["tfidf"]
    if importlib.util.find_spec("sentence_transformers") is not None:
        modes.append("sentence_transformers")
    return {"total_candidates": counts["candidates"], "total_jobs": counts["jobs"],
            "total_rankings": counts["rankings"], "dataset_available": bool(counts["candidates"]) or get_candidates_path().is_file(),
            "default_candidates_path": "./candidates.jsonl", "demo_mode": os.getenv("DEMO_MODE", "true").lower() == "true",
            "embedding_modes": modes}


@app.post("/api/datasets", status_code=201, tags=["Candidates"])
async def upload_dataset(request: Request, filename: str = Query("candidates.jsonl", max_length=200),
                         conn: sqlite3.Connection = Depends(get_db)):
    import tempfile
    from starlette.concurrency import run_in_threadpool
    from backend.database import get_data_dir, _seed_database_from_records
    from backend.datasets import MAX_UPLOAD_BYTES, validate_dataset, records_from_dataset
    if not filename.lower().endswith(".jsonl"):
        raise HTTPException(status_code=422, detail="Upload a JSONL file, with one candidate object per line.")
    length = request.headers.get("content-length")
    if length and (not length.isdigit() or int(length) > MAX_UPLOAD_BYTES):
        raise HTTPException(status_code=413, detail="Upload exceeds the 50 MiB limit.")
    upload_dir = get_data_dir() / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    dataset_id = str(uuid.uuid4())
    destination = upload_dir / f"{dataset_id}.jsonl"
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(dir=upload_dir, suffix=".part", delete=False) as handle:
            temp_path = Path(handle.name)
            size = 0
            async for chunk in request.stream():
                size += len(chunk)
                if size > MAX_UPLOAD_BYTES:
                    raise HTTPException(status_code=413, detail="Upload exceeds the 50 MiB limit.")
                handle.write(chunk)
        try:
            total = await run_in_threadpool(validate_dataset, temp_path)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

        def publish():
            try:
                conn.execute("BEGIN IMMEDIATE")
                if conn.execute("SELECT 1 FROM pipeline_runs WHERE status='running' LIMIT 1").fetchone():
                    raise HTTPException(status_code=409, detail="Wait for the active pipeline to finish before importing candidates.")
                conn.execute("CREATE TEMP TABLE import_ids (candidate_id TEXT PRIMARY KEY)")
                conn.executemany("INSERT INTO import_ids VALUES (?)", ((row["candidate_id"],) for row in records_from_dataset(temp_path)))
                # Changed profiles invalidate old scores; unrelated jobs/profiles are preserved.
                conn.execute("UPDATE jobs SET status='pending' WHERE job_id IN (SELECT job_id FROM rankings WHERE candidate_id IN (SELECT candidate_id FROM import_ids))")
                conn.execute("DELETE FROM rankings WHERE candidate_id IN (SELECT candidate_id FROM import_ids)")
                _seed_database_from_records(conn, records_from_dataset(temp_path), commit=False)
                temp_path.replace(destination)
                conn.commit()
            except BaseException:
                conn.rollback()
                destination.unlink(missing_ok=True)
                raise
        await run_in_threadpool(publish)
        return {"dataset_id": dataset_id, "filename": Path(filename).name, "candidates_path": str(destination), "total_candidates": total}
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


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
    run_id = str(uuid.uuid4())
    candidate_path = get_candidates_path() if body.candidates_path == "./candidates.jsonl" else Path(body.candidates_path)
    use_database = body.candidates_path == "./candidates.jsonl" and bool(conn.execute("SELECT 1 FROM candidates LIMIT 1").fetchone())
    if use_database:
        snapshot_dir = get_data_dir() / "snapshots"
        snapshot_dir.mkdir(parents=True, exist_ok=True)
        candidate_path = snapshot_dir / f"{run_id}.jsonl"
    if not candidate_path.is_absolute():
        candidate_path = ROOT_DIR / candidate_path
    candidate_path = candidate_path.resolve()
    roots = (ROOT_DIR.resolve(), get_data_dir().resolve())
    if not any(candidate_path.is_relative_to(root) for root in roots):
        raise HTTPException(status_code=422, detail="Dataset must be inside the project or DATA_DIR.")
    if not use_database and not candidate_path.is_file():
        raise HTTPException(status_code=422, detail="Candidate dataset is missing. Configure CANDIDATES_PATH or use demo mode.")
    if candidate_path.suffix not in {".jsonl", ".gz"}:
        raise HTTPException(status_code=422, detail="Dataset must be JSONL or gzipped JSONL.")
    # Serialize admission across requests and processes. SQLite is a single-worker deployment.
    try:
        conn.execute("BEGIN IMMEDIATE")
        if conn.execute("SELECT 1 FROM pipeline_runs WHERE status = 'running' LIMIT 1").fetchone():
            conn.rollback()
            raise HTTPException(status_code=409, detail="A pipeline is already running. Try again after it finishes.")
        # Snapshot under the same write reservation as admission so concurrent
        # uploads cannot replace profiles between snapshot and run creation.
        if use_database:
            import json
            with candidate_path.open("w", encoding="utf-8") as snapshot:
                for row in conn.execute("SELECT raw_json FROM candidates ORDER BY candidate_id"):
                    if not row["raw_json"]:
                        raise HTTPException(status_code=422, detail="A candidate has no source profile. Reimport that candidate before ranking.")
                    try:
                        snapshot.write(json.dumps(json.loads(row["raw_json"])) + "\n")
                    except ValueError as exc:
                        raise HTTPException(status_code=422, detail="A candidate has an invalid source profile. Reimport it before ranking.") from exc
        conn.execute("INSERT INTO pipeline_runs (run_id, job_id, status) VALUES (?, ?, 'running')", (run_id, body.job_id))
        conn.execute("UPDATE jobs SET status = 'running' WHERE job_id = ?", (body.job_id,))
        conn.commit()
    except BaseException:
        conn.rollback()
        if use_database:
            candidate_path.unlink(missing_ok=True)
        raise

    # Launch pipeline in background thread so the API responds immediately
    def _run():
        from backend.pipeline import run_full_pipeline
        run_full_pipeline(
            run_id=run_id,
            job_id=body.job_id,
            candidates_path=str(candidate_path),
            top_k=body.top_k,
            embedding_mode=body.embedding_mode,
        )

    thread = threading.Thread(target=_run, daemon=True)
    try:
        thread.start()
    except RuntimeError:
        crud.finish_pipeline_run(conn, run_id, "failed", error_message="Worker could not start.")
        crud.update_job_status(conn, body.job_id, "failed")
        raise HTTPException(status_code=503, detail="Pipeline worker is unavailable.")
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


# A single production origin serves the UI and API; Vite is only needed in development.
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

FRONTEND_DIST = ROOT_DIR / "frontend" / "dist"
if FRONTEND_DIST.is_dir():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def frontend(path: str):
        if path == "api" or path.startswith("api/"):
            raise HTTPException(status_code=404, detail="API endpoint not found.")
        file = (FRONTEND_DIST / path).resolve()
        if not file.is_relative_to(FRONTEND_DIST.resolve()):
            raise HTTPException(status_code=404, detail="Not found.")
        if file.is_file():
            return FileResponse(file)
        return FileResponse(FRONTEND_DIST / "index.html")
