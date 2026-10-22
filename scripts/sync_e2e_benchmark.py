"""Profile two real SQLite replicas through the production encrypted sync engine.

Only the remote object store and credential vault are simulated. All workspaces
are disposable synthetic data under .run; Google and the user's data are unused.
Requires the repository's development environment/test support adapters.
"""
import argparse
from datetime import date
import json
from pathlib import Path
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'backend'), str(ROOT / 'backend/tests/sync')]

from sqlalchemy import event, func, select
from sqlalchemy.orm import Session
from app.database import create_database, migrate_database
from app.models import Application
from app.sync.engine import SyncEngine
from sync_support import MemorySecrets, ObjectStore


def benchmark(size):
    run_root = ROOT / '.run'
    run_root.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='sync-e2e-', dir=run_root) as folder:
        engines = [create_database(Path(folder) / label) for label in ('left', 'right')]
        try:
            for engine in engines:
                migrate_database(engine)
            remote = ObjectStore()
            replicas = [SyncEngine(engine, remote, MemorySecrets()) for engine in engines]
            counts, results = [0, 0], {'applications': size}
            for index, engine in enumerate(engines):
                def count(*_args, index=index):
                    counts[index] += 1
                event.listen(engine, 'before_cursor_execute', count)

            def measure(name, action):
                before, started = sum(counts), time.perf_counter()
                result = action()
                results[name] = {'seconds': round(time.perf_counter() - started, 4), 'sql': sum(counts) - before}
                if isinstance(result, dict) and result.get('error'):
                    raise RuntimeError('Synthetic synchronization failed: ' + result['error'])
                return result

            recovery = replicas[0].initialize('Left')['recovery_export']
            def seed():
                with Session(engines[0]) as session:
                    session.add_all([Application(company=f'Synthetic {index}', job_title='Engineer',
                        date_applied=date(2026, 10, 20), job_url=f'https://example.invalid/{index}') for index in range(size)])
                    session.commit()
            measure('seed', seed)
            measure('upload', lambda: replicas[0].run(manual=True))
            measure('pair', lambda: replicas[1].initialize('Right', recovery))
            measure('bootstrap', lambda: replicas[1].run(manual=True))
            measure('settle', lambda: replicas[1].run(manual=True))
            measure('noop', lambda: replicas[1].run(manual=True))
            def edit():
                with Session(engines[0]) as session:
                    for item in session.scalars(select(Application).limit(10)):
                        item.job_title = 'Updated'
                    session.commit()
            measure('ten_edits', edit)
            measure('incremental_upload', lambda: replicas[0].run(manual=True))
            measure('incremental_download', lambda: replicas[1].run(manual=True))
            with Session(engines[1]) as session:
                assert session.scalar(select(func.count()).select_from(Application)) == size
                assert session.scalar(select(func.count()).select_from(Application).where(Application.job_title == 'Updated')) == min(10, size)
            results['converged'] = True
            results['remote_objects'] = len(remote.files)
            results['remote_ciphertext_bytes'] = sum(len(value) for _, value in remote.files.values())
            results['live_google'] = False
            return results
        finally:
            for engine in engines:
                engine.dispose()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sizes', type=int, nargs='+', default=[100, 1000])
    parser.add_argument('--output', type=Path, default=ROOT / '.run/sync-e2e-optimized.json')
    args = parser.parse_args()
    results = []
    for size in args.sizes:
        if size < 1:
            parser.error('Sizes must be positive')
        results.append(benchmark(size))
        print(json.dumps(results[-1]), flush=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(results, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
