"""Local database initialization, demo ranking and safe SQLite backups."""
from __future__ import annotations

import argparse
import os
from contextlib import closing
from pathlib import Path
import sqlite3
import uuid


def prepare_demo():
    from backend import crud, database
    from backend.pipeline import run_full_pipeline
    database.init_db()
    with closing(database.get_connection()) as conn:
        ids = {r[0] for r in conn.execute('SELECT candidate_id FROM candidates')}
        if os.getenv('DEMO_MODE', 'true').lower() != 'true' or ids != {'CAND_001', 'CAND_002'}:
            print('Database initialized; existing candidate data preserved.')
            return
        if conn.execute('SELECT 1 FROM jobs LIMIT 1').fetchone():
            print('Database and jobs already exist; preserved without reranking.')
            return
        if not database.get_candidates_path().is_file():
            print('Database initialized; configure a candidate dataset to run ranking.')
            return
        job = 'demo-ai-engineer'
        crud.create_job(conn, job, 'Senior AI Engineer — demo',
                        'Senior AI Engineer building Python machine learning ranking, retrieval, '
                        'recommendation and vector search systems with production experience.')
        run_id = str(uuid.uuid4())
        crud.create_pipeline_run(conn, run_id, job)
        crud.update_job_status(conn, job, 'running')
    run_full_pipeline(run_id, job, str(database.get_candidates_path()))
    with closing(database.get_connection()) as conn:
        result = crud.get_pipeline_run(conn, run_id)
        if result['status'] != 'done':
            raise RuntimeError(f"Demo ranking failed: {result['error_message']}")
    print('Database initialized and demo rankings saved. Start the app to inspect them.')


def backup(destination: Path):
    from backend.database import get_db_path
    source = get_db_path()
    if not source.is_file():
        raise ValueError('Database does not exist; run init or prepare-demo first.')
    destination = destination.expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Reserve a fresh file so existing user backups are never overwritten.
    with destination.open('xb'):
        pass
    try:
        with closing(sqlite3.connect(source)) as src, closing(sqlite3.connect(destination)) as dst:
            src.backup(dst)
            if dst.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise RuntimeError('Backup integrity check failed.')
    except BaseException:
        destination.unlink(missing_ok=True)
        raise
    print(f'Consistent database backup written to {destination}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('init')
    sub.add_parser('prepare-demo')
    task = sub.add_parser('backup')
    task.add_argument('destination', type=Path)
    args = parser.parse_args()
    if args.command == 'backup':
        backup(args.destination)
    elif args.command == 'prepare-demo':
        prepare_demo()
    else:
        from backend.database import init_db
        init_db()
        print('Database initialized.')


if __name__ == '__main__':
    main()
