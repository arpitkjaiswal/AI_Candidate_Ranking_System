"""Explainable matching against a supplied role, independent of challenge heuristics.

These scores measure evidence in supplied profiles. They are not calibrated hiring
probabilities and do not establish that a skill claim has been independently verified.
"""
from __future__ import annotations

import math
import re
from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS

_EXCLUDE = set(ENGLISH_STOP_WORDS) | {"senior", "junior", "required", "requirements", "experience", "years", "year", "candidate", "candidates"}
_ALIASES = {"ml": "machine learning", "nlp": "natural language processing", "js": "javascript", "postgres": "postgresql", "sklearn": "scikit learn", "py": "python"}


def words(text: str) -> set[str]:
    return {word for word in re.findall(r"[a-z][a-z0-9+#]*", normalized(text)) if word not in _EXCLUDE}


def normalized(text: str) -> str:
    value = " ".join(re.findall(r"[a-z0-9+#]+", str(text).lower()))
    for alias, expansion in _ALIASES.items():
        value = re.sub(r"(?<![a-z0-9+#])" + re.escape(alias) + r"(?![a-z0-9+#])", expansion, value)
    return value


def contains_phrase(text: str, phrase: str) -> bool:
    return f" {phrase} " in f" {text} " if phrase else False


def build_job_context(description: str, candidates: list[dict]) -> dict:
    """Resolve one consistent skill denominator and per-profile supporting evidence."""
    if not description.strip() or not words(description):
        raise ValueError("Job description needs meaningful text.")
    job_text = normalized(description)
    # Candidate skill names identify skills to compare; only names explicitly present
    # in the job description count. Missing skills never become inferred requirements.
    requested = {}
    for candidate in candidates:
        for skill in candidate.get("skills", []):
            name = str(skill.get("name") or "").strip()
            canonical = normalized(name)
            if contains_phrase(job_text, canonical):
                requested.setdefault(canonical, name)
    requirement = re.search(r"\b(\d{1,2})(?:\s*[-–]\s*(\d{1,2}))?\s*\+?\s*(?:years|yrs)\b", description, re.I)
    minimum_years = int(requirement[1]) if requirement else None
    job_words = words(description)
    matches = {}
    for candidate in candidates:
        profile = candidate.get("profile") or {}
        claimed = {normalized(skill.get("name") or "") for skill in candidate.get("skills", [])}
        matched = sorted(requested[name] for name in requested.keys() & claimed)
        skill_score = len(matched) / len(requested) if requested else 0.0
        title = " ".join([str(profile.get("current_title") or "")] + [str(role.get("title") or "") for role in candidate.get("career_history", [])])
        title_words = words(title)
        title_score = len(title_words & job_words) / len(title_words) if title_words else 0.0
        years = max(0.0, float(profile.get("years_of_experience") or 0))
        experience_score = min(1.0, years / minimum_years) if minimum_years else None
        career_score = .7 * title_score + .3 * experience_score if experience_score is not None else title_score
        matches[candidate["candidate_id"]] = {
            "matched_skills": matched,
            "requested_skills": sorted(requested.values()),
            "skills_match": skill_score,
            "career_relevance": career_score,
            "minimum_years": minimum_years,
            "stated_years": years,
        }
    return {
        "version": 1,
        "description": description,
        "method": "job_description_match",
        "weights": {"semantic_similarity": .6 if requested else .8, "skills_match": .25 if requested else 0, "career_relevance": .15 if requested else .2},
        "candidates": matches,
    }


def score_job_match(context: dict, candidate_id: str, semantic_similarity: float) -> tuple[dict, float, dict]:
    evidence = context["candidates"][candidate_id]
    components = {
        "semantic_similarity": semantic_similarity,
        "skills_match": evidence["skills_match"],
        "career_relevance": evidence["career_relevance"],
    }
    if not all(math.isfinite(float(value)) for value in components.values()):
        raise ValueError("Job matching produced non-finite scores.")
    components = {key: max(0.0, min(1.0, float(value))) for key, value in components.items()}
    final = sum(context["weights"][key] * value for key, value in components.items())
    return components, max(0.0, min(1.0, final)), evidence


def explain_job_match(result: dict) -> str:
    evidence = result["job_match"]
    components = result["component_scores"]
    details = [f"Profile/job text similarity {components['semantic_similarity']:.0%}"]
    if evidence["requested_skills"]:
        skills = ", ".join(evidence["matched_skills"][:5]) or "none listed"
        details.append(f"listed skill matches {len(evidence['matched_skills'])}/{len(evidence['requested_skills'])}: {skills}")
    else:
        details.append("no explicit listed-skill requirements could be resolved from this job")
    if evidence["minimum_years"]:
        details.append(f"{evidence['stated_years']:g} stated years against a {evidence['minimum_years']}-year minimum")
    else:
        details.append(f"career-title overlap {components['career_relevance']:.0%}")
    return "; ".join(details) + ". Based on supplied profile evidence; review suitability before making a hiring decision."
