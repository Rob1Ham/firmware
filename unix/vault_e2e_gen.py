#!/usr/bin/env python3
# (c) Copyright 2026 for the vault co-sign policy work; license per COPYING-CC.
#
# unix/vault_e2e_gen.py - host-side generator for the simulator end-to-end run.
#
# Builds REAL binary PSBT files (BIP-174 v0, witness-utxo form) covering every
# vault policy class, plus expected.json (the lattice root, computed here via
# the same pure vault_policy module, and per-file expected gate outcomes).
# The device-side driver (unix/vault_sim_e2e.py) parses these files with the
# real firmware psbtObject and runs the full vault flow against them.
#
# Run:  python3 unix/vault_e2e_gen.py [outdir]
#       (default outdir: unix/work/sim-e2e)

import os, sys, json, hashlib, struct

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'shared'))
import vault_policy as vp

# ---- the enrolled policy (mirrors what the device enrolls) ----------------
K1 = b'\x02' + bytes(range(1, 33))    # 33-byte compressed pubkeys
K2 = b'\x03' + bytes(range(33, 65))
K3 = b'\x02' + bytes(range(65, 97))
N = 1008
F0_MAX = 10000

def push(b):
    return bytes([len(b)]) + b


# S_e (E-2): <K1> OP_CHECKSIGVERIFY OP_1 <K2> <K3> OP_2 OP_CMS - 106 bytes
S_E = (push(K1) + bytes([vp.OP_CHECKSIGVERIFY, 0x51]) + push(K2) + push(K3) +
       bytes([0x52, vp.OP_CMS]))
assert len(S_E) == 106
vp.parse_deepvault_script(S_E)          # structural self-check

# S_v (D-1'): OP_IF <N> OP_CSV OP_DROP OP_ELSE OP_ENDIF OP_2 K1 K2 K3 OP_3 CMS
N_PUSH = bytes([2, N & 0xff, (N >> 8) & 0xff])
S_V = (bytes([vp.OP_IF]) + N_PUSH +
       bytes([vp.OP_CSV, vp.OP_DROP, vp.OP_ELSE, vp.OP_ENDIF, 0x52]) +
       push(K1) + push(K2) + push(K3) + bytes([0x53, vp.OP_CMS]))
assert 111 <= len(S_V) <= 140
vp.parse_vault_script(S_V)

SPK_V = vp.p2wsh_spk(S_V)
SPK_E = vp.p2wsh_spk(S_E)
EXIT_SPK = vp.p2wsh_spk(bytes([0x51]) + K1 + K2 + K3 + bytes([vp.OP_CMS]))
OTHER_SPK = vp.p2wsh_spk(b'\x51' + b'\x00' * 40)   # unrelated destination


def vi(n):
    # bitcoin compact size
    if n < 253:
        return bytes([n])
    if n < 0x10000:
        return b'\xfd' + struct.pack('<H', n)
    assert n < 0x100000000
    return b'\xfe' + struct.pack('<I', n)


def build_tx(prevouts, seqs, outs, lock_time=0, version=2):
    # Legacy (no witness marker) unsigned-tx serialization.
    assert len(prevouts) == len(seqs)
    r = struct.pack('<i', version)
    r += vi(len(prevouts))
    for i, (txid, n) in enumerate(prevouts):
        r += txid + struct.pack('<I', n) + vi(0) + struct.pack('<I', seqs[i])
    r += vi(len(outs))
    for (spk, value) in outs:
        r += struct.pack('<q', value) + vi(len(spk)) + spk
    r += struct.pack('<I', lock_time)
    return r


def ct_out(spk, value):
    return struct.pack('<q', value) + vi(len(spk)) + spk


def build_psbt(tx_bytes, num_outputs, witness_utxos=(), partial_sigs=()):
    # BIP-174 v0: globals(UNSIGNED_TX) + per-input maps + per-output maps.
    assert witness_utxos or partial_sigs  # every input map must be non-empty
    r = b'psbt\xff'
    r += vi(1) + b'\x00' + vi(len(tx_bytes)) + tx_bytes
    r += b'\x00'                              # end of globals
    for i, wu in enumerate(witness_utxos):
        assert wu is not None, 'input %d has no map data' % i
        r += vi(1) + b'\x01' + vi(len(wu)) + wu
        for pk, sig in partial_sigs.get(i, ()):
            r += vi(1 + len(pk)) + b'\x02' + pk + vi(len(sig)) + sig
        r += b'\x00'                          # end of this input map
    for o in range(num_outputs):
        r += b'\x00'                          # empty output map
    return r


def mk(prevout_seed, utxo_spk, utxo_val, seq, outs, lock_time=0,
       partial_sigs=None):
    # one-input PSBT: prevout hash from seed, witness utxo = (spk, val)
    txid = hashlib.sha256(b'e2e:%d' % prevout_seed).digest()
    tx = build_tx([(txid, 0)], [seq], outs, lock_time=lock_time)
    wu = ct_out(utxo_spk, utxo_val)
    return build_psbt(tx, len(outs), witness_utxos=[wu],
                      partial_sigs=partial_sigs or {})


EMG = vp.SEQ_EMERGENCY
FAKE_SIG = b'\x30' + b'\x45' + b'\x01' * 70   # 72-byte DER-ish; content unused

def main(outdir):
    os.makedirs(outdir, exist_ok=True)
    files = {}

    # lattice members: 5 compliant emergency exits (P1), distinct fees/prevouts
    for i in range(5):
        fee = 500 + 13 * i
        files['emg%d.psbt' % i] = mk(
            1000 + i, SPK_V, 10000 + fee, EMG, [(SPK_E, 10000)])

    # P3 exit ceremony: spends the sink, K1 partial sig present
    files['exit.psbt'] = mk(
        2000, SPK_E, 9000 + 600, EMG, [(EXIT_SPK, 9000)],
        partial_sigs={0: [(K1, FAKE_SIG)]})

    # INV-SEQ: correct-N ladder withdrawal (approved)
    files['ladder_ok.psbt'] = mk(
        3000, SPK_V, 50000, N, [(OTHER_SPK, 49000)])

    # INV-SEQ: wrong-N ladder (refused)
    files['ladder_bad.psbt'] = mk(
        3100, SPK_V, 50000, N - 10, [(OTHER_SPK, 49000)])

    # INV-SINK: ladder-shaped tx paying the sink (refused)
    files['sink_ladder.psbt'] = mk(
        3200, SPK_V, 50000, N, [(SPK_E, 49000)])

    # nLockTime != 0 on an otherwise-compliant emergency (refused)
    files['emg_lt.psbt'] = mk(
        3300, SPK_V, 10500, EMG, [(SPK_E, 10000)], lock_time=5)

    # non-vault spend (unrelated input): passes gate in non-strict mode
    files['novault.psbt'] = mk(
        4000, OTHER_SPK, 8000, 0xFFFFFFFE, [(OTHER_SPK, 7500)])

    for name, blob in files.items():
        with open(os.path.join(outdir, name), 'wb') as fd:
            fd.write(blob)

    # lattice root over the 5 emergency members - computed HERE, on the host,
    # from the exact raw unsigned-tx bytes inside the generated PSBTs
    leaves = []
    for i in range(5):
        blob = files['emg%d.psbt' % i]
        assert blob[:5] == b'psbt\xff'
        # locate UNSIGNED_TX (key 0x00) value in the globals map
        p = 5
        assert blob[p] == 1 and blob[p + 1] == 0      # keylen 1, key 0x00
        p += 2
        vlen = blob[p]
        tx = blob[p + 1:p + 1 + vlen]
        leaves.append(vp.leaf_hash(i, tx))
    root, count = vp.lattice_root(iter(leaves))

    cfg = {
        'n': N,
        'sv_hash': vp.p2wsh_spk(S_V).hex(),
        'spk_e': SPK_E.hex(),
        'k1_pubkey': K1.hex(),
        'f0_max': F0_MAX,
        'exit_spk': EXIT_SPK.hex(),
    }
    expect = [
        # (file, expect_approve, msg_substring, note)
        ('emg0.psbt',     True,  'emergency',      'P1 compliant emergency exit'),
        ('exit.psbt',     True,  'exit ceremony',  'P3 exit ceremony w/ K1 partial sig'),
        ('ladder_ok.psbt', True, 'ladder',         'INV-SEQ correct-N ladder'),
        ('ladder_bad.psbt', False, 'nSequence != N', 'wrong-N ladder refused'),
        ('sink_ladder.psbt', False, 'sink entry',  'INV-SINK refused'),
        ('emg_lt.psbt',   False, 'nLockTime == 0', 'locktime pin refused'),
        ('novault.psbt',  True,  'not vault-relevant', 'non-vault passes (non-strict)'),
    ]
    out = {
        'cfg': cfg,
        'lattice_root': root.hex(),
        'lattice_count': count,
        'expect': expect,
        'strict_expect': ['novault.psbt', False, 'strict'],
        'ccc_vel': [
            ['emg0.psbt', True,  'vault tx skips velocity ratchet'],
            ['novault.psbt', False, 'non-vault tx hit by velocity ratchet'],
        ],
    }
    with open(os.path.join(outdir, 'expected.json'), 'w') as fd:
        json.dump(out, fd, indent=1)

    print('wrote %d PSBTs + expected.json to %s' % (len(files), outdir))
    print('lattice root (host): %s count=%d' % (root.hex(), count))
    print('S_v len=%d S_e len=%d' % (len(S_V), len(S_E)))


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else
         os.path.join(HERE, 'work', 'sim-e2e'))
