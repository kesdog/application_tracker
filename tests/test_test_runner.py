"""Regressions for selective testing: never silently skip shared/unknown changes."""
import importlib.util
from pathlib import Path
from unittest.mock import patch

import pytest

spec = importlib.util.spec_from_file_location('test_runner', Path(__file__).resolve().parents[1] / 'scripts/test.py')
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


def test_feature_selection_includes_backend_consumers():
    assert runner.select(['backend/app/backup.py'], graph={})[0] == {'auth', 'notifications', 'sync', 'applications', 'documents'}
    assert runner.select(['backend/app/application_merge.py'], graph={})[0] == {'applications', 'sync', 'followups', 'activity', 'documents'}
    assert runner.select(['backend/app/secret_store.py'], graph={})[0] == {'auth', 'agent', 'sync'}
    assert runner.select(['backend/app/application_import.py'], graph={})[0] == {'applications', 'documents', 'migrations', 'auth'}
    assert runner.select(['backend/app/mail_reviews.py'], graph={})[0] == {'applications', 'followups', 'auth'}
    assert runner.select(['backend/app/workspace_routes.py'], graph={})[0] == {'applications', 'documents', 'auth', 'sync', 'migrations'}
    vendor = runner.VENDOR['toolbox']
    assert runner.select([vendor + '/test_contacts.py'], graph={}) == ({'toolbox'}, set(), False)
    assert runner.select([vendor.replace('/tests', '/src/webtoolbox/contacts.py')], graph={})[0] == {'toolbox', 'followups', 'agent', 'system'}
    assert runner.select(['backend/app/application_sync.py'], graph={})[0] == {'applications', 'sync', 'auth', 'system'}
    assert runner.select(['backend/app/mailbox_import.py'], graph={})[0] == {'applications', 'sync', 'activity', 'migrations'}
    back, front, tooling = runner.select(['backend/app/push.py', 'backend/app/exports.py'], graph={})
    assert back == {'notifications', 'documents', 'applications', 'dashboard'}
    assert front == set() and not tooling
    assert runner.select(['backend/app/recipient_discovery.py'], graph={})[0] == {'followups', 'agent', 'activity', 'auth', 'migrations', 'system'}
    assert runner.select(['backend/app/recipient_research.py'], graph={})[0] == {'followups', 'system'}
    assert runner.select(['backend/app/recipient_reports.py'], graph={})[0] == {'followups', 'agent', 'auth', 'migrations', 'system'}
    assert runner.select(['backend/app/followup_ai.py'], graph={})[0] == {'followups', 'agent', 'activity', 'auth'}
    assert runner.select(['backend/app/google_connection.py'], graph={})[0] == {'agent', 'followups', 'auth', 'migrations', 'system', 'sync', 'applications'}
    assert runner.select(['backend/app/confirmation_details.py'], graph={})[0] == {'posting', 'agent', 'applications'}
    assert runner.select(['backend/app/authorized_api.py'], graph={})[0] == {'auth', 'agent', 'sync'}
    assert runner.select(['backend/app/sync/merge.py'], graph={})[0] == {'sync'}
    assert runner.select(['backend/app/sync/journal.py'], graph={})[0] == runner.BACKEND
    assert runner.select(['backend/app/sync/queue.py'], graph={})[0] == runner.BACKEND
    assert runner.select(['backend/app/sync/checkpoints.py'], graph={})[0] == {'sync'}
    for module in ('google_login', 'oauth_sessions'):
        assert runner.select([f'backend/app/{module}.py'], graph={})[0] == {'agent', 'followups', 'auth', 'migrations', 'system'}
    assert runner.select(['backend/app/agent_call_context.py'], graph={})[0] == runner.BACKEND


def test_frontend_import_graph_tracks_transitive_components_and_raw_assets():
    graph = runner.frontend_dependencies()
    _, front, _ = runner.select(['frontend/src/components/shared/TemplateField.vue'], graph)
    assert front == {'auth', 'followups', 'shell'}
    _, front, _ = runner.select(['frontend/public/sw.js'], graph)
    assert front == {'notifications'}


def test_shared_and_unknown_files_fall_back_to_full_affected_layer():
    assert runner.select(['backend/app/models.py'], graph={})[0] == runner.BACKEND
    assert runner.select(['backend/app/new_service.py'], graph={})[0] == runner.BACKEND
    assert runner.select(['frontend/src/new-component.vue'], graph={})[1] == runner.FRONTEND
    back, front, tooling = runner.select(['scripts/test.py'], graph={})
    assert (back, front, tooling) == (runner.BACKEND | runner.VENDOR.keys(), runner.FRONTEND, True)


def test_test_changes_select_own_segment_and_docs_select_none():
    assert {p.parent.name for p in (runner.ROOT / 'backend/tests').glob('*/test_*.py')} == runner.BACKEND
    assert {p.parent.name for p in (runner.ROOT / 'frontend/tests').glob('*/*.test.ts')} == runner.FRONTEND
    assert runner.select(['backend/tests/posting/test_posting_checker.py'], graph={})[0] == {'posting'}
    assert runner.select(['frontend/tests/auth/auth.test.ts'], graph={})[1] == {'auth'}
    assert runner.select(['README.md', 'design.md'], graph={}) == (set(), set(), False)
    with pytest.raises(ValueError):
        runner.select(['../outside-workspace.py'], graph={})


def test_changed_paths_union_worktree_untracked_and_committed_changes():
    with patch.object(runner, 'git_paths', side_effect=[['deleted.py', 'staged.py'], ['new.py'], ['committed.py', 'staged.py']]), patch.object(runner.subprocess, 'run') as run:
        run.return_value.stdout = 'abc123\n'
        assert runner.changed_paths('origin/main') == ['committed.py', 'deleted.py', 'new.py', 'staged.py']
        assert '--end-of-options' in run.call_args.args[0]


def test_full_gate_order_and_failure_propagation():
    commands = runner.commands(runner.BACKEND | runner.VENDOR.keys(), runner.FRONTEND, tooling=True, full=True)
    assert commands[0][1] == ['pnpm', 'build']
    assert commands[1][1][-2:] == ['pip', 'check']
    assert set(commands[2][1][8:]) == {f'backend/tests/{name}' for name in runner.BACKEND} | set(runner.VENDOR.values()) | {'tests'}
    assert runner.VENDOR['toolbox'] not in runner.commands({'followups'}, set())[0][1]
    assert runner.commands({'toolbox'}, set())[0][1][8:] == [runner.VENDOR['toolbox']]
    temp = Path(commands[2][1][commands[2][1].index('--basetemp') + 1])
    assert temp.is_relative_to(runner.ROOT / '.run')
    assert temp != Path(runner.commands({'system'}, set())[0][1][7])
    assert commands[3][1][:2] == ['pnpm', 'test']
    with patch.object(runner.subprocess, 'run') as run, patch.object(runner.shutil, 'which', return_value='python'):
        run.return_value.returncode = 7
        assert runner.main(['--segment', 'notifications']) == 7
        assert run.call_count == 1


def test_fresh_checkout_creates_test_parent_only_when_running(tmp_path):
    with patch.object(runner,'ROOT',tmp_path),patch.object(runner.subprocess,'run') as run,patch.object(runner.shutil,'which',return_value='python'):
        run.return_value.returncode=0
        assert runner.main(['--segment','tooling','--dry-run'])==0
        assert not (tmp_path/'.run').exists()
        assert runner.main(['--segment','tooling'])==0
        assert (tmp_path/'.run').is_dir()
