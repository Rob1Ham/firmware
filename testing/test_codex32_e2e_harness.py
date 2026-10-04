"""Host-only safety tests for the Codex32 simulator release harness."""

import os
import signal
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

import codex32_e2e_harness as harness
from codex32_e2e_harness import (collect, junit_id, parse_junit, run_logged,
                                 skipped_are_disposed)


@pytest.mark.parametrize('code,expected', [
    ('print("ok")', 0),
    ('raise SystemExit(7)', 7),
    ('import os,signal; os.kill(os.getpid(), signal.SIGKILL)', -signal.SIGKILL),
])
def test_child_status_propagates(tmp_path, code, expected):
    result = run_logged([sys.executable, '-c', code], cwd=tmp_path,
                        env=os.environ.copy(), log_path=tmp_path / 'child.log', timeout=5)
    assert result['exit_code'] == expected
    assert result['timed_out'] is False


def test_timeout_kills_owned_process(tmp_path):
    pid_file = tmp_path / 'pid'
    code = f'import os,time; open({str(pid_file)!r}, "w").write(str(os.getpid())); time.sleep(30)'
    result = run_logged([sys.executable, '-c', code], cwd=tmp_path,
                        env=os.environ.copy(), log_path=tmp_path / 'child.log', timeout=0.3)
    assert result['timed_out'] is True
    pid = int(pid_file.read_text())
    with pytest.raises(ProcessLookupError):
        os.kill(pid, 0)


def test_interrupt_kills_owned_process(tmp_path, monkeypatch):
    real_popen = harness.subprocess.Popen
    child = {}

    class InterruptOnce:
        def __init__(self, proc):
            self.proc = proc
            self.pid = proc.pid
            self.interrupted = False

        def wait(self, *args, **kwargs):
            if not self.interrupted:
                self.interrupted = True
                raise KeyboardInterrupt
            return self.proc.wait(*args, **kwargs)

        def poll(self):
            return self.proc.poll()

    def start_child(*args, **kwargs):
        child['proc'] = InterruptOnce(real_popen(*args, **kwargs))
        return child['proc']

    monkeypatch.setattr(harness.subprocess, 'Popen', start_child)
    with pytest.raises(KeyboardInterrupt):
        run_logged([sys.executable, '-c', 'import time; time.sleep(30)'],
                   cwd=tmp_path, env=os.environ.copy(),
                   log_path=tmp_path / 'child.log', timeout=5)
    with pytest.raises(ProcessLookupError):
        os.kill(child['proc'].pid, 0)


def test_missing_empty_and_skipped_junit_are_visible(tmp_path):
    with pytest.raises(ValueError, match='missing'):
        parse_junit(tmp_path / 'missing.xml')
    empty = tmp_path / 'empty.xml'
    empty.write_text('<testsuite tests="0"/>')
    with pytest.raises(ValueError, match='no testcases'):
        parse_junit(empty)
    incomplete = tmp_path / 'incomplete.xml'
    incomplete.write_text('<testsuite><testcase')
    with pytest.raises(Exception):
        parse_junit(incomplete)
    skipped = tmp_path / 'skipped.xml'
    skipped.write_text('<testsuite><testcase classname="x" name="y">'
                       '<skipped message="display unavailable"/></testcase></testsuite>')
    report = parse_junit(skipped)
    assert report['counts'] == {'collected': 1, 'passed': 0, 'failed': 0,
                                'error': 0, 'skipped': 1}
    assert report['skip_reasons'][0]['reason'] == 'display unavailable'


def test_empty_selection_is_not_success(tmp_path):
    root = Path(__file__).resolve().parents[1]
    args = SimpleNamespace(python=Path(sys.executable), root=root,
                           marks='not onetime and not veryslow and not manual',
                           select='no_such_codex32_test_id', target=['test_unit.py'],
                           collect_timeout=30, require_node=[])
    env = dict(os.environ, PYSECP_SO='/opt/homebrew/lib/libsecp256k1.dylib')
    result = collect(args, env, tmp_path)
    assert result['ok'] is False
    assert result['selected_count'] == 0


def test_frozen_coverage_rejects_disappearing_test(tmp_path, monkeypatch):
    def collect_one(*args, **kwargs):
        kwargs['log_path'].write_text('test_dummy.py::test_one\n1 test collected\n')
        return {'exit_code': 0, 'timed_out': False}

    monkeypatch.setattr(harness, 'run_logged', collect_one)
    args = SimpleNamespace(python=Path(sys.executable), root=tmp_path,
                           marks='not onetime and not veryslow and not manual',
                           select='', target=['test_dummy.py'], collect_timeout=5,
                           require_node=[],
                           coverage_ids=['test_dummy.py::test_one',
                                         'test_dummy.py::test_required'])
    result = collect(args, os.environ.copy(), tmp_path)
    assert result['ok'] is False
    assert result['coverage_missing'] == ['test_dummy.py::test_required']
    assert result['coverage_unexpected'] == []


def test_junit_ids_and_skip_dispositions_are_exact():
    assert junit_id('test_codex32.py::test_roundtrip[ms16]') == \
        'test_codex32::test_roundtrip[ms16]'
    skips = [{'test': 'test_codex32::test_q1_only',
              'reason': 'Q1 hardware profile required'}]
    ledger = {'test_codex32::test_q1_only': {
        'reason': 'Q1 hardware profile required',
        'disposition': 'covered in Q1 display lane'}}
    assert skipped_are_disposed(skips, ledger, [])
    assert not skipped_are_disposed(skips, {}, [])
    assert not skipped_are_disposed(skips, ledger, ['test_q1_only'])
    assert not skipped_are_disposed(skips, {
        'test_codex32::test_q1_only': {'reason': 'another reason',
                                       'disposition': 'covered elsewhere'}}, [])


def test_passing_retry_cannot_erase_first_failure(tmp_path, monkeypatch, capsys):
    binary = tmp_path / 'unix/coldcard-mpy'
    binary.parent.mkdir()
    binary.write_bytes(b'dummy simulator')
    monkeypatch.setattr(harness.subprocess, 'check_output',
                        lambda command, text: 'a' * 40 + '\n' if 'rev-parse' in command else '')
    monkeypatch.setattr(harness, 'collect', lambda *a: {
        'ok': True, 'selected_count': 1,
        'selected_ids': ['test_dummy.py::test_value']})
    attempts = iter(({'ok': False, 'exit_code': 1, 'counts': {'failed': 1}},
                     {'ok': True, 'exit_code': 0, 'counts': {'passed': 1}}))
    monkeypatch.setattr(harness, 'attempt', lambda *a: next(attempts))
    output = tmp_path / 'artifacts'
    monkeypatch.setattr(sys, 'argv', ['harness', '--root', str(tmp_path),
                        '--model', 'mk4', '--target', 'test_dummy.py',
                        '--artifacts', str(output), '--retry'])
    assert harness.main() == 1
    report = __import__('json').loads((output / 'manifest.json').read_text())
    assert report['qualified'] is False
    assert report['first_attempt']['ok'] is False
    assert report['retry']['ok'] is True
    assert '"qualified": false' in capsys.readouterr().out


def test_interrupt_writes_failed_manifest(tmp_path, monkeypatch):
    binary = tmp_path / 'unix/coldcard-mpy'
    binary.parent.mkdir()
    binary.write_bytes(b'dummy simulator')
    monkeypatch.setattr(harness.subprocess, 'check_output',
                        lambda command, text: 'a' * 40 + '\n' if 'rev-parse' in command else '')
    monkeypatch.setattr(harness, 'collect', lambda *a: {
        'ok': True, 'selected_count': 1,
        'selected_ids': ['test_dummy.py::test_value']})

    def interrupted_attempt(*args):
        raise KeyboardInterrupt

    monkeypatch.setattr(harness, 'attempt', interrupted_attempt)
    output = tmp_path / 'artifacts'
    monkeypatch.setattr(sys, 'argv', ['harness', '--root', str(tmp_path),
                        '--model', 'mk4', '--target', 'test_dummy.py',
                        '--artifacts', str(output)])
    assert harness.main() == 130
    report = __import__('json').loads((output / 'manifest.json').read_text())
    assert report['qualified'] is False
    assert report['interrupted'] is True
    assert report['harness_error'].startswith('KeyboardInterrupt:')
