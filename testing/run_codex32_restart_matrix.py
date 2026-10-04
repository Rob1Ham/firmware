"""Run three separate simulator processes per persistence/cancellation case.

Each repetition owns fresh encrypted settings storage. A failed stage stops
that repetition and makes the aggregate result nonzero; no retry can erase it.
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STAGES = ('test_restart_prepare', 'test_restart_verify_and_discard',
          'test_restart_verify_discard')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--artifacts', type=Path, required=True)
    parser.add_argument('--models', nargs='+', choices=('mk4', 'mk5', 'q1'),
                        default=['mk4', 'mk5', 'q1'])
    parser.add_argument('--repetitions', type=int, default=3)
    parser.add_argument('--allow-dirty', action='store_true')
    args = parser.parse_args()
    if args.repetitions < 1:
        parser.error('repetitions must be positive')
    base = args.artifacts.resolve()
    base.mkdir(parents=True, exist_ok=True)
    report = {'schema_version': 1, 'models': args.models,
              'repetitions': args.repetitions, 'stages': []}
    for model in args.models:
        for repetition in range(1, args.repetitions + 1):
            case_dir = base / f'{model}-{repetition:02}'
            case_dir.mkdir()
            storage = case_dir / 'storage'
            evidence = case_dir / 'expected.json'
            for stage in STAGES:
                output = case_dir / stage
                cmd = [sys.executable, str(ROOT / 'testing/codex32_e2e_harness.py'),
                       '--model', model, '--headless', '--target',
                       'test_codex32_restart.py', '--select', stage,
                       '--storage', str(storage), '--artifacts', str(output),
                       '--require-node', stage, '--test-timeout', '180']
                if args.allow_dirty:
                    cmd.append('--allow-dirty')
                env = dict(os.environ, C32_RESTART_EVIDENCE=str(evidence))
                proc = subprocess.run(cmd, cwd=ROOT / 'testing', env=env,
                                      text=True, capture_output=True, timeout=300)
                item = {'model': model, 'repetition': repetition, 'stage': stage,
                        'exit_code': proc.returncode,
                        'manifest': str(output / 'manifest.json'),
                        'stdout': proc.stdout.strip(), 'stderr': proc.stderr[-1000:]}
                report['stages'].append(item)
                print(f'{model} repetition {repetition} {stage}: exit {proc.returncode}',
                      flush=True)
                if proc.returncode:
                    report['qualified'] = False
                    (base / 'matrix.json').write_text(json.dumps(report, indent=2) + '\n')
                    return 1
    report['qualified'] = True
    (base / 'matrix.json').write_text(json.dumps(report, indent=2) + '\n')
    return 0


if __name__ == '__main__':
    sys.exit(main())
