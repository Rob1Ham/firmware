"""Compare firmware MS1 decoding with a separately installed pinned reference.

This is a capability-scoped comparison, not a validity vote. The BIP 93
vectors are normative; reference disagreement is recorded for review.
"""

import argparse
import json
import random
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'shared'))
from codex32 import CHARSET, Share  # noqa: E402

PIN = '8ab3bae9e5e0877b74cbaca52b2f05229e172f3e'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--python', type=Path, required=True,
                        help='Interpreter in the separate Python-reference environment')
    parser.add_argument('--source', type=Path, required=True,
                        help='Checkout of the pinned Python reference')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    revision = subprocess.check_output(['git', '-C', str(args.source), 'rev-parse', 'HEAD'],
                                       text=True).strip()
    if revision != PIN:
        parser.error('Python reference source is not at the required commit')

    vectors = json.loads((ROOT / 'testing/fixtures/codex32-bip93-vectors.json').read_text())
    rng = random.Random(93032)
    cases = []
    for vector in vectors['valid']:
        cases.append({'case_id': vector['id'], 'operation': 'decode_ms',
                      'encoded': vector['encoded'], 'expected_valid': True,
                      'category': 'bip93-vector'})
    for vector in vectors['invalid']:
        cases.append({'case_id': vector['id'], 'operation': 'decode_ms',
                      'encoded': vector['encoded'], 'expected_valid': False,
                      'category': 'bip93-invalid'})
    for size in (16, 20, 24, 28, 32, 64):
        bits = (-size * 8) % 5
        for i in range(200):
            share = Share.from_seed(rng.randbytes(size), 'ms',
                                    ''.join(rng.choice(CHARSET) for _ in range(4)),
                                    's', 0, rng.randrange(1 << bits))
            cases.append({'case_id': f'generated-{size}-{i:03}',
                          'operation': 'decode_ms', 'encoded': share.to_string(),
                          'expected_valid': True, 'category': 'generated'})

    adapter = ROOT / 'testing/codex32_ref_python_adapter.py'
    stdin = ''.join(json.dumps({k: case[k] for k in ('case_id', 'operation', 'encoded')}) + '\n'
                    for case in cases)
    proc = subprocess.run([str(args.python), '-I', str(adapter)], input=stdin,
                          text=True, capture_output=True, timeout=60, check=False)
    if proc.returncode:
        raise RuntimeError('reference adapter failed: ' + proc.stderr[-2000:])
    responses = [json.loads(line) for line in proc.stdout.splitlines()]
    if len(responses) != len(cases):
        raise RuntimeError(f'reference returned {len(responses)} of {len(cases)} cases')

    disagreements = []
    reference_accepts_invalid = []
    for case, response in zip(cases, responses):
        if response['case_id'] != case['case_id'] or response['commit'] != PIN:
            raise RuntimeError('reference adapter identity or case order changed')
        if response['package_version'] != '0.6.2':
            raise RuntimeError('reference package version changed')
        try:
            firmware = Share.parse(case['encoded'])
            fw_ok = True
        except (AssertionError, ValueError):
            fw_ok = False
        if case['expected_valid']:
            if not fw_ok or not response['ok']:
                disagreements.append({'case_id': case['case_id'],
                                      'rule': 'valid BIP93 MS1 decode',
                                      'firmware_ok': fw_ok,
                                      'reference_error': response.get('error_type')})
                continue
            seed, padding = firmware.to_seed_and_pad()
            actual = (response['header'], response['seed_hex'], response['padding'])
            expected = (firmware.data()[:6], seed.hex(), padding)
            if actual != expected:
                disagreements.append({'case_id': case['case_id'],
                                      'rule': 'header/seed/padding identity',
                                      'firmware': expected, 'reference': actual})
        else:
            if fw_ok:
                disagreements.append({'case_id': case['case_id'],
                                      'rule': 'BIP93 invalid rejected by firmware'})
            if response['ok']:
                reference_accepts_invalid.append({'case_id': case['case_id'],
                                                  'classification': 'reference accepts BIP93-invalid input'})

    report = {'schema_version': 1, 'reference': {'repository': str(args.source),
              'commit': revision, 'package_version': '0.6.2',
              'module_file': responses[0]['module_file']},
              'counts': {'valid_vectors': len(vectors['valid']),
                         'invalid_vectors': len(vectors['invalid']),
                         'generated': 1200, 'disagreements': len(disagreements),
                         'reference_accepts_invalid': len(reference_accepts_invalid)},
              'disagreements': disagreements,
              'reference_accepts_invalid': reference_accepts_invalid}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report['counts'], sort_keys=True))
    return 1 if disagreements else 0


if __name__ == '__main__':
    sys.exit(main())
