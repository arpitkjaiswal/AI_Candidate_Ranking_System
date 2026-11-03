"""Prepare a mounted data directory, then run the server without root privileges."""
from __future__ import annotations

import os
from pathlib import Path
import pwd
import sys


def main():
    data = Path(os.getenv('DATA_DIR', '/var/data')).expanduser().resolve()
    # Never repair ownership on system directories after a configuration mistake.
    if data == Path('/') or data in (Path('/app'), Path('/var'), Path('/usr'), Path('/etc'), Path('/home'), Path('/tmp')):
        raise SystemExit('DATA_DIR must be a dedicated application data directory.')
    data.mkdir(parents=True, exist_ok=True)
    if os.getuid() == 0:
        account = pwd.getpwnam('app')
        # Mounted disks hide the image directory's ownership. Repair only root-owned
        # data; never follow symlinks out of the dedicated directory.
        targets = [data]
        for root, directories, files in os.walk(data, followlinks=False):
            targets.extend(Path(root) / name for name in directories + files)
        for path in targets:
            if not path.is_symlink() and path.stat().st_uid == 0:
                os.chown(path, account.pw_uid, account.pw_gid)
        os.setgroups([])
        os.setgid(account.pw_gid)
        os.setuid(account.pw_uid)
    if not os.access(data, os.W_OK | os.X_OK):
        raise SystemExit('DATA_DIR is not writable. Set its ownership to UID 10001 or use a writable mounted directory.')
    os.umask(0o077)
    command = sys.argv[1:]
    if not command:
        command = [sys.executable, '-m', 'uvicorn', 'backend.main:app', '--host', '0.0.0.0',
                   '--port', os.getenv('PORT', '8000'), '--workers', '1']
    os.execvp(command[0], command)


if __name__ == '__main__':
    main()
