"""
backend/schemas.py
Pydantic v2 models for all API request/response bodies.
Mirrors the SQLite schema in backend/schema.sql.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Literal
from pydantic import ConfigDict
from pydantic import BaseModel, Field, model_validator


# ─── Candidate ────────────────────────────────────────────────────────────────

class CandidateBase(BaseModel):
    candidate_id: str
    anonymized_name: Optional[str] = None
    headline: Optional[str] = None
    summary: Optional[str] = None
    location: Optional[str] = None
    country: Optional[str] = None
    years_of_experience: float = 0.0
    current_title: Optional[str] = None
    current_company: Optional[str] = None
    current_company_size: Optional[str] = None
    current_industry: Optional[str] = None
    open_to_work: bool = False
    willing_to_relocate: bool = False
    preferred_work_mode: Optional[str] = None
    notice_period_days: Optional[int] = None
    expected_salary_min: Optional[float] = None
    expected_salary_max: Optional[float] = None
    github_activity_score: Optional[float] = None
    profile_completeness_score: float = 0.0
    linkedin_connected: bool = False
    verified_email: bool = False
    verified_phone: bool = False
    last_active_date: Optional[str] = None
    signup_date: Optional[str] = None


class CandidateSkill(BaseModel):
    id: int
    skill_name: str
    proficiency: Optional[str] = None
    endorsements: int = 0
    duration_months: int = 0
    cluster: Optional[str] = None


class CandidateEducation(BaseModel):
    id: int
    institution: Optional[str] = None
    degree: Optional[str] = None
    field_of_study: Optional[str] = None
    start_year: Optional[int] = None
    end_year: Optional[int] = None
    grade: Optional[str] = None
    tier: Optional[str] = None


class CandidateCareer(BaseModel):
    id: int
    company: Optional[str] = None
    title: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    duration_months: Optional[int] = None
    is_current: bool = False
    industry: Optional[str] = None
    company_size: Optional[str] = None
    description: Optional[str] = None


class CandidateDetail(CandidateBase):
    """Full profile including nested relations."""
    skills: List[CandidateSkill] = []
    education: List[CandidateEducation] = []
    career: List[CandidateCareer] = []


# ─── Rankings ─────────────────────────────────────────────────────────────────

class RankingResult(BaseModel):
    id: Optional[int] = None
    job_id: str
    candidate_id: str
    rank: int
    score: float
    career_score: Optional[float] = None
    skill_score: Optional[float] = None
    behavioral_score: Optional[float] = None
    education_score: Optional[float] = None
    embedding_sim: Optional[float] = None
    is_honeypot: bool = False
    reasoning: Optional[str] = None
    created_at: Optional[str] = None


class RankedCandidateDetail(RankingResult):
    """Ranking result + candidate profile fields."""
    anonymized_name: Optional[str] = None
    headline: Optional[str] = None
    location: Optional[str] = None
    country: Optional[str] = None
    years_of_experience: float = 0.0
    current_title: Optional[str] = None
    current_company: Optional[str] = None
    open_to_work: bool = False
    willing_to_relocate: bool = False
    preferred_work_mode: Optional[str] = None
    notice_period_days: Optional[int] = None
    github_activity_score: Optional[float] = None


# ─── Jobs ─────────────────────────────────────────────────────────────────────

class JobCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    job_id: str = Field(min_length=1, max_length=100, pattern=r"^[a-zA-Z0-9_-]+$")
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=50000)


class JobResponse(BaseModel):
    job_id: str
    title: str
    description: str
    created_at: Optional[str] = None
    status: str = "pending"


# ─── Pipeline ─────────────────────────────────────────────────────────────────

class PipelineRunRequest(BaseModel):
    job_id: str
    candidates_path: str = Field(
        default="./candidates.jsonl",
        description="Path to candidates JSONL file (server-side path)"
    )
    top_k: int = Field(default=100, ge=1, le=1000)
    embedding_mode: Literal["tfidf", "sentence_transformers"] = Field(
        default="tfidf",
        description="'tfidf' (fast, no GPU) or 'sentence_transformers' (better quality)"
    )


class PipelineRunStatus(BaseModel):
    run_id: str
    job_id: str
    status: str   # running | done | failed
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    total_candidates: Optional[int] = None
    error_message: Optional[str] = None


# ─── Pagination ───────────────────────────────────────────────────────────────

class PaginatedCandidates(BaseModel):
    total: int
    page: int
    size: int
    candidates: List[CandidateBase]


class PaginatedRankings(BaseModel):
    total: int
    page: int
    size: int
    job_id: str
    rankings: List[RankedCandidateDetail]


# ─── Feature analysis ─────────────────────────────────────────────────────────

class CandidateFeatures(BaseModel):
    candidate_id: str
    features: Dict[str, Any]
    component_scores: Optional[Dict[str, float]] = None


# ─── Generic responses ────────────────────────────────────────────────────────

class MessageResponse(BaseModel):
    message: str

class ErrorResponse(BaseModel):
    detail: str
