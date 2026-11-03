import copy
import json

import pytest

from backend import database
from tests.test_application import client, create, run


def body(record=None):
    row = copy.deepcopy(record or database._build_fallback_candidates()[0])
    row['candidate_id'] = 'UPLOADED_001'
    return json.dumps(row) + '\n'


def upload(api, data):
    return api.post('/api/datasets?filename=team.jsonl', content=data,
                    headers={'Content-Type': 'application/octet-stream'})


def test_import_is_persistent_and_default_pipeline_includes_import(client):
    api, _ = client
    assert api.get('/api/system').json()['total_candidates'] == 2
    response = upload(api, body())
    assert response.status_code == 201, response.text
    assert response.json()['total_candidates'] == 1
    assert api.get('/api/candidates').json()['total'] == 3
    assert api.get('/api/candidates/UPLOADED_001/features').status_code == 200
    create(api)
    assert run(api, top_k=10)['total_candidates'] == 3
    assert api.get('/api/jobs/test-job/rankings').json()['total'] == 3


@pytest.mark.parametrize('data', ['[]\n', 'null\n', 'broken\n', '{}\n', '', body() + body(), '{"candidate_id":"../invalid"}\n'])
def test_invalid_upload_has_no_partial_writes(client, data):
    api, directory = client
    response = upload(api, data)
    assert response.status_code == 422, response.text
    assert api.get('/api/candidates').json()['total'] == 2
    assert list((directory / 'uploads').glob('*.jsonl')) == []
    assert list((directory / 'uploads').glob('*.part')) == []


def test_reimport_updates_relations_and_invalidates_scores(client):
    api, _ = client
    create(api)
    run(api)
    record = database._build_fallback_candidates()[0]
    record['profile']['headline'] = 'Updated profile'
    response = upload(api, json.dumps(record))
    assert response.status_code == 201, response.text
    assert api.get('/api/candidates/CAND_001').json()['headline'] == 'Updated profile'
    assert api.get('/api/jobs/test-job').json()['status'] == 'pending'
    assert api.get('/api/jobs/test-job/rankings').json()['total'] == 1


def test_null_lists_are_normalized_and_invalid_types_rejected(client):
    api, _ = client
    row = {'candidate_id': 'EMPTY_LISTS', 'profile': {'years_of_experience': None},
           'skills': None, 'career_history': None, 'education': None}
    response = upload(api, json.dumps(row))
    assert response.status_code == 201, response.text
    assert api.get('/api/candidates/EMPTY_LISTS').json()['skills'] == []
    row['skills'] = 'not-a-list'
    assert upload(api, json.dumps(row)).status_code == 422


def test_auth_protects_import_and_limits_request(client, monkeypatch):
    api, _ = client
    monkeypatch.setenv('APP_PASSWORD', 'test-only')
    assert upload(api, body()).status_code == 401
    monkeypatch.delenv('APP_PASSWORD')
    assert api.post('/api/datasets', content=b'x', headers={'Content-Length': str(51*1024*1024)}).status_code == 413


def test_database_remains_rankable_without_original_file(client):
    api, directory = client
    (directory / 'candidates.jsonl').unlink()
    create(api)
    assert api.get('/api/system').json()['dataset_available'] is True
    assert run(api)['total_candidates'] == 2
