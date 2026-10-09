"""Run feature segments, changed-file checks, or the complete pre-push gate."""
import argparse
from pathlib import Path
import shutil
import subprocess
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
BACKEND = {'applications', 'activity', 'work', 'followups', 'interviews', 'dashboard',
           'documents', 'posting', 'agent', 'auth', 'notifications', 'migrations', 'system'}
FRONTEND = {'applications', 'work', 'followups', 'api', 'auth', 'notifications', 'appearance', 'shell'}
SEGMENTS = BACKEND | FRONTEND | {'tooling'}

# Shared persistence, application services/schemas, startup and configuration
# affect all backend features. Smaller modules list their consumers explicitly.
BACKEND_MODULES = {
    'activity': BACKEND,
    'activity_schemas': {'activity', 'agent'},
    'work': BACKEND,
    'work_schemas': BACKEND,
    'interviews': {'interviews', 'dashboard', 'activity', 'agent'},
    'interview_schemas': {'interviews', 'agent', 'activity', 'dashboard'},
    'documents': {'documents', 'agent', 'interviews', 'auth'},
    'document_schemas': {'documents', 'agent', 'interviews', 'auth'},
    'exports': {'documents', 'applications', 'dashboard'},
    'dashboard': {'dashboard', 'agent', 'followups', 'notifications'},
    'dashboard_schemas': {'dashboard', 'agent'},
    'scheduler': {'dashboard', 'posting', 'system'},
    'followup_templates': BACKEND,
    'followup_reminders': {'followups', 'notifications', 'dashboard', 'agent'},
    'integrations': {'followups', 'interviews', 'notifications'},
    'human_auth': {'auth', 'notifications'},
    'backup': {'auth', 'notifications'},
    'push': {'notifications'}, 'push_keys': {'notifications'},
    'posting_checker': {'posting', 'agent'}, 'posting_service': {'posting', 'activity', 'agent'},
    'posting_review': {'posting', 'agent'},
    'confirmation_details': {'posting', 'agent'}, 'confirmation_links': {'posting', 'agent'},
    'contract_types': {'applications', 'dashboard', 'agent', 'documents'},
    'job_sources': {'applications', 'posting', 'agent'},
    'invalidation': {'agent', 'auth', 'activity', 'work', 'followups', 'interviews', 'posting', 'applications'},
}


def git_paths(*args):
    result = subprocess.run(['git', *args], cwd=ROOT, check=True, stdout=subprocess.PIPE)
    return [path.decode('utf-8') for path in result.stdout.split(b'\0') if path]


def changed_paths(base=None):
    paths = git_paths('diff', '--name-only', '-z', 'HEAD')
    paths += git_paths('ls-files', '--others', '--exclude-standard', '-z')
    if base:
        # Separate arguments and verified commit refs prevent option injection.
        revision = subprocess.run(['git', 'rev-parse', '--verify', '--end-of-options', base + '^{commit}'],
                                  cwd=ROOT, check=True, capture_output=True, text=True).stdout.strip()
        paths += git_paths('diff', '--name-only', '-z', revision, 'HEAD')
    return sorted(set(paths))


def normalize(path):
    candidate = Path(path.replace('\\', '/'))
    if not candidate.is_absolute():
        candidate = ROOT / candidate
    return candidate.resolve().relative_to(ROOT).as_posix()


def frontend_dependencies():
    """Resolve local imports without executing code; unknown files fall back below."""
    import re
    graph = {}
    for folder in ('src', 'tests'):
        for path in (ROOT / 'frontend' / folder).rglob('*'):
            if path.suffix not in {'.ts', '.vue'}:
                continue
            source = path.read_text(encoding='utf-8')
            # Imports, re-exports, dynamic imports, raw assets and vi.mock calls.
            references = re.findall(r'''(?:from\s*|import\s*\(\s*|import\s+|vi\.mock\(\s*)["']([^"']+)["']''', source)
            deps = set()
            for reference in references:
                if not reference.startswith('.'):
                    continue
                target = path.parent / reference.split('?')[0]
                candidates = [target, Path(str(target) + '.ts'), Path(str(target) + '.vue'), target / 'index.ts']
                resolved = next((p for p in candidates if p.is_file()), None)
                if resolved and resolved.resolve().is_relative_to(ROOT):
                    deps.add(resolved.resolve().relative_to(ROOT).as_posix())
            graph[path.relative_to(ROOT).as_posix()] = deps
    return graph


def select(paths, graph=None):
    backend, frontend = set(), set()
    tooling = False
    graph = frontend_dependencies() if graph is None else graph
    for raw in paths:
        path = normalize(raw)
        parts = path.split('/')
        if path.startswith('backend/tests/'):
            if len(parts) >= 4 and parts[2] in BACKEND:
                backend.add(parts[2])
            else:
                backend.update(BACKEND)
        elif path.startswith('backend/migrations/') or path == 'alembic.ini':
            backend.update(BACKEND)
        elif path.startswith('backend/app/'):
            stem = Path(path).stem
            if stem.startswith('agent_') or stem == 'mcp_server':
                backend.update({'agent', 'posting', 'followups', 'auth'})
            else:
                backend.update(BACKEND_MODULES.get(stem, BACKEND))
        elif path.startswith('backend/'):
            backend.update(BACKEND)
        elif path.startswith('frontend/tests/'):
            if len(parts) >= 4 and parts[2] in FRONTEND:
                frontend.add(parts[2])
            else:
                frontend.update(FRONTEND)
        elif path.startswith(('frontend/src/', 'frontend/public/')):
            affected = {path}
            while True:
                new = {owner for owner, deps in graph.items() if deps & affected} - affected
                if not new:
                    break
                affected.update(new)
            matches = {p.split('/')[2] for p in affected if p.startswith('frontend/tests/')}
            # A new/uncovered/deleted file cannot silently claim adequate coverage.
            frontend.update(matches or FRONTEND)
        elif path.startswith('frontend/'):
            frontend.update(FRONTEND)
        elif path.startswith(('scripts/', 'tests/')):
            backend.update(BACKEND)
            frontend.update(FRONTEND)
            tooling = True
        elif path in {'pyproject.toml', 'requirements-dev.lock', 'Dockerfile', 'build-windows.ps1'} or path.startswith(('deploy/', '.github/')) or path.endswith(('.yaml', '.yml')):
            backend.update(BACKEND)
            frontend.update(FRONTEND)
            tooling = True
        elif Path(path).suffix != '.md' and path != '.gitignore':
            backend.update(BACKEND)
            frontend.update(FRONTEND)
            tooling = True
    return backend, frontend, tooling


def commands(backend, frontend, tooling=False, full=False):
    result = []
    if full:
        # Build first; the suite no longer needs pre-existing frontend/dist.
        result.append((ROOT / 'frontend', ['pnpm', 'build']))
        result.append((ROOT, [sys.executable, '-m', 'pip', 'check']))
    if backend or tooling:
        targets = [f'backend/tests/{name}' for name in sorted(backend)]
        if tooling:
            targets.append('tests')
        # A fresh, ignored directory avoids inaccessible user temp folders and
        # never asks pytest to clear a previous run's workspace.
        temp = ROOT / '.run' / ('tests-' + uuid4().hex)
        result.append((ROOT, [sys.executable, '-m', 'pytest', '-q', '-p', 'no:cacheprovider', '--basetemp', str(temp), *targets]))
    if frontend:
        result.append((ROOT / 'frontend', ['pnpm', 'test', *[f'tests/{name}' for name in sorted(frontend)]]))
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--full', action='store_true', help='build, dependency check, and every test')
    mode.add_argument('--segment', nargs='+', choices=sorted(SEGMENTS))
    mode.add_argument('--changed', action='store_true', help='staged, unstaged, deleted and untracked files')
    mode.add_argument('--files', nargs='+', help='repo-relative or absolute file paths')
    mode.add_argument('--list', action='store_true', help='show available segments')
    parser.add_argument('--base', help='include committed differences from this ref with --changed')
    parser.add_argument('--dry-run', action='store_true', help='show commands without running them')
    args = parser.parse_args(argv)
    if args.base and not args.changed:
        parser.error('--base requires --changed')
    if args.list:
        for name in sorted(SEGMENTS):
            print(f"{name:15} {'backend ' if name in BACKEND else ''}{'frontend' if name in FRONTEND else ''}{'runner checks' if name == 'tooling' else ''}")
        return 0
    if args.full:
        backend, frontend, tooling = BACKEND, FRONTEND, True
    elif args.segment:
        backend = BACKEND & set(args.segment)
        frontend = FRONTEND & set(args.segment)
        tooling = 'tooling' in args.segment
    else:
        try:
            backend, frontend, tooling = select(args.files or changed_paths(args.base))
        except (ValueError, subprocess.CalledProcessError) as exc:
            parser.error(str(exc))
    print('Backend: ' + (', '.join(sorted(backend)) or 'none'))
    print('Frontend: ' + (', '.join(sorted(frontend)) or 'none'))
    for cwd, command in commands(backend, frontend, tooling, args.full):
        print(f'[{cwd.relative_to(ROOT) if cwd != ROOT else "."}] {subprocess.list2cmdline(command)}', flush=True)
        if args.dry_run:
            continue
        command[0] = shutil.which(command[0]) or command[0]
        try:
            result = subprocess.run(command, cwd=cwd)
        except OSError as exc:
            print(f'Cannot start test command: {exc}', file=sys.stderr)
            return 1
        if result.returncode:
            return result.returncode
    if not backend and not frontend and not tooling:
        print('No executable changes require tests (documentation-only or a clean checkout).')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
