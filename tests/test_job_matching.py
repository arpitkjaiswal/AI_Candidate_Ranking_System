import json
import math

import numpy as np
import pytest

from src.data_preparation import prepare_all_data
from src.embedding_engine import EmbeddingEngine
from src.ranking_engine import rank_candidates
from src.job_matching import build_job_context
from src.reasoning_generator import generate_all_reasoning


def candidate(identifier, title, summary, skills):
    return {
        "candidate_id": identifier,
        "profile": {"current_title": title, "headline": title, "summary": summary, "years_of_experience": 6},
        "career_history": [{"title": title, "description": summary, "duration_months": 72}],
        "skills": [{"name": skill, "duration_months": 36, "proficiency": "advanced"} for skill in skills],
        "education": [], "redrob_signals": {},
    }


def test_job_changes_winner_without_senior_ai_penalties(tmp_path):
    records = [
        candidate("ML", "Machine Learning Engineer", "Python machine learning ranking retrieval production models", ["Python", "PyTorch", "Machine Learning"]),
        candidate("SALES", "Sales Account Executive", "Sales CRM enterprise revenue client accounts negotiation", ["Sales", "CRM", "Negotiation"]),
    ]
    dataset = tmp_path / "candidates.jsonl"
    dataset.write_text("".join(json.dumps(record) + "\n" for record in records))
    for expected, description in [
        ("ML", "Machine Learning Engineer: Python PyTorch ranking models, minimum 5 years experience"),
        ("SALES", "Sales Account Executive: Sales CRM negotiation enterprise revenue, 5 years experience"),
    ]:
        output = tmp_path / expected
        prepare_all_data(str(dataset), str(output), "tfidf", job_description=description)
        ranked = generate_all_reasoning(rank_candidates(str(output)), str(output))
        assert ranked[0]["candidate_id"] == expected
        assert ranked[0]["score"] > ranked[1]["score"]
        assert ranked[0]["job_match"]["matched_skills"]
        assert "non-technical current role" not in ranked[0]["reasoning"]
        assert "listed skill matches" in ranked[0]["reasoning"]
        assert all(math.isfinite(row["score"]) and 0 <= row["score"] <= 1 for row in ranked)
        assert "education_location" not in ranked[0]["component_scores"]


def test_single_candidate_does_not_gain_perfect_similarity(tmp_path):
    engine = EmbeddingEngine()
    texts = ["Python ranking retrieval", "Sales CRM revenue"]
    embedding = engine.fit_tfidf(texts)
    assert engine.compute_similarity(embedding[0], embedding[1:])[0] == pytest.approx(0)
    assert engine.compute_similarity(embedding[0], engine.transform_tfidf([texts[0]]))[0] == pytest.approx(1)
    engine.save(str(tmp_path / "engine.pkl"))
    restored = EmbeddingEngine.load(str(tmp_path / "engine.pkl"))
    assert np.allclose(restored.transform_tfidf(texts), embedding)


def test_empty_profile_is_valid_but_empty_job_is_rejected(tmp_path):
    dataset = tmp_path / "empty-profile.jsonl"
    dataset.write_text(json.dumps(candidate("EMPTY", "", "", [])) + "\n")
    prepare_all_data(str(dataset), str(tmp_path / "out"), "tfidf", job_description="Python engineer")
    result = rank_candidates(str(tmp_path / "out"))[0]
    assert result["score"] == pytest.approx(0)
    with pytest.raises(ValueError, match="meaningful text"):
        prepare_all_data(str(dataset), str(tmp_path / "empty"), "tfidf", job_description=" ")


def test_skill_aliases_are_resolved_in_job_text():
    profile = candidate("NLP", "NLP engineer", "Language processing", ["Natural Language Processing", "Python"])
    context = build_job_context("NLP engineer using py", [profile])
    assert len(context["candidates"]["NLP"]["matched_skills"]) == 2
