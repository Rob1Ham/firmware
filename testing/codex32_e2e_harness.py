"""Fail-closed local simulator test runner for Codex32 qualification.

One invocation owns one simulator process group, one storage directory, one
socket, one pytest process group, and its reports. A retry is diagnostic only.
Run from any directory with the isolated firmware checkout as --root.
"""

import argparse
import contextlib
import hashlib
import json
import os
import re
import signal
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path


def sha256(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as source:
        for block in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def as_text(value):
    return value.decode() if isinstance(value, bytes) else str(value)


def stop_group(proc):
    # The leader may exit while its children remain. Own and terminate the
    # process group even in that case.
    with contextlib.suppress(ProcessLookupError):
        os.killpg(proc.pid, signal.SIGTERM)
    if proc.poll() is None:
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            with contextlib.suppress(ProcessLookupError):
                os.killpg(proc.pid, signal.SIGKILL)
            proc.wait(timeout=5)


def run_logged(cmd, *, cwd, env, log_path, timeout):
    started = time.monotonic()
    with open(log_path, 'w') as log:
        proc = subprocess.Popen(cmd, cwd=cwd, env=env, stdout=log,
                                stderr=subprocess.STDOUT, start_new_session=True)
        timed_out = False
        try:
            code = proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            stop_group(proc)
            code = proc.returncode
        except BaseException:
            stop_group(proc)
            raise
    return {'command': cmd, 'exit_code': code, 'timed_out': timed_out,
            'seconds': round(time.monotonic() - started, 3),
            'log': str(log_path)}


def parse_junit(path):
    if not path.exists():
        raise ValueError('missing JUnit XML')
    root = ET.parse(path).getroot()
    cases = root.findall('.//testcase')
    if not cases:
        raise ValueError('JUnit XML contains no testcases')
    counts = {'passed': 0, 'failed': 0, 'error': 0, 'skipped': 0}
    ids = []
    skip_reasons = []
    for case in cases:
        node = case.get('classname', '') + '::' + case.get('name', '')
        ids.append(node)
        outcome = next((name for name in ('failure', 'error', 'skipped')
                        if case.find(name) is not None), None)
        if outcome == 'failure':
            counts['failed'] += 1
        elif outcome == 'error':
            counts['error'] += 1
        elif outcome == 'skipped':
            counts['skipped'] += 1
            skip_reasons.append({'test': node,
                                 'reason': case.find('skipped').get('message', '')})
        else:
            counts['passed'] += 1
    counts['collected'] = len(cases)
    return {'counts': counts, 'ids': ids, 'skip_reasons': skip_reasons}


def junit_id(collection_id):
    """Map a pytest node ID to the JUnit classname/name convention."""
    path, separator, name = collection_id.partition('::')
    if not separator:
        return collection_id
    return path.removesuffix('.py').replace('/', '.') + '::' + name


def skipped_are_disposed(skips, ledger, required_nodes):
    for skip in skips:
        item = ledger.get(skip['test'])
        if (not item or not item.get('disposition') or
                item.get('reason') not in skip['reason'] or
                any(required in skip['test'] for required in required_nodes)):
            return False
    return True


def collect(args, env, artifacts):
    cmd = [str(args.python), '-m', 'pytest', '--collect-only', '-q',
           '-o', 'addopts=', '-m', args.marks]
    if args.select:
        cmd.extend(['-k', args.select])
    cmd.extend(args.target)
    result = run_logged(cmd, cwd=args.root / 'testing', env=env,
                        log_path=artifacts / 'collection.log', timeout=args.collect_timeout)
    text = (artifacts / 'collection.log').read_text(errors='replace')
    selected = [line for line in text.splitlines()
                if '::' in line and not line.startswith((' ', '='))
                and not line.startswith('WARNING')]
    result['selected_ids'] = selected
    result['selected_count'] = len(selected)
    result['ok'] = (result['exit_code'] == 0 and not result['timed_out']
                    and bool(selected) and all(any(required in node for node in selected)
                                               for required in args.require_node))
    return result


def ready(proc, socket_path, expected_model, timeout):
    from ckcc.client import ColdcardDevice
    from ckcc.protocol import CCProtocolPacker
    deadline = time.monotonic() + timeout
    last_error = None
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(f'simulator exited before readiness: {proc.returncode}')
        if socket_path.exists():
            try:
                dev = ColdcardDevice(sn=str(socket_path), is_simulator=True,
                                     encrypt=False, timeout=2000)
                version = dev.send_recv(CCProtocolPacker.version(), timeout=2000)
                parts = as_text(version).split()
                label = parts[4].lower() if len(parts) > 4 else ''
                if label != expected_model:
                    raise RuntimeError(f'expected {expected_model}, got {label}: {version!r}')
                source = as_text(dev.send_recv(
                    b'EXECimport codex32, ckcc; RV.write(codex32.__file__ + "|" + ckcc.get_sim_root_dirs()[0])',
                    encrypt=False, timeout=2000))
                dev.close()
                return {'version': as_text(version), 'model': label,
                        'source_and_storage': source, 'socket': str(socket_path)}
            except RuntimeError:
                raise
            except Exception as exc:
                last_error = f'{type(exc).__name__}: {exc}'
        time.sleep(.1)
    raise TimeoutError(f'simulator readiness timeout; last error: {last_error}')


def attempt(args, env, artifacts, label, storage, expected_count):
    from ckcc.client import ColdcardDevice  # noqa: F401; fail before starting simulator
    sim_log = artifacts / f'{label}-simulator.log'
    test_log = artifacts / f'{label}-pytest.log'
    junit = artifacts / f'{label}-junit.xml'
    socket_path = None
    storage.mkdir(parents=True, exist_ok=True)
    sim_env = dict(env, CKCC_SIM_WORKDIR=str(storage))
    sim_cmd = [str(args.python), 'simulator.py', '--segregate']
    if args.headless:
        sim_cmd.append('--headless')
    if args.model != 'mk5':
        sim_cmd.append('--' + args.model)
    for setting in args.setting:
        sim_cmd.extend(['--set', setting])
    with open(sim_log, 'w') as log:
        proc = subprocess.Popen(sim_cmd, cwd=args.root / 'unix', env=sim_env,
                                stdout=log, stderr=subprocess.STDOUT,
                                start_new_session=True)
        socket_path = Path(f'/tmp/ckcc-simulator-{proc.pid}.sock')
        try:
            identity = ready(proc, socket_path, args.model, args.ready_timeout)
            expected_source = str((args.root / 'shared/codex32.py').resolve())
            expected_storage = str(storage.resolve())
            if identity['source_and_storage'] != expected_source + '|' + expected_storage:
                raise RuntimeError('simulator source/storage identity mismatch: '
                                   + identity['source_and_storage'])
            # Put test paths before custom conftest options. With an existing
            # Unix socket as --sim-socket's value, pytest's early path scan can
            # otherwise miss conftest and reject its options.
            command = [str(args.python), '-m', 'pytest', *args.target,
                       '-q', '-o', 'addopts=',
                       '-m', args.marks, '--sim', '--sim-socket', str(socket_path),
                       '--junitxml', str(junit)]
            if args.headless:
                command.append('--headless')
            if args.model == 'q1':
                command.append('--Q')
            else:
                command.extend(['--mk', '4' if args.model == 'mk4' else '5'])
            if args.select:
                command.extend(['-k', args.select])
            result = run_logged(command, cwd=args.root / 'testing', env=env,
                                log_path=test_log, timeout=args.test_timeout)
            result.update({'simulator_command': sim_cmd, 'simulator_log': str(sim_log),
                           'storage': str(storage), 'identity': identity,
                           'junit': str(junit)})
            try:
                result.update(parse_junit(junit))
            except (ET.ParseError, ValueError) as exc:
                result['report_error'] = str(exc)
            counts = result.get('counts', {})
            expected_ids = {junit_id(item) for item in args.selected_ids}
            actual_ids = result.get('ids', [])
            result['selected_ids_match'] = (len(actual_ids) == len(set(actual_ids))
                                            and set(actual_ids) == expected_ids)
            result['skips_disposed'] = skipped_are_disposed(
                result.get('skip_reasons', []), args.skip_ledger,
                args.require_node)
            result['ok'] = (result['exit_code'] == 0 and not result['timed_out']
                            and not result.get('report_error')
                            and counts.get('collected', 0) == expected_count
                            and result['selected_ids_match']
                            and counts.get('failed', 0) == 0
                            and counts.get('error', 0) == 0
                            and result['skips_disposed'])
            return result
        finally:
            stop_group(proc)
            if socket_path.exists():
                socket_path.unlink()  # only this process's socket


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--python', type=Path, default=Path(sys.executable))
    parser.add_argument('--model', choices=('mk4', 'mk5', 'q1'), required=True)
    parser.add_argument('--artifacts', type=Path, required=True)
    parser.add_argument('--storage', type=Path)
    parser.add_argument('--target', action='append', required=True)
    parser.add_argument('--require-node', action='append', default=[])
    parser.add_argument('--select', default='')
    parser.add_argument('--marks', default='not onetime and not veryslow and not manual')
    parser.add_argument('--setting', action='append', default=['nfc=1'])
    parser.add_argument('--headless', action='store_true')
    parser.add_argument('--skip-ledger', type=Path,
                        help='JSON map of exact test IDs to reason substring and disposition')
    parser.add_argument('--allow-dirty', action='store_true',
                        help='Development runs only; final qualification requires committed source')
    parser.add_argument('--retry', action='store_true')
    parser.add_argument('--collect-timeout', type=int, default=90)
    parser.add_argument('--ready-timeout', type=int, default=45)
    parser.add_argument('--test-timeout', type=int, default=1200)
    parser.add_argument('--expect-commit', default='')
    args = parser.parse_args()
    args.root = args.root.resolve()
    # Keep the venv entry point: resolve() follows its interpreter symlink and
    # silently drops the virtual environment's site-packages.
    args.python = Path(os.path.abspath(args.python))
    args.artifacts = args.artifacts.resolve()
    args.artifacts.mkdir(parents=True, exist_ok=True)
    args.skip_ledger = json.loads(args.skip_ledger.read_text()) if args.skip_ledger else {}
    binary = (args.root / 'unix/coldcard-mpy').resolve()
    commit = subprocess.check_output(['git', '-C', str(args.root), 'rev-parse', 'HEAD'],
                                     text=True).strip()
    report = {'schema_version': 1, 'source_commit': commit, 'model': args.model,
              'binary': str(binary), 'binary_sha256': sha256(binary),
              'root': str(args.root), 'artifacts': str(args.artifacts)}
    report['working_tree_status'] = subprocess.check_output(
        ['git', '-C', str(args.root), 'status', '--porcelain',
         '--ignore-submodules=dirty'], text=True).strip().splitlines()
    env = dict(os.environ, PYSECP_SO=os.environ.get('PYSECP_SO',
                                                   '/opt/homebrew/lib/libsecp256k1.dylib'))
    try:
        if args.expect_commit and commit != args.expect_commit:
            raise RuntimeError('source commit differs from --expect-commit')
        if report['working_tree_status'] and not args.allow_dirty:
            raise RuntimeError('working tree is not committed; use --allow-dirty only for development')
        report['collection'] = collect(args, env, args.artifacts)
        if not report['collection']['ok']:
            raise RuntimeError('collection failed, selected no tests, or missed required node')
        args.selected_ids = report['collection']['selected_ids']
        storage = args.storage.resolve() if args.storage else args.artifacts / 'storage'
        expected_count = report['collection']['selected_count']
        report['first_attempt'] = attempt(args, env, args.artifacts, 'first',
                                          storage, expected_count)
        if args.retry and not report['first_attempt']['ok']:
            report['retry'] = attempt(args, env, args.artifacts, 'retry',
                                      args.artifacts / 'retry-storage', expected_count)
        report['qualified'] = bool(report['first_attempt']['ok'])
    except KeyboardInterrupt:
        report['qualified'] = False
        report['interrupted'] = True
        report['harness_error'] = 'KeyboardInterrupt: run interrupted'
    except Exception as exc:
        report['qualified'] = False
        report['harness_error'] = f'{type(exc).__name__}: {exc}'
    report_path = args.artifacts / 'manifest.json'
    report_path.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'qualified': report['qualified'], 'manifest': str(report_path),
                      'error': report.get('harness_error')}, sort_keys=True))
    return 0 if report['qualified'] else 130 if report.get('interrupted') else 1


if __name__ == '__main__':
    sys.exit(main())
