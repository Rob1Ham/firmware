# (c) Copyright 2026 for the vault co-sign policy work; license per COPYING-CC.
#
# testing/test_vault_hostapp.py - host tests for hostapp/vault_tree.py.
#
# Exercises all three funding shapes (input-only, incorrect output,
# already-correct), verifies the built tree (deposit pays S_v, leaf fees,
# witness utxos chained to the deposit txid) and re-derives the lattice
# root INDEPENDENTLY from the written PSBT files.
#
# Run: python3 testing/test_vault_hostapp.py

import os, sys, json, shutil, subprocess, tempfile, hashlib

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'hostapp'))
# append (not insert) shared/ so firmware shims never shadow CPython stdlib
sys.path.append(os.path.join(HERE, '..', 'shared'))
import vault_tree as vt
import vault_policy as vp

APP = os.path.join(HERE, '..', 'hostapp', 'vault_tree.py')
FUNDING_VALUE = 100000
DEPOSIT_FEE = 500

R = []
def ok(name, cond):
    R.append((name, bool(cond)))
    print('%s: %s' % ('ok' if cond else 'FAIL', name))

def make_policy(tmp):
    # fixed demo keys (same as init-policy defaults)
    pol = {
        'k1': (b'\x02' + bytes(range(1, 33))).hex(),
        'k2': (b'\x03' + bytes(range(33, 65))).hex(),
        'k3': (b'\x02' + bytes(range(65, 97))).hex(),
        'n': 1008, 'f0_max': 10000, 'leaves': 5,
        'emg_fee': 500, 'emg_step': 13, 'deposit_fee': DEPOSIT_FEE,
    }
    path = os.path.join(tmp, 'policy.json')
    open(path, 'w').write(json.dumps(pol))
    return path

def make_funding(tmp, kind, spk_v, name):
    # one-input funding PSBT in the requested shape
    ins = [(hashlib.sha256(b'fund:' + name.encode()).digest(), 0, 0xFFFFFFFE)]
    if kind == 'input-only':
        outs = []
    elif kind == 'incorrect':
        outs = [(vp.p2wsh_spk(b'\x51' + b'\x00' * 40),
                 FUNDING_VALUE - DEPOSIT_FEE)]
    elif kind == 'correct':
        outs = [(spk_v, FUNDING_VALUE - DEPOSIT_FEE)]
    else:
        raise ValueError(kind)
    tx = vt.ser_tx(2, ins, outs, 0)
    wu = vt.ct_out(vp.p2wsh_spk(b'\x61' * 30), FUNDING_VALUE)
    im = vt.vi(1) + b'\x01' + vt.vi(len(wu)) + wu + b'\x00'
    path = os.path.join(tmp, name + '.psbt')
    open(path, 'wb').write(vt.build_psbt(tx, [im], len(outs)))
    return path

def run_app(policy, funding, outdir):
    r = subprocess.run(
        [sys.executable, APP, 'build', policy, funding, outdir],
        capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stdout)
        print(r.stderr)
    return r

def check_tree(outdir, mode):
    man = json.loads(open(os.path.join(outdir, 'manifest.json')).read())
    ok('mode == %s' % mode, man['funding_mode'] == mode)
    ok('vault value', man['vault_value'] == FUNDING_VALUE - DEPOSIT_FEE)

    s_v, s_e = vt.build_scripts({
        'k1': bytes.fromhex(man['cfg']['k1_pubkey']),
        'k2': b'\x03' + bytes(range(33, 65)),
        'k3': b'\x02' + bytes(range(65, 97)),
        'n': man['cfg']['n']})
    spk_v, spk_e = vp.p2wsh_spk(s_v), vp.p2wsh_spk(s_e)
    ok('cfg sv_hash/spk_e match scripts',
       man['cfg']['sv_hash'] == spk_v.hex() and
       man['cfg']['spk_e'] == spk_e.hex())

    # deposit: single output paying S_v at the vault value
    dep = vt.parse_psbt(open(os.path.join(outdir, 'deposit.psbt'), 'rb').read())
    _, _, outs, _ = vt.parse_tx(dep['tx'])
    ok('deposit pays S_v', len(outs) == 1 and outs[0] == (
        spk_v, FUNDING_VALUE - DEPOSIT_FEE))
    ok('deposit keeps funding input maps', len(dep['in_maps']) == 1
       and dep['in_maps'][0][-1:] == b'\x00')

    # leaves: spend deposit txid vout 0, S_v witness utxo, fee ladder
    dep_txid = vt.txid_of(dep['tx'])
    fees = []
    for i, f in enumerate(man['files']):
        p = vt.parse_psbt(open(os.path.join(outdir, f), 'rb').read())
        _, ins, outs, lt = vt.parse_tx(p['tx'])
        ok('%s shape' % f,
           len(ins) == 1 and ins[0][0] == dep_txid and ins[0][1] == 0
           and ins[0][2] == vp.SEQ_EMERGENCY and lt == 0
           and len(outs) == 1 and outs[0][0] == spk_e)
        ok('%s witness utxo' % f,
           len(p['wutxos']) == 1 and p['wutxos'][0] == (
               spk_v, FUNDING_VALUE - DEPOSIT_FEE))
        fees.append((FUNDING_VALUE - DEPOSIT_FEE) - outs[0][1])
    ok('fee ladder 500..552', fees == [500 + 13 * i for i in range(5)])

    # independent root: re-derive from the FILES, not the manifest
    leaves = [vp.leaf_hash(i, vt.parse_psbt(open(
        os.path.join(outdir, f), 'rb').read())['tx'])
        for i, f in enumerate(man['files'])]
    root, count = vp.lattice_root(iter(leaves))
    ok('root matches independent re-derive',
       root.hex() == man['lattice_root'] and count == man['lattice_count'])
    return man

def main():
    tmp = tempfile.mkdtemp(prefix='vault-hostapp-')
    try:
        policy = make_policy(tmp)
        s_v, _ = vt.build_scripts({
            'k1': b'\x02' + bytes(range(1, 33)),
            'k2': b'\x03' + bytes(range(33, 65)),
            'k3': b'\x02' + bytes(range(65, 97)), 'n': 1008})
        spk_v = vp.p2wsh_spk(s_v)

        for kind, mode in (('input-only', 'input-only'),
                           ('incorrect', 'incorrect-output'),
                           ('correct', 'already-correct')):
            fund = make_funding(tmp, kind, spk_v, 'fund-' + kind)
            outdir = os.path.join(tmp, 'tree-' + kind)
            r = run_app(policy, fund, outdir)
            ok('app run (%s)' % kind, r.returncode == 0)
            if r.returncode != 0:
                continue
            man = check_tree(outdir, mode)
            if kind == 'input-only':
                # keep for the device-driver run (see docs/vault_progress.md)
                shutil.copytree(outdir, os.path.join(HERE, '..', 'unix',
                                                     'work', 'app-tree'),
                                dirs_exist_ok=True)
                print('  (app tree copied to unix/work/app-tree for the '
                      'device run)')
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    n = sum(1 for _, c in R if c)
    print('VAULT HOSTAPP: %d/%d checks pass' % (n, len(R)))
    if n != len(R):
        sys.exit(1)

if __name__ == '__main__':
    main()
