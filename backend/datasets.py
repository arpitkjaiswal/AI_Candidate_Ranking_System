"""Validate and import local JSONL datasets without partial database writes."""
from __future__ import annotations

import json
import math
import re
from pathlib import Path

from backend.database import _normalize_candidate
from backend.schemas import CandidateDetail
from src.data_cleaner import clean_candidate_dict
from src.feature_extractor import extract_all_features

MAX_UPLOAD_BYTES = 50 * 1024 * 1024
MAX_LINE_BYTES = 2 * 1024 * 1024


def _finite(value):
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError('Non-finite numbers are not supported.')
    if isinstance(value, dict):
        for child in value.values():
            _finite(child)
    elif isinstance(value, list):
        for child in value:
            _finite(child)


def validate_record(record: dict) -> dict:
    if not isinstance(record, dict):
        raise ValueError('Each line must be a candidate object.')
    cid = record.get('candidate_id')
    if not isinstance(cid, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,100}', cid):
        raise ValueError('candidate_id must contain 1–100 letters, digits, underscores or hyphens.')
    _finite(record)
    for key in ('profile', 'redrob_signals'):
        if record.get(key) is None:
            record[key] = {}
        if not isinstance(record[key], dict):
            raise ValueError(f'{key} must be an object.')
    for key in ('skills', 'education', 'career_history', 'certifications', 'languages'):
        if record.get(key) is None:
            record[key] = []
        if not isinstance(record[key], list) or any(not isinstance(item, dict) for item in record[key]):
            raise ValueError(f'{key} must be a list of objects.')
    record['redrob_signals'] = {key: value for key, value in record['redrob_signals'].items() if value is not None}
    profile = record['profile']
    for key in ('headline', 'summary', 'location', 'country', 'current_title', 'current_company', 'current_company_size', 'current_industry'):
        if profile.get(key) is None:
            profile[key] = ''
        if not isinstance(profile[key], str):
            raise ValueError(f'profile.{key} must be text.')
    for key in ('years_of_experience',):
        value = profile.get(key)
        profile[key] = 0 if value is None else float(value)
        if not math.isfinite(profile[key]) or profile[key] < 0:
            raise ValueError(f'profile.{key} must be a finite nonnegative number.')
    for row in record['career_history']:
        for key in ('title', 'description', 'company', 'industry', 'company_size'):
            if row.get(key) is None:
                row[key] = ''
            if not isinstance(row[key], str):
                raise ValueError(f'career_history.{key} must be text.')
    for row in record['skills']:
        if not isinstance(row.get('name'), str) or not row['name'].strip():
            raise ValueError('Each skill needs a nonempty name.')
    # Exercise the same cleaning, features and response contract used by the app.
    cleaned = clean_candidate_dict(record)
    extract_all_features(cleaned)
    normalized = _normalize_candidate(cleaned)
    CandidateDetail.model_validate({**normalized,
        'skills': [dict(id=0, skill_name=s['name'], **{k:v for k,v in s.items() if k != 'name'}) for s in cleaned['skills']],
        'education': [dict(e, id=0) for e in cleaned['education']],
        'career': [dict(e, id=0) for e in cleaned['career_history']]})
    return cleaned


def records_from_dataset(path: Path):
    """Stream strict UTF-8 JSONL (optionally gzip) and normalize every record.

    All ingestion paths use this reader so startup, uploads and runs enforce the
    same duplicate, encoding, size and response-contract validation.
    """
    import gzip
    path = Path(path)
    seen = set()
    source = gzip.open(path, 'rb') if path.suffix == '.gz' else path.open('rb')
    with source:
        line_no = 0
        while True:
            line = source.readline(MAX_LINE_BYTES + 1)
            if not line:
                break
            line_no += 1
            if len(line) > MAX_LINE_BYTES:
                raise ValueError(f'Line {line_no} exceeds the 2 MiB record limit.')
            if not line.strip():
                continue
            try:
                text = line.decode('utf-8-sig' if line_no == 1 else 'utf-8')
                record = validate_record(json.loads(text))
                if record['candidate_id'] in seen:
                    raise ValueError('Duplicate candidate_id.')
                seen.add(record['candidate_id'])
            except (ValueError, TypeError, AttributeError, KeyError, OverflowError, RecursionError) as exc:
                raise ValueError(f'Invalid candidate at line {line_no}: {exc}') from exc
            yield record
    if not seen:
        raise ValueError('Dataset contains no valid candidates.')


def validate_dataset(path: Path) -> int:
    """Validate the complete dataset without retaining profiles in memory."""
    return sum(1 for _ in records_from_dataset(path))
