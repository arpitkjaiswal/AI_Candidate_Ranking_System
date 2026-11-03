"""
Task 8 (cont): Reasoning Generator

Generates personalized 1-2 sentence reasoning for each ranked candidate.
Reasoning is specific to the candidate's actual profile data — not templated.
"""

import logging
import os
import pickle
from typing import Optional

logger = logging.getLogger(__name__)


def generate_reasoning(
    candidate_result: dict,
    candidate_data: Optional[dict] = None,
) -> str:
    """
    Generate a personalized reasoning string for a ranked candidate.

    Args:
        candidate_result: Dict with score, component_scores, features
        candidate_data: Optional lightweight candidate data for richer reasoning

    Returns:
        1-2 sentence reasoning string
    """
    if "job_match" in candidate_result:
        from .job_matching import explain_job_match
        return explain_job_match(candidate_result)

    features = candidate_result.get("features", {})
    component_scores = candidate_result.get("component_scores", {})
    score = candidate_result.get("score", 0)

    parts = []

    # ─── Primary signal: title and experience ────────────────────────────
    if candidate_data:
        profile = candidate_data.get("profile", {})
        title = profile.get("current_title", "Unknown")
        company = profile.get("current_company", "Unknown")
        yoe = profile.get("years_of_experience", 0)

        parts.append(f"{title} at {company} with {yoe:.1f} yrs experience")
    else:
        yoe = features.get("total_experience_years", 0)
        parts.append(f"{yoe:.1f} yrs total experience")

    # ─── Strengths ───────────────────────────────────────────────────────
    strengths = []

    # Skills
    must_have = features.get("must_have_clusters_matched", 0)
    if must_have >= 5:
        strengths.append(f"matches {must_have}/6 core skill clusters")
    elif must_have >= 3:
        strengths.append(f"matches {must_have}/6 core skill clusters")

    # ML experience
    ml_yrs = features.get("estimated_ml_experience_years", 0)
    if ml_yrs >= 3:
        strengths.append(f"{ml_yrs:.1f} yrs ML/AI experience")

    # Product company
    product_ratio = features.get("product_company_ratio", 0)
    if product_ratio > 0.7:
        strengths.append("strong product-company background")
    elif product_ratio > 0.4:
        strengths.append("mixed product/consulting background")

    # Production signals
    if features.get("has_production_signals", 0) > 0.5:
        strengths.append("production deployment experience")

    # Specific cluster highlights
    if features.get("cluster_embeddings_retrieval_matched", 0) > 0:
        strengths.append("embeddings/retrieval experience")
    if features.get("cluster_vector_databases_matched", 0) > 0:
        strengths.append("vector database experience")
    if features.get("cluster_ranking_recommendation_systems_matched", 0) > 0:
        strengths.append("ranking/recommendation systems")
    if features.get("cluster_ranking_evaluation_matched", 0) > 0:
        strengths.append("ranking evaluation expertise")
    if features.get("cluster_llm_finetuning_matched", 0) > 0:
        strengths.append("LLM fine-tuning skills")

    # Location
    location_score = features.get("location_match_score", 0)
    if location_score >= 0.85:
        if candidate_data:
            loc = candidate_data.get("profile", {}).get("location", "")
            if loc:
                strengths.append(f"located in {loc}")

    # GitHub activity
    github = features.get("github_activity_score", 0)
    if github > 0.5:
        strengths.append("active GitHub profile")

    # ─── Behavioral highlights ───────────────────────────────────────────
    response_rate = features.get("recruiter_response_rate", 0)
    if response_rate > 0.6:
        strengths.append(f"response rate {response_rate:.0%}")

    open_to_work = features.get("open_to_work", 0)
    if open_to_work > 0.5:
        strengths.append("open to work")

    notice_days = features.get("notice_period_days", 90)
    if notice_days <= 30:
        strengths.append(f"{notice_days}-day notice period")

    # ─── Weaknesses (for lower-ranked candidates) ────────────────────────
    weaknesses = []

    if features.get("consulting_only_flag", 0) > 0.5:
        weaknesses.append("consulting-only career background")

    if features.get("is_non_relevant_title", 0) > 0.5:
        weaknesses.append("non-technical current role")

    if features.get("keyword_stuffer_score", 0) > 0.3:
        weaknesses.append("skill claims exceed career evidence")

    if features.get("is_likely_honeypot", 0) > 0.5:
        weaknesses.append("profile contains inconsistencies")

    if features.get("is_title_chaser", 0) > 0.5:
        weaknesses.append("frequent job changes")

    if response_rate < 0.2 and response_rate > 0:
        weaknesses.append(f"low response rate ({response_rate:.0%})")

    if notice_days > 90:
        weaknesses.append(f"long notice period ({notice_days} days)")

    # ─── Compose reasoning ───────────────────────────────────────────────
    # Take top 3-4 strengths and top 1-2 weaknesses
    top_strengths = strengths[:4]
    top_weaknesses = weaknesses[:2]

    reasoning_parts = parts.copy()

    if top_strengths:
        reasoning_parts.append("; ".join(top_strengths))

    if top_weaknesses and score < 0.7:
        reasoning_parts.append("however " + "; ".join(top_weaknesses))

    reasoning = ". ".join(reasoning_parts)

    # Ensure it's not too long (keep under 200 chars is good)
    if len(reasoning) > 300:
        reasoning = reasoning[:297] + "..."

    # Clean up any double periods
    reasoning = reasoning.replace("..", ".").replace(";.", ".")

    return reasoning


def generate_all_reasoning(
    ranked_candidates: list[dict],
    precomputed_dir: str,
) -> list[dict]:
    """
    Generate reasoning for all ranked candidates.

    Args:
        ranked_candidates: List of ranked candidate dicts from ranking_engine
        precomputed_dir: Directory with pre-computed data

    Returns:
        Same list with 'reasoning' field added
    """
    # Load lightweight candidate data for richer reasoning
    candidates_lite_path = os.path.join(precomputed_dir, "candidates_lite.pkl")
    candidates_lite = {}
    if os.path.exists(candidates_lite_path):
        with open(candidates_lite_path, "rb") as f:
            candidates_lite = pickle.load(f)

    for candidate in ranked_candidates:
        cid = candidate["candidate_id"]
        candidate_data = candidates_lite.get(cid)
        candidate["reasoning"] = generate_reasoning(candidate, candidate_data)

    return ranked_candidates
