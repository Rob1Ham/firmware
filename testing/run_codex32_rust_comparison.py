"""Capability-scoped comparison against the pinned, unchanged Rust crate.

BIP 93 vectors decide correctness. Rust's older length and HRP behavior is
reported, never used as a vote to waive a firmware conformance failure.
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

PIN = '1a1c22aa895d78f2d385303feb9491d155e14cf7'


def build_adapter(source, artifacts):
    crate = source / 'reference/rust-codex32'
    artifacts.mkdir(parents=True, exist_ok=True)
    lib = artifacts / 'libcodex32_reference.rlib'
    exe = artifacts / 'codex32_ref_rust_adapter'
    subprocess.run(['rustc', '--edition=2018', '--crate-name=codex32',
                    '--crate-type=rlib', str(crate / 'src/lib.rs'),
                    '-o', str(lib)], check=True, timeout=60)
    subprocess.run(['rustc', '--edition=2018',
                    str(ROOT / 'testing/codex32_ref_rust_adapter.rs'),
                    '--extern', f'codex32={lib}', '-o', str(exe)],
                   check=True, timeout=60)
    return exe


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    revision = subprocess.check_output(
        ['git', '-C', str(args.source), 'rev-parse', 'HEAD'], text=True).strip()
    if revision != PIN:
        parser.error('Rust reference source is not at the required commit')
    vectors = json.loads((ROOT / 'testing/fixtures/codex32-bip93-vectors.json').read_text())
    cases = [(v['id'], v['encoded'], True, 'bip93-valid') for v in vectors['valid']]
    cases += [(v['id'], v['encoded'], False, 'bip93-invalid') for v in vectors['invalid']]
    rng = random.Random(93033)
    for size in (16, 20, 24, 28, 32, 64):
        bits = (-size * 8) % 5
        for index in range(60):
            share = Share.from_seed(rng.randbytes(size), 'ms',
                                    ''.join(rng.choice(CHARSET) for _ in range(4)),
                                    's', 0, rng.randrange(1 << bits))
            cases.append((f'generated-{size}-{index:02}', share.to_string(),
                          True, 'generated'))

    exe = build_adapter(args.source, args.output.parent)
    proc = subprocess.run([str(exe)], input=''.join(s + '\n' for _, s, _, _ in cases),
                          text=True, capture_output=True, timeout=60, check=True)
    responses = proc.stdout.splitlines()
    if len(responses) != len(cases):
        raise RuntimeError(f'Rust returned {len(responses)} of {len(cases)} cases')
    disagreements = []
    firmware_failures = []
    rust_valid_failures = []
    for (case_id, encoded, expected_valid, category), response in zip(cases, responses):
        status, _, data = response.partition('\t')
        try:
            share = Share.parse(encoded)
            firmware_valid = True
        except (AssertionError, ValueError):
            share = None
            firmware_valid = False
        if firmware_valid != expected_valid:
            firmware_failures.append({'case_id': case_id, 'rule': 'BIP93 validity',
                                      'expected_valid': expected_valid,
                                      'firmware_valid': firmware_valid})
        if expected_valid:
            if status != 'OK':
                rust_valid_failures.append({'case_id': case_id,
                                            'rule': 'valid MS1 parse', 'rust': response})
            elif share is not None:
                seed = share.to_seed_and_pad()[0]
                if data != seed.hex():
                    disagreements.append({'case_id': case_id, 'rule': 'MS1 seed bytes',
                                          'firmware': seed.hex(), 'rust': data})
        elif status == 'OK':
            rule = 'HRP scope' if not encoded.lower().startswith('ms1') else 'invalid MS1 acceptance'
            disagreements.append({'case_id': case_id, 'rule': rule,
                                  'rust': response, 'category': category})
        elif status == 'PANIC':
            disagreements.append({'case_id': case_id, 'rule': 'Rust parser panic',
                                  'category': category})
    report = {'schema_version': 1, 'reference': {'implementation': 'BlockstreamResearch/codex32',
              'commit': revision, 'crate': 'reference/rust-codex32',
              'capabilities': ['MS1 short and long checksum parsing', 'seed data decoding'],
              'limits': ['HRP-agnostic parser', 'older length selection',
                         'interpolation checks minimum rather than exact threshold']},
              'counts': {'valid_vectors': len(vectors['valid']),
                         'invalid_vectors': len(vectors['invalid']), 'generated': 360,
                         'firmware_failures': len(firmware_failures),
                         'rust_valid_failures': len(rust_valid_failures),
                         'disagreements': len(disagreements)},
              'firmware_failures': firmware_failures,
              'rust_valid_failures': rust_valid_failures,
              'disagreements': disagreements,
              'rust_stderr': proc.stderr[-2000:]}
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report['counts'], sort_keys=True))
    return 1 if firmware_failures or rust_valid_failures or any(
        item['rule'] == 'MS1 seed bytes' for item in disagreements) else 0


if __name__ == '__main__':
    sys.exit(main())
