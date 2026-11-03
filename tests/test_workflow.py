"""Run with: venv/bin/python -m unittest discover -s tests -v"""
import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
from fastapi.testclient import TestClient
from backend.main import app
from backend import database, pipeline
from backend.database import _build_fallback_candidates, get_connection
from src.embedding_engine import EmbeddingEngine


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.runtime = tempfile.TemporaryDirectory(prefix="redrob-tests-")
        self.addCleanup(self.runtime.cleanup)
        directory = Path(self.runtime.name)
        # Isolate configuration per test without changing other suites at import time.
        patches = [
            patch.dict(os.environ, {"DATA_DIR": str(directory), "DEMO_MODE": "true",
                                    "CANDIDATES_PATH": "", "CANDIDATES_URL": "", "APP_PASSWORD": ""}),
            patch.object(database, "DATA_DIR", directory),
            patch.object(database, "DB_PATH", directory / "redrob_candidates.db"),
            patch.object(pipeline, "PRECOMPUTED_DIR", directory),
        ]
        for item in patches:
            item.start()
            self.addCleanup(item.stop)
        self.client_context = TestClient(app)
        self.client = self.client_context.__enter__()
        self.dataset = Path(self.runtime.name) / "candidates.jsonl"
        self.dataset.write_text("\n".join(json.dumps(c) for c in _build_fallback_candidates()))
        with get_connection() as conn:
            conn.execute("DELETE FROM rankings")
            conn.execute("DELETE FROM pipeline_runs")
            conn.execute("DELETE FROM jobs")

    def tearDown(self):
        self.client_context.__exit__(None, None, None)

    def create_job(self, job_id="ml-engineer", description="Python NLP semantic search ranking retrieval"):
        response = self.client.post("/api/jobs", json={"job_id": job_id, "title": "ML Engineer", "description": description})
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def run_pipeline(self, top_k=2):
        response = self.client.post("/api/pipeline/run", json={"job_id": "ml-engineer", "top_k": top_k})
        self.assertEqual(response.status_code, 202, response.text)
        run_id = response.json()["run_id"]
        for _ in range(200):
            run = self.client.get(f"/api/pipeline/runs/{run_id}").json()
            if run["status"] != "running":
                self.assertEqual(run["status"], "done", run)
                return run
            time.sleep(0.05)
        self.fail("Pipeline did not finish within 10 seconds")

    def test_health_candidates_and_features(self):
        self.assertEqual(self.client.get("/health").status_code, 200)
        candidates = self.client.get("/api/candidates?size=1").json()
        self.assertGreaterEqual(candidates["total"], 2)
        cid = candidates["candidates"][0]["candidate_id"]
        self.assertEqual(self.client.get(f"/api/candidates/{cid}").status_code, 200)
        self.assertEqual(self.client.get(f"/api/candidates/{cid}/features").status_code, 200)

    def test_job_validation_and_duplicates(self):
        for changes in ({"title": "   "}, {"job_id": "bad/id"}, {"description": ""}):
            body = {"job_id": "valid", "title": "Engineer", "description": "Python"} | changes
            self.assertEqual(self.client.post("/api/jobs", json=body).status_code, 422)
        self.create_job()
        self.assertEqual(self.client.post("/api/jobs", json={"job_id": "ml-engineer", "title": "Other", "description": "Other"}).status_code, 409)

    def test_invalid_pipeline_inputs(self):
        self.create_job()
        for changes in ({"embedding_mode": "invalid"}, {"top_k": 0}, {"candidates_path": "/etc/passwd"}, {"candidates_path": "missing.jsonl"}):
            self.assertEqual(self.client.post("/api/pipeline/run", json={"job_id": "ml-engineer"} | changes).status_code, 422)
        self.assertEqual(self.client.get("/api/pipeline/runs").json(), [])

    def test_experience_filters(self):
        for query in ("min_yoe=-1", "min_yoe=10&max_yoe=2", "page=0"):
            self.assertEqual(self.client.get(f"/api/candidates?{query}").status_code, 422)

    def test_repeated_pipeline_preserves_profiles_and_replaces_rankings(self):
        self.create_job()
        first = self.run_pipeline()
        ranks = self.client.get("/api/jobs/ml-engineer/rankings").json()
        self.assertEqual(ranks["total"], 2)
        with get_connection() as conn:
            before = conn.execute("SELECT COUNT(*) FROM candidate_skills").fetchone()[0]
        second = self.run_pipeline(top_k=1)
        self.assertNotEqual(first["run_id"], second["run_id"])
        self.assertEqual(self.client.get("/api/jobs/ml-engineer/rankings").json()["total"], 1)
        with get_connection() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM candidate_skills").fetchone()[0], before)

    def test_job_description_changes_similarity(self):
        from src.data_preparation import prepare_all_data
        paths = []
        for i, description in enumerate(("Python ML ranking retrieval semantic search", "Baking bread sourdough pastry kitchen")):
            output = Path(self.runtime.name) / f"description-{i}"
            prepare_all_data(str(self.dataset), str(output), "tfidf", job_description=description)
            paths.append(np.load(output / "similarities.npy"))
        self.assertFalse(np.allclose(*paths))

    def test_tiny_tfidf_corpus(self):
        for corpus in (["python", "python"], ["python", "java"], ["python"]):
            engine = EmbeddingEngine()
            result = engine.fit_tfidf(corpus)
            self.assertEqual(result.shape[0], len(corpus))
            self.assertTrue(np.isfinite(result).all())
            self.assertEqual(engine.transform_tfidf(["python"]).shape[1], result.shape[1])

    def test_candidate_search(self):
        result = self.client.get("/api/candidates", params={"search": "Ava"}).json()
        self.assertEqual(result["total"], 1)
        self.assertEqual(result["candidates"][0]["candidate_id"], "CAND_001")
        self.assertEqual(self.client.get("/api/candidates", params={"search": "%"}).json()["total"], 0)

    def test_unrelated_tiny_documents_stay_unrelated(self):
        engine = EmbeddingEngine()
        embeddings = engine.fit_tfidf(["python", "java"])
        similarity = engine.compute_similarity(embeddings[0], embeddings[1:])[0]
        self.assertAlmostEqual(float(similarity), 0.0)

    def test_empty_dataset_records_failure(self):
        self.create_job()
        self.dataset.write_text("")
        # An explicit source must fail if empty; default runs intentionally use the DB.
        response = self.client.post("/api/pipeline/run", json={"job_id": "ml-engineer", "candidates_path": str(self.dataset)})
        self.assertEqual(response.status_code, 202)
        run_id = response.json()["run_id"]
        for _ in range(200):
            run = self.client.get(f"/api/pipeline/runs/{run_id}").json()
            if run["status"] != "running":
                self.assertEqual(run["status"], "failed")
                self.assertIn("no valid candidates", run["error_message"])
                return
            time.sleep(.05)
        self.fail("Empty dataset run never completed")

    def test_concurrent_run_rejected(self):
        self.create_job()
        with get_connection() as conn:
            conn.execute("INSERT INTO pipeline_runs(run_id,job_id) VALUES ('reserved','ml-engineer')")
        self.assertEqual(self.client.post("/api/pipeline/run", json={"job_id": "ml-engineer"}).status_code, 409)


if __name__ == "__main__":
    unittest.main()
