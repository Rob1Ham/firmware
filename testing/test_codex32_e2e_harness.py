"""Host-only safety tests for the Codex32 simulator release harness."""

import os
import signal
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

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
