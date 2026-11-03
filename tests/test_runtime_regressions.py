"""Every ingestion path must be strict and existing rankings must stay truthful."""
import copy
import gzip
import json
import sqlite3
from pathlib import Path

import pytest

from backend import crud, database, pipeline
from tests.test_application import client
from tests.test_pipeline_integrity import stored_run


def test_startup_canonicalizes_nullable_collections(tmp_path, monkeypatch):
    dataset = tmp_path / 'source.jsonl'
    record = {'candidate_id': 'NULLABLE', 'profile': None, 'skills': None,
              'education': None, 'career_history': None, 'redrob_signals': None}
    dataset.write_text(json.dumps(record))
    monkeypatch.setenv('CANDIDATES_PATH', str(dataset))
    monkeypatch.delenv('CANDIDATES_URL', raising=False)
    db = tmp_path / 'data.db'
    database.init_db(db)
    with database.get_connection(db) as conn:
        profile = crud.get_candidate_full(conn, 'NULLABLE')
        assert profile['years_of_experience'] == 0
        assert profile['skills'] == []
        assert profile['career'] == []


@pytest.mark.parametrize('bad_suffix', ['not json', json.dumps({'candidate_id': 'DUPLICATE'})])
def test_invalid_startup_dataset_never_partially_seeds(tmp_path, monkeypatch, bad_suffix):
    dataset = tmp_path / 'source.jsonl'
    dataset.write_text(json.dumps({'candidate_id': 'DUPLICATE'}) + '\n' + bad_suffix)
    monkeypatch.setenv('CANDIDATES_PATH', str(dataset))
    monkeypatch.delenv('CANDIDATES_URL', raising=False)
    db = tmp_path / 'data.db'
    with pytest.raises(ValueError):
        database.init_db(db)
    with sqlite3.connect(db) as conn:
        assert conn.execute('SELECT count(*) FROM candidates').fetchone()[0] == 0


def test_utf16_upload_is_rejected_before_database_publication(client):
    api, directory = client
    data = json.dumps({'candidate_id': 'UTF16', 'profile': {'headline': 'Python engineer'}}).encode('utf-16')
    response = api.post('/api/datasets?filename=utf16.jsonl', content=data,
                        headers={'Content-Type': 'application/octet-stream'})
    assert response.status_code == 422, response.text
    assert api.get('/api/candidates').json()['total'] == 2
    assert not list((directory / 'uploads').glob('*'))


def other_job(conn):
    crud.create_job(conn, 'other-job', 'Different job', 'Python engineer')
    crud.upsert_rankings_batch(conn, 'other-job', [
        {'candidate_id': 'CAND_001', 'rank': 1, 'score': .9},
        {'candidate_id': 'CAND_002', 'rank': 2, 'score': .8},
    ])
    crud.update_job_status(conn, 'other-job', 'done')


def test_changed_pipeline_profiles_invalidate_other_job_scores(stored_run):
    conn, db, dataset = stored_run
    other_job(conn)
    pipeline.run_full_pipeline('run', 'job', str(dataset), db_path=db)
    assert crud.get_pipeline_run(conn, 'run')['status'] == 'done'
    assert crud.get_job(conn, 'other-job')['status'] == 'pending'
    assert crud.get_ranking_for_candidate(conn, 'other-job', 'CAND_001') is None
    assert crud.get_ranking_for_candidate(conn, 'other-job', 'CAND_002')['score'] == .8


def test_unchanged_pipeline_profiles_preserve_other_job_scores(stored_run):
    conn, db, dataset = stored_run
    other_job(conn)
    dataset.write_text(''.join(json.dumps(row) + '\n' for row in database._build_fallback_candidates()))
    pipeline.run_full_pipeline('run', 'job', str(dataset), db_path=db)
    assert crud.get_pipeline_run(conn, 'run')['status'] == 'done'
    assert crud.get_job(conn, 'other-job')['status'] == 'done'
    assert crud.get_ranking_for_candidate(conn, 'other-job', 'CAND_001')['score'] == .9


def test_source_cleanup_only_removes_internal_database_snapshot(stored_run, monkeypatch):
    conn, db, uploaded = stored_run
    monkeypatch.setattr(pipeline, 'get_data_dir', lambda: db.parent)
    temporary_source = db.parent / 'snapshots' / 'run.jsonl'
    temporary_source.parent.mkdir()
    temporary_source.write_bytes(uploaded.read_bytes())
    pipeline.run_full_pipeline('run', 'job', str(temporary_source), db_path=db)
    assert crud.get_pipeline_run(conn, 'run')['status'] == 'done'
    assert not temporary_source.exists()
    assert uploaded.exists()
    assert (db.parent / 'runs' / 'run' / 'candidates.jsonl').exists()
