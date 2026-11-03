"""Verify redrob-ranking:release using a disposable volume and private test credentials.

Build the image and install frontend test dependencies/Chromium before running.
Uses the local Docker socket and host loopback port 8020.
"""
import base64
import json
import os
from pathlib import Path
import secrets
import subprocess
import time
import urllib.error
import urllib.request

repo = Path(__file__).resolve().parents[1]
command_env = {k: v for k, v in os.environ.items() if k not in ['DOCKER_HOST','DOCKER_CONTEXT','DOCKER_TLS','DOCKER_TLS_VERIFY','DOCKER_CERT_PATH']}
docker = ['docker', '--host=unix:///var/run/docker.sock']
password = secrets.token_urlsafe(30)
command_env['APP_PASSWORD'] = password
name = 'redrob-release-' + secrets.token_hex(4)
volume = name + '-data'

def call(*args):
    result = subprocess.run([*docker, *args], env=command_env, capture_output=True, text=True, check=True)
    return result.stdout.strip()

call('volume','create',volume)
# Simulate an attached disk owned by root rather than the image user.
call('run','--rm','--entrypoint','python','-v',volume+':/var/data','redrob-ranking:release','-c',
     "import os; os.chown('/var/data',0,0); open('/var/data/storage-probe','w').write('probe'); os.chmod('/var/data/storage-probe',0o600)")
call('run','-d','--name',name,'-p','127.0.0.1:8020:8000','-e','APP_PASSWORD','-v',volume+':/var/data','redrob-ranking:release')
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
base = 'http://127.0.0.1:8020'
auth = 'Basic ' + base64.b64encode(('admin:'+password).encode()).decode()

def request(path, data=None, authenticated=True):
    headers = {'Authorization':auth} if authenticated else {}
    if data is not None:
        headers['Content-Type']='application/json'
    req = urllib.request.Request(base+path, data=None if data is None else json.dumps(data).encode(), headers=headers)
    with opener.open(req,timeout=8) as response:
        return json.load(response)

def ready():
    for _ in range(100):
        try:
            request('/health', authenticated=False)
            return
        except (OSError,ValueError):
            time.sleep(.2)
    raise RuntimeError('Container failed readiness')

try:
    ready()
    try:
        request('/api/candidates', authenticated=False)
        raise AssertionError('Unprotected candidates API')
    except urllib.error.HTTPError as exc:
        assert exc.code==401
    assert request('/api/candidates')['total']==2
    # Verify PID1 actually runs as the app user, not the root entrypoint.
    uid=call('exec', name,'python','-c',"print(next(l for l in open('/proc/1/status') if l.startswith('Uid:')).split()[1])")
    assert uid=='10001',uid
    request('/api/jobs', {'job_id':'release-smoke','title':'ML engineer','description':'Python machine learning ranking retrieval'})
    run=request('/api/pipeline/run',{'job_id':'release-smoke'})
    for _ in range(150):
        result=request('/api/pipeline/runs/'+run['run_id'])
        if result['status']!='running':
            break
        time.sleep(.2)
    assert result['status']=='done',result
    before=request('/api/jobs/release-smoke/rankings')
    assert before['total']==2
    call('exec',name,'python','-m','backend.manage','backup','/var/data/backups/release.sqlite')
    integrity=call('exec',name,'python','-c',"import sqlite3; c=sqlite3.connect('/var/data/backups/release.sqlite'); print(c.execute('PRAGMA integrity_check').fetchone()[0]); print(c.execute('SELECT count(*) FROM rankings').fetchone()[0])")
    assert integrity.splitlines()==['ok','2'],integrity
    call('restart',name)
    ready()
    assert request('/api/jobs/release-smoke/rankings')==before
    print('PASS: root-owned volume initialization, UID10001 server, authentication, ranking, consistent backup, and restart persistence.')
    browser_env={**command_env,'TEST_BASE_URL':base,'TEST_USERNAME':'admin','TEST_PASSWORD':password}
    subprocess.run(['npm','run','test:e2e'],cwd=repo/'frontend',env=browser_env,check=True)
    print('PASS: authenticated browser suite against production image.')
finally:
    call('rm','-f',name)
    call('volume','rm',volume)
