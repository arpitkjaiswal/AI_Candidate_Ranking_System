"""
Task 5: Prepare Data for AI Models

Orchestrates data loading, cleaning, feature extraction, and embedding
generation. Produces pre-computed artifacts for the ranking step.
"""

import json
import logging
import os
import time
import pickle
import numpy as np
from pathlib import Path

from .data_loader import load_candidates_stream, load_job_description
from .data_cleaner import clean_candidate_dict
from .feature_extractor import extract_all_features
from .embedding_engine import EmbeddingEngine, build_candidate_text, build_jd_text

logger = logging.getLogger(__name__)


def prepare_all_data(
    candidates_path: str,
    output_dir: str,
    embedding_mode: str = "sentence_transformers",
    populate_sqlite: bool = False,
    job_description: str | None = None,
) -> dict:
    """
    Full data preparation pipeline:
    1. Load and clean all candidates
    2. Extract features for each candidate
    3. Build text representations
    4. Generate embeddings
    5. Save everything to disk

    Args:
        candidates_path: Path to candidates.jsonl
        output_dir: Directory to save pre-computed artifacts
        embedding_mode: "tfidf" or "sentence_transformers"

    Returns:
        dict with paths to saved artifacts
    """
    os.makedirs(output_dir, exist_ok=True)
    start_time = time.time()

    # ─── Step 1: Load and Clean ──────────────────────────────────────────
    logger.info("Step 1: Loading and cleaning candidates...")
    candidates_data = []
    candidate_ids = []

    for raw_data in load_candidates_stream(candidates_path):
        cleaned = clean_candidate_dict(raw_data)
        candidates_data.append(cleaned)
        candidate_ids.append(cleaned["candidate_id"])

    if not candidates_data:
        raise ValueError("Dataset contains no valid candidates.")
    if len(candidate_ids) != len(set(candidate_ids)):
        raise ValueError("Dataset contains duplicate candidate IDs.")
    logger.info(f"Loaded {len(candidates_data)} candidates")

    # ─── Step 2: Extract Features ────────────────────────────────────────
    logger.info("Step 2: Extracting features...")
    all_features = {}
    for i, data in enumerate(candidates_data):
        cid = data["candidate_id"]
        features = extract_all_features(data)
        all_features[cid] = features

        if (i + 1) % 10000 == 0:
            logger.info(f"  Extracted features for {i + 1}/{len(candidates_data)}")

    logger.info(f"Feature extraction complete for {len(all_features)} candidates")

    # ─── Step 3: Build Text Representations ──────────────────────────────
    logger.info("Step 3: Building text representations...")
    candidate_texts = []
    for data in candidates_data:
        text = build_candidate_text(data)
        candidate_texts.append(text)

    jd_text = build_jd_text() if job_description is None else job_description
    job_context = None
    if job_description is not None:
        from .job_matching import build_job_context
        job_context = build_job_context(job_description, candidates_data)

    # ─── Step 4: Generate Embeddings ─────────────────────────────────────
    logger.info(f"Step 4: Generating embeddings (mode={embedding_mode})...")
    engine = EmbeddingEngine(mode=embedding_mode)

    # Fit on all candidate texts + JD text
    all_texts = [jd_text] + candidate_texts
    all_embeddings = engine.fit_tfidf(all_texts) if embedding_mode == "tfidf" else engine.encode_texts(all_texts)

    jd_embedding = all_embeddings[0]
    candidate_embeddings = all_embeddings[1:]

    # Compute similarities
    similarities = engine.compute_similarity(jd_embedding, candidate_embeddings)

    logger.info(f"Embedding shape: {candidate_embeddings.shape}")
    logger.info(f"Similarity range: [{similarities.min():.4f}, {similarities.max():.4f}]")

    # ─── Step 5: Save Artifacts ──────────────────────────────────────────
    logger.info("Step 5: Saving pre-computed artifacts...")

    # Custom roles use their own context; CLI challenge runs retain legacy scoring.
    context_path = Path(output_dir) / "job_context.json"
    if job_context is not None:
        context_path.write_text(json.dumps(job_context, ensure_ascii=False), encoding="utf-8")
    else:
        context_path.unlink(missing_ok=True)

    # Save candidate IDs
    ids_path = os.path.join(output_dir, "candidate_ids.json")
    with open(ids_path, "w") as f:
        json.dump(candidate_ids, f)

    # Save features
    features_path = os.path.join(output_dir, "features.pkl")
    with open(features_path, "wb") as f:
        pickle.dump(all_features, f)

    # Save embeddings
    embeddings_path = os.path.join(output_dir, "candidate_embeddings.npy")
    np.save(embeddings_path, candidate_embeddings)

    jd_embedding_path = os.path.join(output_dir, "jd_embedding.npy")
    np.save(jd_embedding_path, jd_embedding)

    # Save similarities
    similarities_path = os.path.join(output_dir, "similarities.npy")
    np.save(similarities_path, similarities)

    # Save embedding engine
    engine_path = os.path.join(output_dir, "embedding_engine.pkl")
    engine.save(engine_path)

    # Save cleaned candidate data (lightweight version for reasoning)
    # Only save essential fields to reduce size
    lightweight_candidates = {}
    for data in candidates_data:
        cid = data["candidate_id"]
        lightweight_candidates[cid] = {
            "candidate_id": cid,
            "profile": data["profile"],
            "career_history": [
                {
                    "company": e.get("company", ""),
                    "title": e.get("title", ""),
                    "duration_months": e.get("duration_months", 0),
                    "is_current": e.get("is_current", False),
                    "industry": e.get("industry", ""),
                }
                for e in data.get("career_history", [])
            ],
            "skills": [
                {
                    "name": s.get("name", ""),
                    "proficiency": s.get("proficiency", ""),
                }
                for s in data.get("skills", [])
            ],
            "education": [
                {
                    "degree": e.get("degree", ""),
                    "field_of_study": e.get("field_of_study", ""),
                    "tier": e.get("tier", "unknown"),
                }
                for e in data.get("education", [])
            ],
        }

    candidates_lite_path = os.path.join(output_dir, "candidates_lite.pkl")
    with open(candidates_lite_path, "wb") as f:
        pickle.dump(lightweight_candidates, f)

    if populate_sqlite:
        logger.info("Populating SQLite database for teammate integration...")
        try:
            from .db_populator import setup_database, populate_candidates, populate_computed_features
            db_path = os.path.join(output_dir, "redrob_candidates.db")
            schema_path = os.path.join(os.path.dirname(__file__), "schema.sql")
            conn = setup_database(db_path, schema_path)
            populate_candidates(conn, candidates_data)
            populate_computed_features(conn, all_features)
            conn.close()
        except Exception as e:
            logger.error(f"Failed to populate SQLite: {e}")

    elapsed = time.time() - start_time
    logger.info(f"Data preparation complete in {elapsed:.1f}s")

    return {
        "candidate_ids": ids_path,
        "features": features_path,
        "embeddings": embeddings_path,
        "jd_embedding": jd_embedding_path,
        "similarities": similarities_path,
        "engine": engine_path,
        "candidates_lite": candidates_lite_path,
        "num_candidates": len(candidates_data),
    }
