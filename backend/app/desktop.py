"""Shared loopback server lifecycle; platform UI loads only after startup."""
from contextlib import contextmanager
import logging
import os
import socket
import sys
import threading
import time
import urllib.request

import uvicorn

from app.config import Settings
from app.main import create_app


@contextmanager
def workspace_lock(directory):
    """A second desktop process must never start another workspace scheduler."""
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / '.desktop.lock').open('a+b') as handle:
        handle.seek(0, 2)
        if handle.tell() == 0:
            handle.write(b'0')
            handle.flush()
        handle.seek(0)
        try:
            if sys.platform == 'win32':
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise RuntimeError('Application Tracker is already using this data directory') from exc
        try:
            yield
        finally:
            handle.seek(0)
            if sys.platform == 'win32':
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle, fcntl.LOCK_UN)
            # Do not unlink: another process may already hold the same inode.


class LoopbackHost:
    def __init__(self, settings):
        self.settings = settings
        self.address = f'http://127.0.0.1:{settings.app_port}'
        self.server = None
        self.thread = None
        self.listener = None

    def __enter__(self):
        if self.settings.app_host not in {'127.0.0.1', '::1', 'localhost'} or self.settings.app_mode != 'local':
            raise RuntimeError('The desktop host requires local mode and a loopback listener')
        if not (self.settings.app_static_dir / 'index.html').is_file():
            raise RuntimeError('Built frontend is missing. Run the frontend build first.')
        self.listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            if sys.platform != 'win32':
                # POSIX permits a clean restart while closed connections expire;
                # this does not permit sharing an active listening socket.
                self.listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            # Reserve the port before running migrations or starting schedulers.
            self.listener.bind(('127.0.0.1', self.settings.app_port))
            self.listener.listen(128)
            self.server = uvicorn.Server(uvicorn.Config(create_app(self.settings), host='127.0.0.1',
                port=self.settings.app_port, log_level=self.settings.log_level, log_config=None))
            self.thread = threading.Thread(target=self.server.run, kwargs={'sockets': [self.listener]}, name='tracker-api', daemon=True)
            self.thread.start()
            for _ in range(300):
                if self.server.started or not self.thread.is_alive():
                    break
                time.sleep(0.1)
            if not self.server.started:
                raise RuntimeError(f'The local server could not start on {self.address}')
            return self
        except BaseException:
            self.__exit__(None, None, None)
            raise

    def __exit__(self, *_):
        if self.server:
            self.server.should_exit = True
        if self.thread:
            self.thread.join(timeout=15)
        if self.listener:
            self.listener.close()
        if self.thread and self.thread.is_alive():
            raise RuntimeError('Application Tracker failed to shut down')


def run() -> None:
    from app.desktop_platform import show_ui

    # Frozen builds must not discover a developer's dotenv beside their bundle.
    settings = Settings(_env_file=None) if getattr(sys, 'frozen', False) else Settings()
    with workspace_lock(settings.app_data_dir):
        logging.basicConfig(filename=settings.app_data_dir / 'desktop.log', level=settings.log_level.upper(), force=True)
        with LoopbackHost(settings) as host:
            if os.environ.get('APP_DESKTOP_SMOKE') == '1':
                with urllib.request.urlopen(host.address + '/api/health', timeout=10) as response:
                    if response.status != 200:
                        raise RuntimeError('Packaged API health check failed')
            else:
                show_ui(host.address, host.thread)


if __name__ == '__main__':
    run()
