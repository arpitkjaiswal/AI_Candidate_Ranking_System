"""
Task 7: Implement Embeddings

TF-IDF + TruncatedSVD embedding engine (no external model download needed).
Also supports sentence-transformers if available for higher quality.

The engine creates text representations of candidates and the JD,
then computes semantic similarity between them.
"""

import logging
import os
import time
import pickle
import numpy as np
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class EmbeddingEngine:
    """
    Embedding engine with two modes:
    1. TF-IDF + TruncatedSVD (default, no external deps, fast)
    2. Sentence-Transformers (optional, higher quality, needs download)
    """

    def __init__(self, mode: str = "tfidf", model_name: str = "all-MiniLM-L6-v2"):
        self.mode = mode
        self.model_name = model_name
        self._vectorizer = None
        self._svd = None
        self._st_model = None
        self._embedding_dim = 256  # For TF-IDF + SVD

    def fit_tfidf(self, texts: list[str]):
        """Fit TF-IDF + SVD on a corpus of texts."""
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.decomposition import TruncatedSVD

        logger.info(f"Fitting TF-IDF on {len(texts)} documents...")
        start = time.time()

        self._vectorizer = TfidfVectorizer(
            max_features=50000,
            min_df=1,
            max_df=1.0,
            ngram_range=(1, 2),
            sublinear_tf=True,
            strip_accents="unicode",
        )
        try:
            tfidf_matrix = self._vectorizer.fit_transform(texts)
        except ValueError as exc:
            raise ValueError("Candidate and job descriptions need meaningful text.") from exc

        logger.info(f"TF-IDF matrix shape: {tfidf_matrix.shape}")

        # Reduce dimensionality with SVD
        n_components = min(self._embedding_dim, tfidf_matrix.shape[1] - 1, tfidf_matrix.shape[0] - 1)
        # Low-rank SVD on tiny corpora can turn unrelated documents into the
        # same one-dimensional vector. Preserve the original TF-IDF geometry.
        self._svd = None
        if tfidf_matrix.shape[1] < 2 or tfidf_matrix.shape[0] <= self._embedding_dim:
            embeddings = tfidf_matrix.toarray()
        else:
            self._svd = TruncatedSVD(n_components=max(1, n_components), random_state=42)
            embeddings = self._svd.fit_transform(tfidf_matrix)

        elapsed = time.time() - start
        logger.info(f"TF-IDF + SVD fit complete in {elapsed:.1f}s. "
                     f"Embedding dim: {embeddings.shape[1]}")

        return embeddings

    def transform_tfidf(self, texts: list[str]) -> np.ndarray:
        """Transform new texts using fitted TF-IDF + SVD."""
        if self._vectorizer is None:
            raise RuntimeError("Must call fit_tfidf() first")

        tfidf_matrix = self._vectorizer.transform(texts)
        embeddings = self._svd.transform(tfidf_matrix) if self._svd is not None else tfidf_matrix.toarray()
        return embeddings

    def encode_texts(self, texts: list[str], batch_size: int = 256) -> np.ndarray:
        """
        Encode texts into embeddings using the configured mode.
        """
        if self.mode == "sentence_transformers":
            return self._encode_st(texts, batch_size)
        else:
            return self._encode_tfidf(texts)

    def _encode_tfidf(self, texts: list[str]) -> np.ndarray:
        """Encode using TF-IDF + SVD."""
        if self._vectorizer is None:
            # Fit on the provided texts (for single-batch use)
            return self.fit_tfidf(texts)
        return self.transform_tfidf(texts)

    def _encode_st(self, texts: list[str], batch_size: int = 256) -> np.ndarray:
        """Encode using sentence-transformers."""
        try:
            from sentence_transformers import SentenceTransformer

            if self._st_model is None:
                logger.info(f"Loading sentence-transformers model: {self.model_name}")
                self._st_model = SentenceTransformer(self.model_name)

            logger.info(f"Encoding {len(texts)} texts with sentence-transformers...")
            start = time.time()
            embeddings = self._st_model.encode(
                texts,
                batch_size=batch_size,
                show_progress_bar=True,
                normalize_embeddings=True,
            )
            elapsed = time.time() - start
            logger.info(f"Encoded {len(texts)} texts in {elapsed:.1f}s")
            return embeddings

        except ImportError:
            logger.warning("sentence-transformers not available, falling back to TF-IDF")
            self.mode = "tfidf"
            return self._encode_tfidf(texts)

    def compute_similarity(
        self,
        query_embedding: np.ndarray,
        candidate_embeddings: np.ndarray,
    ) -> np.ndarray:
        """
        Compute cosine similarity between a query and all candidates.
        Returns array of similarity scores.
        """
        # Normalize embeddings
        query_norm = query_embedding / (np.linalg.norm(query_embedding) + 1e-10)
        if len(candidate_embeddings.shape) == 1:
            candidate_embeddings = candidate_embeddings.reshape(1, -1)

        norms = np.linalg.norm(candidate_embeddings, axis=1, keepdims=True) + 1e-10
        candidates_norm = candidate_embeddings / norms

        # Cosine similarity
        if len(query_norm.shape) == 1:
            query_norm = query_norm.reshape(1, -1)

        similarities = (candidates_norm @ query_norm.T).flatten()

        # Clamp to [0, 1]
        similarities = np.clip(similarities, 0, 1)

        return similarities

    def save(self, path: str):
        """Save the fitted model to disk."""
        save_data = {
            "mode": self.mode,
            "model_name": self.model_name,
            "embedding_dim": self._embedding_dim,
        }

        if self.mode == "tfidf" and self._vectorizer is not None:
            save_data["vectorizer"] = self._vectorizer
            save_data["svd"] = self._svd

        with open(path, "wb") as f:
            pickle.dump(save_data, f)

        logger.info(f"Saved embedding engine to {path}")

    @classmethod
    def load(cls, path: str) -> "EmbeddingEngine":
        """Load a fitted model from disk."""
        with open(path, "rb") as f:
            save_data = pickle.load(f)

        engine = cls(
            mode=save_data["mode"],
            model_name=save_data.get("model_name", "all-MiniLM-L6-v2"),
        )
        engine._embedding_dim = save_data.get("embedding_dim", 256)

        if "vectorizer" in save_data:
            engine._vectorizer = save_data["vectorizer"]
            engine._svd = save_data["svd"]

        logger.info(f"Loaded embedding engine from {path} (mode={engine.mode})")
        return engine


def build_candidate_text(data: dict) -> str:
    """
    Build a rich text representation of a candidate for embedding.
    Combines headline, summary, career descriptions, and skill names.
    """
    parts = []

    profile = data.get("profile", {})

    # Headline (important, concise self-description)
    headline = profile.get("headline", "")
    if headline:
        parts.append(headline)

    # Summary (professional narrative)
    summary = profile.get("summary", "")
    if summary:
        parts.append(summary)

    # Current title and company
    title = profile.get("current_title", "")
    company = profile.get("current_company", "")
    if title:
        parts.append(f"Currently working as {title} at {company}")

    # Career descriptions (rich information about actual work)
    for entry in data.get("career_history", []):
        desc = entry.get("description", "")
        entry_title = entry.get("title", "")
        if desc:
            parts.append(f"{entry_title}: {desc}")

    # Skill names
    skill_names = [s.get("name", "") for s in data.get("skills", []) if s.get("name")]
    if skill_names:
        parts.append(f"Skills: {', '.join(skill_names)}")

    # Certifications
    for cert in data.get("certifications", []):
        cert_name = cert.get("name", "")
        if cert_name:
            parts.append(f"Certification: {cert_name}")

    return " ".join(parts)


def build_jd_text() -> str:
    """
    Build the job description text for embedding.
    Structured to emphasize what the JD actually requires.
    """
    return (
        "Senior AI Engineer at a Series A AI-native talent intelligence platform. "
        "Own the intelligence layer: ranking, retrieval, and matching systems for "
        "recruiter search and candidate-job matching. "
        "Ship a v2 ranking system with embeddings, hybrid retrieval, and LLM-based re-ranking. "
        "Set up evaluation infrastructure with offline benchmarks, A/B testing, "
        "and recruiter-feedback loops. "
        "Must have production experience with embeddings-based retrieval systems "
        "using sentence-transformers, BGE, E5, or similar models deployed to real users. "
        "Must have production experience with vector databases or hybrid search: "
        "Pinecone, Weaviate, Qdrant, Milvus, OpenSearch, Elasticsearch, FAISS. "
        "Strong Python. Hands-on experience designing evaluation frameworks for "
        "ranking systems: NDCG, MRR, MAP, offline-to-online correlation, A/B testing. "
        "Nice to have: LLM fine-tuning with LoRA, QLoRA, PEFT. "
        "Learning-to-rank models with XGBoost. HR-tech or marketplace experience. "
        "Distributed systems and large-scale inference optimization. "
        "Open-source contributions in AI/ML. "
        "5-9 years experience, ideally 6-8 total with 4-5 in applied ML/AI "
        "at product companies. Shipped end-to-end ranking, search, or recommendation "
        "systems to real users at meaningful scale. "
        "Located in or willing to relocate to Pune or Noida, India."
    )
