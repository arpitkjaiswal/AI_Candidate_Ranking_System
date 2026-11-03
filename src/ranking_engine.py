"""
Task 8: Build Recommendation/Matching Engine

Hybrid scoring pipeline that combines:
1. Semantic similarity (embedding match)
2. Structured skill matching
3. Career relevance
4. Behavioral signals
5. Education + location fit

With honeypot detection and disqualifier filtering.
"""

import json
import logging
import os
import time
import pickle
import numpy as np
from typing import Optional

logger = logging.getLogger(__name__)

# ─── Scoring Weights ─────────────────────────────────────────────────────────
# These are the default weights. Can be tuned via tune_weights.py.

DEFAULT_WEIGHTS = {
    "semantic_similarity": 0.20,      # Embedding match (JD ↔ candidate text)
    "skills_match": 0.30,             # Structured skill cluster matching
    "career_relevance": 0.25,         # Title, experience, product-company history
    "behavioral_signals": 0.15,       # Redrob signals composite
    "education_location": 0.10,       # Education + location fit
}


def compute_component_scores(features: dict, semantic_sim: float) -> dict:
    """
    Compute individual component scores from features.
    Each score is normalized to [0, 1].
    """
    scores = {}

    # ─── 1. Semantic Similarity Score ────────────────────────────────────
    scores["semantic_similarity"] = float(semantic_sim)

    # ─── 2. Skills Match Score ───────────────────────────────────────────
    # Weighted combination of must-have and nice-to-have cluster matches
    must_have_score = features.get("must_have_clusters_score", 0)
    nice_to_have_score = features.get("nice_to_have_score", 0)
    trust_score = features.get("avg_skill_trust_score", 0)
    stuffer_penalty = features.get("keyword_stuffer_score", 0)

    skills_raw = (
        0.60 * must_have_score
        + 0.20 * nice_to_have_score
        + 0.20 * trust_score
    )
    # Penalize keyword stuffers
    skills_raw *= (1.0 - 0.8 * stuffer_penalty)

    scores["skills_match"] = max(0.0, min(1.0, skills_raw))

    # ─── 3. Career Relevance Score ───────────────────────────────────────
    title_relevance = features.get("current_title_relevance", 0)
    best_title = features.get("best_title_relevance", 0)
    experience_fit = features.get("experience_fit_score", 0)
    ml_experience = features.get("estimated_ml_experience_years", 0)
    product_ratio = features.get("product_company_ratio", 0)
    production_signals = features.get("has_production_signals", 0)
    consulting_only = features.get("consulting_only_flag", 0)
    is_title_chaser = features.get("is_title_chaser", 0)
    is_non_relevant = features.get("is_non_relevant_title", 0)

    # ML experience fit (4-5 years ideal)
    if 4 <= ml_experience <= 6:
        ml_fit = 1.0
    elif 3 <= ml_experience <= 8:
        ml_fit = 0.8
    elif 2 <= ml_experience <= 10:
        ml_fit = 0.5
    elif ml_experience > 0:
        ml_fit = 0.2
    else:
        ml_fit = 0.0

    career_raw = (
        0.25 * max(title_relevance, best_title * 0.8)  # Current or best title
        + 0.20 * experience_fit
        + 0.20 * ml_fit
        + 0.15 * product_ratio
        + 0.10 * production_signals
        + 0.10 * (1.0 - is_non_relevant)  # Penalty for non-relevant titles
    )

    # Hard penalties
    if consulting_only > 0.5:
        career_raw *= 0.15  # Severe penalty per JD
    if is_title_chaser > 0.5:
        career_raw *= 0.5

    scores["career_relevance"] = max(0.0, min(1.0, career_raw))

    # ─── 4. Behavioral Signals Score ─────────────────────────────────────
    availability = features.get("availability_score", 0)
    engagement = features.get("engagement_score", 0)
    reliability = features.get("reliability_score", 0)
    notice_score = features.get("notice_period_score", 0)
    github_score = features.get("github_activity_score", 0)
    verification = features.get("verification_score", 0)
    work_mode = features.get("work_mode_score", 0)
    saved_score = features.get("saved_by_recruiters_score", 0)

    behavioral_raw = (
        0.30 * availability
        + 0.15 * engagement
        + 0.15 * reliability
        + 0.15 * notice_score
        + 0.10 * github_score
        + 0.05 * verification
        + 0.05 * work_mode
        + 0.05 * saved_score
    )

    scores["behavioral_signals"] = max(0.0, min(1.0, behavioral_raw))

    # ─── 5. Education + Location Score ───────────────────────────────────
    edu_tier = features.get("education_tier_score", 0)
    degree_relevance = features.get("relevant_degree_score", 0)
    advanced_degree = features.get("has_advanced_degree", 0)
    location_match = features.get("location_match_score", 0)

    edu_location_raw = (
        0.40 * location_match
        + 0.25 * degree_relevance
        + 0.20 * edu_tier
        + 0.15 * advanced_degree
    )

    scores["education_location"] = max(0.0, min(1.0, edu_location_raw))

    return scores


def compute_final_score(
    component_scores: dict,
    features: dict,
    weights: Optional[dict] = None,
) -> float:
    """
    Compute final weighted score with honeypot and disqualifier penalties.
    """
    if weights is None:
        weights = DEFAULT_WEIGHTS

    # Weighted sum
    weighted_sum = sum(
        weights.get(key, 0) * component_scores.get(key, 0)
        for key in weights
    )

    # ─── Penalty multipliers ─────────────────────────────────────────────
    # Honeypot penalty
    honeypot_score = features.get("honeypot_score", 0)
    if honeypot_score >= 0.6:
        weighted_sum *= 0.01  # Effectively zero
    elif honeypot_score >= 0.4:
        weighted_sum *= 0.1
    elif honeypot_score >= 0.2:
        weighted_sum *= 0.5

    # Keyword stuffer penalty (additional to skills component)
    stuffer = features.get("keyword_stuffer_score", 0)
    if stuffer >= 0.6:
        weighted_sum *= 0.15
    elif stuffer >= 0.3:
        weighted_sum *= 0.5

    # Non-relevant title with no ML career history = very poor fit
    if (features.get("is_non_relevant_title", 0) > 0.5
            and features.get("estimated_ml_experience_months", 0) < 6):
        weighted_sum *= 0.1

    return max(0.0, min(1.0, weighted_sum))


def rank_candidates(
    precomputed_dir: str,
    weights: Optional[dict] = None,
    top_k: int = 100,
) -> list[dict]:
    """
    Main ranking function. Loads pre-computed data and produces ranked results.

    Args:
        precomputed_dir: Directory with pre-computed artifacts
        weights: Optional custom scoring weights
        top_k: Number of top candidates to return

    Returns:
        List of dicts with candidate_id, rank, score, component_scores, features
    """
    if top_k < 1:
        raise ValueError("top_k must be positive")
    start_time = time.time()

    # ─── Load pre-computed data ──────────────────────────────────────────
    logger.info("Loading pre-computed data...")

    with open(os.path.join(precomputed_dir, "candidate_ids.json"), "r") as f:
        candidate_ids = json.load(f)

    with open(os.path.join(precomputed_dir, "features.pkl"), "rb") as f:
        all_features = pickle.load(f)

    similarities = np.load(os.path.join(precomputed_dir, "similarities.npy"))
    if not candidate_ids or len(candidate_ids) != len(similarities):
        raise ValueError("Ranking artifacts are empty or inconsistent.")

    if not np.isfinite(similarities).all():
        raise ValueError("Ranking similarities contain non-finite values.")
    context_path = os.path.join(precomputed_dir, "job_context.json")
    job_context = None
    if os.path.exists(context_path):
        with open(context_path, encoding="utf-8") as context_file:
            job_context = json.load(context_file)

    logger.info(f"Loaded data for {len(candidate_ids)} candidates")

    # ─── Score all candidates ────────────────────────────────────────────
    logger.info("Computing scores...")
    scored_candidates = []

    for i, cid in enumerate(candidate_ids):
        features = all_features.get(cid, {})
        semantic_sim = float(similarities[i])

        evidence = None
        if job_context is not None:
            from .job_matching import score_job_match
            component_scores, final_score, evidence = score_job_match(job_context, cid, semantic_sim)
        else:
            component_scores = compute_component_scores(features, semantic_sim)
            final_score = compute_final_score(component_scores, features, weights)

        scored_candidates.append({
            "candidate_id": cid,
            "score": final_score,
            "component_scores": component_scores,
            "features": features,
            **({"job_match": evidence, "ranking_method": "job_description_match"} if evidence is not None else {}),
        })

    # ─── Sort and select top-K ───────────────────────────────────────────
    # Sort by score descending, then by candidate_id ascending for tiebreaks
    scored_candidates.sort(
        key=lambda x: (-x["score"], x["candidate_id"])
    )

    # Assign ranks
    top_candidates = scored_candidates[:top_k]
    for rank, candidate in enumerate(top_candidates, 1):
        candidate["rank"] = rank

    elapsed = time.time() - start_time
    logger.info(
        f"Ranking complete in {elapsed:.1f}s. "
        f"Top score: {top_candidates[0]['score']:.4f}, "
        f"Bottom score: {top_candidates[-1]['score']:.4f}"
    )

    if job_context is not None:
        logger.info("Ranked candidates against the supplied job description.")
        return top_candidates

    # Log some stats
    honeypot_count = sum(
        1 for c in top_candidates
        if c["features"].get("is_likely_honeypot", 0) > 0.5
    )
    consulting_count = sum(
        1 for c in top_candidates
        if c["features"].get("consulting_only_flag", 0) > 0.5
    )
    non_relevant_count = sum(
        1 for c in top_candidates
        if c["features"].get("is_non_relevant_title", 0) > 0.5
        and c["features"].get("estimated_ml_experience_months", 0) < 12
    )

    logger.info(f"Top-{top_k} stats: "
                f"{honeypot_count} likely honeypots, "
                f"{consulting_count} consulting-only, "
                f"{non_relevant_count} non-relevant titles")

    return top_candidates
