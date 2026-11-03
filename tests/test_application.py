import json
import time
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient

from backend import database, main, pipeline, crud
from src.embedding_engine import EmbeddingEngine
from src.data_preparation import prepare_all_data


@pytest.fixture
def client(tmp_path, monkeypatch):
    db = tmp_path / 'redrob_candidates.db'
    monkeypatch.setattr(database, 'DATA_DIR', tmp_path)
    monkeypatch.setattr(database, 'DB_PATH', db)
    monkeypatch.setattr(pipeline, 'PRECOMPUTED_DIR', tmp_path)
    monkeypatch.setattr(main, 'init_db', lambda: database.init_db(db))
    monkeypatch.setattr(database, 'get_connection', lambda path=db: connect(path))
    def dependency():
        conn = connect(db)
        try:
            yield conn
        finally:
            conn.close()
    main.app.dependency_overrides[database.get_db] = dependency
    monkeypatch.setenv('DEMO_MODE', 'true')
    with TestClient(main.app) as api:
        yield api, tmp_path
    main.app.dependency_overrides.clear()


def connect(path):
    import sqlite3
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys=ON')
    return conn


def create(api, job='test-job', description='Python machine learning ranking retrieval systems'):
    response = api.post('/api/jobs', json={'job_id': job, 'title': 'ML Engineer', 'description': description})
    assert response.status_code == 201, response.text
    return response.json()


def run(api, top_k=2):
    response = api.post('/api/pipeline/run', json={'job_id': 'test-job', 'top_k': top_k})
    assert response.status_code == 202, response.text
    run_id = response.json()['run_id']
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        result = api.get(f'/api/pipeline/runs/{run_id}').json()
        if result['status'] != 'running':
            assert result['status'] == 'done', result
            return result
        time.sleep(.05)
    pytest.fail('Pipeline did not complete')


def test_candidate_profiles_filters_and_features(client):
    api, _ = client
    assert api.get('/health').status_code == 200
    rows = api.get('/api/candidates').json()
    assert rows['total'] == 2
    for row in rows['candidates']:
        cid = row['candidate_id']
        profile = api.get(f'/api/candidates/{cid}').json()
        assert profile['skills'] and profile['career']
        response = api.get(f'/api/candidates/{cid}/features')
        assert response.status_code == 200, response.text
        assert len(response.json()['features']) > 20
    assert api.get('/api/candidates?country=missing').json()['total'] == 0
    assert api.get('/api/candidates?page=0').status_code == 422
    assert api.get('/api/candidates?min_yoe=10&max_yoe=1').status_code == 422
    assert api.get('/api/candidates/unknown').status_code == 404


def test_pipeline_rerun_replaces_rankings_and_preserves_relations(client):
    api, directory = client
    create(api)
    before = api.get('/api/candidates/CAND_001').json()
    run(api)
    ranking = api.get('/api/jobs/test-job/rankings').json()
    assert ranking['total'] == 2
    assert all(r['reasoning'] and 0 <= r['score'] <= 1 for r in ranking['rankings'])
    run(api, top_k=1)
    assert api.get('/api/jobs/test-job/rankings').json()['total'] == 1
    after = api.get('/api/candidates/CAND_001').json()
    for key in ['skills', 'career', 'education']:
        assert len(before[key]) == len(after[key])
    assert api.get('/api/jobs/test-job').json()['status'] == 'done'
    assert len(list((directory / 'runs').iterdir())) == 2


@pytest.mark.parametrize('body', [
    {'job_id': '', 'title': 'X', 'description': 'Y'},
    {'job_id': '../bad', 'title': 'X', 'description': 'Y'},
    {'job_id': 'valid', 'title': ' ', 'description': 'Y'},
])
def test_invalid_jobs(client, body):
    assert client[0].post('/api/jobs', json=body).status_code == 422


def test_pipeline_validation_and_duplicate_jobs(client):
    api, directory = client
    create(api)
    assert api.post('/api/jobs', json={'job_id': 'test-job', 'title': 'X', 'description': 'Y'}).status_code == 409
    for body in [{'embedding_mode': 'invalid'}, {'top_k': 0}, {'candidates_path': '/etc/passwd'}, {'candidates_path': 'missing.jsonl'}]:
        assert api.post('/api/pipeline/run', json={'job_id': 'test-job', **body}).status_code == 422
    assert api.get('/api/pipeline/runs').json() == []
    conn = connect(directory / 'redrob_candidates.db')
    crud.create_pipeline_run(conn, 'busy-run', 'test-job')
    conn.close()
    assert api.post('/api/pipeline/run', json={'job_id': 'test-job'}).status_code == 409


def test_job_description_changes_similarity(tmp_path):
    records = database._build_fallback_candidates()
    path = tmp_path / 'candidates.jsonl'
    path.write_text(''.join(json.dumps(r) + '\n' for r in records))
    for name, description in [('ml', 'Python machine learning ranking retrieval'), ('sales', 'Sales business development client accounts')]:
        prepare_all_data(str(path), str(tmp_path / name), 'tfidf', job_description=description)
    assert not np.allclose(np.load(tmp_path / 'ml/similarities.npy'), np.load(tmp_path / 'sales/similarities.npy'))


def test_tiny_vocabulary_and_empty_dataset(tmp_path):
    engine = EmbeddingEngine()
    values = engine.fit_tfidf(['python', 'python'])
    assert values.shape == (2, 1)
    assert engine.transform_tfidf(['python']).shape == (1, 1)
    empty = tmp_path / 'empty.jsonl'
    empty.write_text('')
    with pytest.raises(ValueError, match='no valid candidates'):
        prepare_all_data(str(empty), str(tmp_path / 'out'), 'tfidf')


def test_authentication_protects_private_data(client, monkeypatch):
    api, _ = client
    monkeypatch.setenv('APP_PASSWORD', 'integration-only-password')
    assert api.get('/health').status_code == 200
    assert api.get('/api/candidates').status_code == 401
    assert api.get('/api/candidates', auth=('admin', 'wrong')).status_code == 401
    assert api.get('/api/candidates', auth=('admin', 'integration-only-password')).status_code == 200
    assert api.get('/api/jobs', headers={'Authorization': 'Basic broken!'}).status_code == 401


def test_pipeline_failure_is_reported_and_can_retry(client):
    api, directory = client
    create(api)
    empty = directory / 'empty.jsonl'
    empty.write_text('')
    response = api.post('/api/pipeline/run', json={'job_id': 'test-job', 'candidates_path': str(empty)})
    assert response.status_code == 202
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        result = api.get('/api/pipeline/runs/' + response.json()['run_id']).json()
        if result['status'] != 'running':
            break
        time.sleep(.05)
    assert result['status'] == 'failed'
    assert 'no valid candidates' in result['error_message']
    run(api)


def test_cli_produces_valid_submission(tmp_path):
    import copy
    import subprocess
    import sys
    records = database._build_fallback_candidates()
    dataset = tmp_path / 'candidates.jsonl'
    with dataset.open('w') as handle:
        for i in range(120):
            record = copy.deepcopy(records[i % 2])
            record['candidate_id'] = f'CAND_{i:07d}'
            handle.write(json.dumps(record) + '\n')
    artifacts = tmp_path / 'cli'
    output = tmp_path / 'submission.csv'
    for args in [
        ['-m', 'src.precompute', '--candidates', str(dataset), '--output', str(artifacts), '--embedding-mode', 'tfidf'],
        ['rank.py', '--candidates', str(dataset), '--precomputed-dir', str(artifacts), '--out', str(output)],
        ['validate_submission.py', str(output)],
    ]:
        result = subprocess.run([sys.executable, *args], capture_output=True, text=True, timeout=30)
        assert result.returncode == 0, result.stdout + result.stderr
    assert len(output.read_text().splitlines()) == 101


def test_restart_marks_interrupted_runs_failed(tmp_path, monkeypatch):
    db = tmp_path / 'restart.db'
    database.init_db(db)
    conn = connect(db)
    crud.create_job(conn, 'interrupted', 'ML role', 'Python retrieval')
    crud.create_pipeline_run(conn, 'interrupted-run', 'interrupted')
    crud.update_job_status(conn, 'interrupted', 'running')
    conn.close()
    monkeypatch.setattr(main, 'init_db', lambda: database.init_db(db))
    monkeypatch.setattr(database, 'get_connection', lambda: connect(db))
    with TestClient(main.app):
        conn = connect(db)
        assert crud.get_job(conn, 'interrupted')['status'] == 'failed'
        assert crud.get_pipeline_run(conn, 'interrupted-run')['status'] == 'failed'
        conn.close()
