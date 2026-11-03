import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys


def manage(directory, *args):
    return subprocess.run([sys.executable, '-m', 'backend.manage', *args],
                          env={**os.environ, 'DATA_DIR':str(directory), 'DEMO_MODE':'true'},
                          capture_output=True, text=True, timeout=30)


def test_demo_setup_is_idempotent_and_backup_preserves_rankings(tmp_path):
    for _ in range(2):
        result = manage(tmp_path, 'prepare-demo')
        assert result.returncode == 0, result.stdout + result.stderr
    with sqlite3.connect(tmp_path / 'redrob_candidates.db') as conn:
        assert conn.execute('SELECT count(*) FROM candidates').fetchone()[0] == 2
        assert conn.execute('SELECT count(*) FROM jobs').fetchone()[0] == 1
        assert conn.execute('SELECT count(*) FROM rankings').fetchone()[0] == 2
        assert conn.execute('SELECT status FROM pipeline_runs').fetchone()[0] == 'done'
    destination = tmp_path / 'backup.sqlite'
    assert manage(tmp_path, 'backup', str(destination)).returncode == 0
    with sqlite3.connect(destination) as conn:
        assert conn.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        assert conn.execute('SELECT count(*) FROM rankings').fetchone()[0] == 2
    original = destination.read_bytes()
    assert manage(tmp_path, 'backup', str(destination)).returncode != 0
    assert destination.read_bytes() == original
