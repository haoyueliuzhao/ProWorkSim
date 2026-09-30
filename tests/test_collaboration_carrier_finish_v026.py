"""One-shot terminal reporting must not invent closure or restart experiments."""

import json

import pytest

from proworksim.storage import json_bytes
from scripts import finish_collaboration_carrier_v026 as wrapper


def _paths(tmp_path):
    plan = tmp_path / 'plan.json'
    plan.write_bytes(json_bytes({'frozen': True}))
    return plan, tmp_path / 'run', tmp_path / 'reports' / 'end.json', tmp_path / 'reports' / 'end.md'


@pytest.mark.parametrize('status,code', [('complete', 0), ('closed_with_incomplete_workers', 2)])
def test_one_supervisor_call_and_terminal_only_reporting(monkeypatch, tmp_path, status, code):
    paths = _paths(tmp_path)
    calls = []

    def run(plan, root):
        calls.append(('run', plan, root))
        return {'status': status}

    def load(root, *, require_terminal):
        calls.append(('load', root, require_terminal))
        assert require_terminal is True
        return {'run_status': status, 'terminal': True, 'overall': {'known': 0, 'not_started': 16}}

    monkeypatch.setattr(wrapper.supervisor, 'run', run)
    monkeypatch.setattr(wrapper.reporting, 'load_run', load)
    monkeypatch.setattr(wrapper.reporting, 'markdown', lambda report: 'Original terminal report.\n')
    result = wrapper.finish(*paths)
    assert calls == [('run', paths[0].resolve(), paths[1].resolve()), ('load', paths[1].resolve(), True)]
    assert result['terminal'] is True
    assert result['finish_wrapper']['terminal_report_verified'] is True
    assert result['overall']['known'] == 0
    assert wrapper.exit_code(result) == code
    assert json.loads(paths[2].read_text()) == result
    assert 'Original terminal report.' in paths[3].read_text()
    assert json.loads(paths[0].read_text()) == {'frozen': True}


def test_exception_with_still_running_archive_does_not_fabricate_terminal(monkeypatch, tmp_path):
    paths = _paths(tmp_path)
    raw = {'status': 'running', 'started_at': 1.0}

    def run(plan, root):
        root.mkdir()
        (root / 'supervisor.json').write_bytes(json_bytes(raw))
        raise RuntimeError('outside managed supervisor section')

    monkeypatch.setattr(wrapper.supervisor, 'run', run)
    # Use the real terminal guard: it rejects before inspecting plan metadata.
    result = wrapper.finish(*paths)
    assert result['terminal'] is False
    assert result['run_status'] == 'terminal_report_unavailable'
    assert result['finish_wrapper']['supervisor_error'] == {'type': 'RuntimeError', 'message': 'outside managed supervisor section'}
    assert result['finish_wrapper']['report_error']['type'] == 'ValueError'
    assert result['observed_supervisor']['status'] == 'running'
    assert 'overall' not in result and 'reward' not in result
    assert wrapper.exit_code(result) == 3
    assert json.loads((paths[1] / 'supervisor.json').read_text()) == raw
    assert '不代表实验完成' in paths[3].read_text()


def test_preflight_exception_is_retained_when_no_run_archive_exists(monkeypatch, tmp_path):
    paths = _paths(tmp_path)

    def run(plan, root):
        raise ValueError('qualification changed before execution')

    monkeypatch.setattr(wrapper.supervisor, 'run', run)
    result = wrapper.finish(*paths)
    assert not paths[1].exists()
    assert result['terminal'] is False
    assert result['observed_supervisor']['available'] is False
    assert result['finish_wrapper']['supervisor_error']['message'] == 'qualification changed before execution'
    assert paths[2].is_file() and paths[3].is_file()


def test_supervisor_exception_does_not_suppress_valid_closed_report(monkeypatch, tmp_path):
    paths = _paths(tmp_path)

    def run(plan, root):
        raise KeyboardInterrupt('interrupted after a recorded terminal boundary')

    monkeypatch.setattr(wrapper.supervisor, 'run', run)
    monkeypatch.setattr(wrapper.reporting, 'load_run', lambda root, require_terminal: {'run_status': 'supervisor_error', 'terminal': True})
    monkeypatch.setattr(wrapper.reporting, 'markdown', lambda report: 'Saved terminal evidence.\n')
    result = wrapper.finish(*paths)
    assert result['terminal'] is True
    assert result['finish_wrapper']['supervisor_error']['type'] == 'KeyboardInterrupt'
    assert result['finish_wrapper']['terminal_report_verified'] is True
    assert wrapper.exit_code(result) == 2
    assert 'Saved terminal evidence.' in paths[3].read_text()
    assert 'KeyboardInterrupt' in paths[3].read_text()


def test_report_render_failure_is_archived_without_claiming_validated_completion(monkeypatch, tmp_path):
    paths = _paths(tmp_path)
    monkeypatch.setattr(wrapper.supervisor, 'run', lambda plan, root: {'status': 'complete'})
    monkeypatch.setattr(wrapper.reporting, 'load_run', lambda root, require_terminal: {'run_status': 'complete', 'terminal': True})

    def broken_markdown(report):
        raise ValueError('required original assessment missing')

    monkeypatch.setattr(wrapper.reporting, 'markdown', broken_markdown)
    result = wrapper.finish(*paths)
    assert result['terminal'] is False
    assert result['finish_wrapper']['report_error']['message'] == 'required original assessment missing'
    assert result['finish_wrapper']['supervisor_return_status'] == 'complete'
    assert wrapper.exit_code(result) == 3
