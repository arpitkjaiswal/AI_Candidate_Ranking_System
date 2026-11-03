"""Failure paths must never publish a mixture of old rankings and new profiles."""
import copy
import json
import sqlite3
from pathlib import Path

import pytest

from backend import crud, database, pipeline


@pytest.fixture
def stored_run(tmp_path, monkeypatch):
    db = tmp_path / 'ranking.db'
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys=ON')
    conn.executescript(database.SCHEMA_PATH.read_text())
    records = database._build_fallback_candidates()
    database._seed_database_from_records(conn, records)
    crud.create_job(conn, 'job', 'ML Engineer', 'Python production machine learning retrieval')
    crud.upsert_rankings_batch(conn, 'job', [
        {'candidate_id': 'CAND_001', 'rank': 1, 'score': .9, 'reasoning': 'Previous successful result'}
    ])
    crud.create_pipeline_run(conn, 'run', 'job')
    crud.update_job_status(conn, 'job', 'running')
    changed = copy.deepcopy(records)
    changed[0]['profile']['current_company'] = 'Updated company'
    dataset = tmp_path / 'uploaded-candidates.jsonl'
    dataset.write_text(''.join(json.dumps(r) + '\n' for r in changed))
    monkeypatch.setattr(pipeline, 'PRECOMPUTED_DIR', tmp_path)
    yield conn, db, dataset
    conn.close()


def snapshot(conn):
    return {
        table: [tuple(row) for row in conn.execute(f'SELECT * FROM {table} ORDER BY 1')]
        for table in ['candidates', 'candidate_skills', 'candidate_career', 'candidate_education', 'rankings']
    }


def test_preparation_failure_preserves_profiles_and_previous_rankings(stored_run, monkeypatch):
    conn, db, dataset = stored_run
    before = snapshot(conn)
    def fail(**kwargs):
        raise ValueError('Invalid dataset: duplicate candidate IDs')
    monkeypatch.setattr('src.data_preparation.prepare_all_data', fail)
    pipeline.run_full_pipeline('run', 'job', str(dataset), db_path=db)
    assert snapshot(conn) == before
    assert crud.get_pipeline_run(conn, 'run')['status'] == 'failed'
    assert crud.get_job(conn, 'job')['status'] == 'failed'


def test_late_publication_failure_rolls_back_profiles_rankings_and_status(stored_run, monkeypatch):
    conn, db, dataset = stored_run
    before = snapshot(conn)
    finish = crud.finish_pipeline_run
    def fail_success(*args, **kwargs):
        if kwargs.get('status') == 'done':
            raise sqlite3.IntegrityError('Simulated final status failure')
        return finish(*args, **kwargs)
    monkeypatch.setattr(crud, 'finish_pipeline_run', fail_success)
    pipeline.run_full_pipeline('run', 'job', str(dataset), db_path=db)
    assert snapshot(conn) == before
    run = crud.get_pipeline_run(conn, 'run')
    assert run['status'] == 'failed'
    assert 'Simulated final status failure' in run['error_message']


def test_success_publishes_profiles_rankings_and_done_status(stored_run):
    conn, db, dataset = stored_run
    pipeline.run_full_pipeline('run', 'job', str(dataset), db_path=db)
    assert crud.get_candidate(conn, 'CAND_001')['current_company'] == 'Updated company'
    assert crud.get_pipeline_run(conn, 'run')['status'] == 'done'
    assert crud.get_pipeline_run(conn, 'run')['total_candidates'] == 2
    assert crud.get_job(conn, 'job')['status'] == 'done'
    assert conn.execute('SELECT COUNT(*) FROM rankings WHERE job_id=?', ('job',)).fetchone()[0] == 2


def test_no_commit_seed_rolls_back_even_after_batch_boundary(stored_run):
    conn, _, _ = stored_run
    before = snapshot(conn)
    template = database._build_fallback_candidates()[0]
    def records():
        for i in range(1002):
            record = copy.deepcopy(template)
            record['candidate_id'] = f'BATCH_{i}'
            yield record
    conn.execute('BEGIN IMMEDIATE')
    database._seed_database_from_records(conn, records(), commit=False)
    conn.rollback()
    assert snapshot(conn) == before


def test_explicit_transformer_request_cannot_silently_use_tfidf(stored_run, monkeypatch):
    import builtins
    conn, db, dataset = stored_run
    before = snapshot(conn)
    original_import = builtins.__import__
    def unavailable(name, *args, **kwargs):
        if name == 'sentence_transformers':
            raise ImportError('Optional package not installed')
        return original_import(name, *args, **kwargs)
    monkeypatch.setattr(builtins, '__import__', unavailable)
    pipeline.run_full_pipeline('run', 'job', str(dataset), embedding_mode='sentence_transformers', db_path=db)
    assert snapshot(conn) == before
    result = crud.get_pipeline_run(conn, 'run')
    assert result['status'] == 'failed'
    assert 'Use TF-IDF' in result['error_message']


def test_startup_rejects_explicit_missing_dataset_instead_of_demo(tmp_path, monkeypatch):
    monkeypatch.setenv('CANDIDATES_PATH', str(tmp_path / 'missing.jsonl'))
    monkeypatch.delenv('CANDIDATES_URL', raising=False)
    monkeypatch.setenv('DEMO_MODE', 'true')
    db = tmp_path / 'fresh.db'
    with pytest.raises(RuntimeError, match='Configured candidate dataset'):
        database.init_db(db)
    with sqlite3.connect(db) as conn:
        assert conn.execute('SELECT COUNT(*) FROM candidates').fetchone()[0] == 0


def test_database_defaults_resolve_current_config_and_null_metrics(tmp_path, monkeypatch):
    db = tmp_path / 'configured.db'
    monkeypatch.setattr(database, 'DB_PATH', db)
    monkeypatch.setattr(database, 'DATA_DIR', tmp_path)
    monkeypatch.delenv('CANDIDATES_PATH', raising=False)
    monkeypatch.delenv('CANDIDATES_URL', raising=False)
    monkeypatch.setenv('DEMO_MODE', 'true')
    database.init_db()
    with database.get_connection() as conn:
        assert conn.execute('SELECT COUNT(*) FROM candidates').fetchone()[0] == 2
        assert Path(conn.execute('PRAGMA database_list').fetchone()['file']) == db
    normalized = database._normalize_candidate({
        'candidate_id': 'nullable', 'profile': {'years_of_experience': None},
        'redrob_signals': {'profile_completeness_score': None},
    })
    assert normalized['years_of_experience'] == 0
    assert normalized['profile_completeness_score'] == 0


@pytest.mark.parametrize('contents', ['not json\n', '{"candidate_id":"duplicate"}\n{"candidate_id":"duplicate"}\n'])
def test_invalid_source_does_not_change_existing_database(stored_run, contents):
    conn, db, dataset = stored_run
    before = snapshot(conn)
    dataset.write_text(contents)
    pipeline.run_full_pipeline('run', 'job', str(dataset), db_path=db)
    assert snapshot(conn) == before
    assert crud.get_pipeline_run(conn, 'run')['status'] == 'failed'


def test_gzipped_dataset_and_nullable_collections_are_supported(stored_run):
    import gzip
    conn, db, dataset = stored_run
    rows = database._build_fallback_candidates()
    rows[0]['certifications'] = None
    rows[0]['languages'] = None
    rows[0]['profile']['years_of_experience'] = None
    rows[0]['redrob_signals']['profile_completeness_score'] = None
    compressed = dataset.with_suffix('.jsonl.gz')
    with gzip.open(compressed, 'wt') as target:
        target.write(''.join(json.dumps(r) + '\n' for r in rows))
    pipeline.run_full_pipeline('run', 'job', str(compressed), db_path=db)
    assert crud.get_pipeline_run(conn, 'run')['status'] == 'done'
    assert crud.get_candidate(conn, 'CAND_001')['years_of_experience'] == 0
