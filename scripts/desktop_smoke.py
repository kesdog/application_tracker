"""Black-box frozen process checks with synthetic data, restart and collision."""
import argparse
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request


def request(address, path, payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(address + path, data=data, headers={'Content-Type': 'application/json', 'Origin': address})
    with urllib.request.urlopen(req, timeout=3) as response:
        body = response.read()
        return json.loads(body) if response.headers.get_content_type() == 'application/json' else body


def exercise(executable, workspace, port, version):
    address = f'http://127.0.0.1:{port}'
    # Do not inherit workspace credentials/provider configuration from the caller.
    env = {k: v for k, v in os.environ.items() if not k.startswith(('APP_', 'GOOGLE_', 'MCP_', 'VITE_'))}
    env.update(APP_DATA_DIR=str(workspace), APP_PORT=str(port), APP_DESKTOP_NO_BROWSER='1', APP_DESKTOP_HEADLESS='1')
    marker = workspace / '.release-smoke'
    if workspace.exists() and any(workspace.iterdir()) and not marker.is_file():
        raise ValueError('Refusing to smoke-test an existing user workspace')
    workspace.mkdir(parents=True, exist_ok=True)
    marker.write_text('Synthetic release smoke only\n')
    for restart in range(2):
        with (workspace / f'process-{restart}.log').open('wb') as log:
            process = subprocess.Popen([str(executable), '--headless'], env=env, stdout=log, stderr=log)
            try:
                for _ in range(180):
                    if process.poll() is not None:
                        raise RuntimeError(f'Frozen process exited: {process.returncode}')
                    try:
                        health = request(address, '/api/health')
                        break
                    except (OSError, urllib.error.URLError):
                        time.sleep(0.5)
                else:
                    raise RuntimeError('Frozen process startup timed out')
                assert health['version'] == version
                assert b'<html' in request(address, '/').lower()
                records = request(address, '/api/applications')
                if restart == 0:
                    request(address, '/api/recipients/pause', {})
                    if records:
                        assert len(records) == 1 and records[0]['company'] == 'Synthetic frozen smoke'
                        record_id = records[0]['id']
                    else:
                        created = request(address, '/api/applications', {'company': 'Synthetic frozen smoke',
                            'job_title': 'Engineer', 'date_applied': '2026-11-01', 'email_reference': 'Synthetic release smoke only'})
                        record_id = created['id']
                    # A competing process must fail without altering the active DB.
                    collision_env = {**env, 'APP_DESKTOP_SMOKE': '1'}
                    collision = subprocess.run([str(executable)], env=collision_env, timeout=60, stdout=log, stderr=log)
                    assert collision.returncode != 0
                else:
                    assert len(records) == 1 and records[0]['id'] == record_id
            finally:
                # Windows has no portable console SIGTERM; the smoke exit path below
                # separately proves graceful shutdown. Restart also covers crash recovery.
                process.terminate()
                try:
                    process.wait(timeout=20)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
    env['APP_DESKTOP_SMOKE'] = '1'
    subprocess.run([str(executable)], env=env, check=True, timeout=60)
    with socket.socket() as released:
        if sys.platform != 'win32':
            released.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        released.bind(('127.0.0.1', port))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('executable', type=Path)
    parser.add_argument('--version', required=True)
    parser.add_argument('--workspace', type=Path, help='New or previously marked synthetic workspace for installer upgrade checks')
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='tracker-frozen-') as directory:
        with socket.socket() as reservation:
            reservation.bind(('127.0.0.1', 0))
            port = reservation.getsockname()[1]
        workspace = args.workspace.resolve() if args.workspace else Path(directory) / 'workspace'
        try:
            exercise(args.executable.resolve(), workspace, port, args.version)
        except BaseException:
            if (workspace / '.release-smoke').is_file():
                for name in ['process-0.log', 'process-1.log', 'desktop.log', 'startup-error.log']:
                    path = workspace / name
                    if path.is_file():
                        print(f'{name}:\n{path.read_text(encoding="utf-8", errors="replace")[-12000:]}', file=sys.stderr)
            raise
    print('Frozen UI, API, persistence, collision, restart and shutdown checks passed')


if __name__ == '__main__':
    main()
