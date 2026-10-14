# Verification script for the vault-branch bugs (run from the repo root).
# Originally written as bug REPROs; conditions now assert the FIXES.
import os, sys, json, hashlib, struct, tempfile, subprocess, traceback

HERE = os.path.abspath(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, 'hostapp'))
sys.path.append(os.path.join(HERE, 'shared'))
import vault_tree as vt
import vault_policy as vp

R = []
def ok(name, cond, extra=''):
    R.append((name, bool(cond)))
    print('%-6s %s %s' % ('FIXED' if cond else 'STILL', name, extra))

print('--- A: already-correct funding, vault output at vout 1 ---')
tmp = tempfile.mkdtemp(prefix='vr-a-')
pol = {'k1': (b'\x02' + bytes(range(1, 33))).hex(),
       'k2': (b'\x03' + bytes(range(33, 65))).hex(),
       'k3': (b'\x02' + bytes(range(65, 97))).hex(),
       'n': 1008, 'f0_max': 10000, 'leaves': 2,
       'emg_fee': 500, 'emg_step': 13, 'deposit_fee': 500}
open(os.path.join(tmp, 'policy.json'), 'w').write(json.dumps(pol))

s_v, s_e = vt.build_scripts({'k1': bytes.fromhex(pol['k1']),
                             'k2': bytes.fromhex(pol['k2']),
                             'k3': bytes.fromhex(pol['k3']), 'n': 1008})
spk_v = vp.p2wsh_spk(s_v)
other = vp.p2wsh_spk(b'\x51' + b'\x00' * 40)
FUND, FEE = 100000, 500

ins = [(hashlib.sha256(b'fund:A').digest(), 0, 0xFFFFFFFE)]
outs = [(other, 100), (spk_v, FUND - FEE)]
tx = vt.ser_tx(2, ins, outs, 0)
wu = vt.ct_out(vp.p2wsh_spk(b'\x61' * 30), FUND)
im = vt.vi(1) + b'\x01' + vt.vi(len(wu)) + wu + b'\x00'
open(os.path.join(tmp, 'funding.psbt'), 'wb').write(vt.build_psbt(tx, [im], len(outs)))

r = subprocess.run([sys.executable, os.path.join(HERE, 'hostapp', 'vault_tree.py'),
                    'build', os.path.join(tmp, 'policy.json'),
                    os.path.join(tmp, 'funding.psbt'),
                    os.path.join(tmp, 'out')], capture_output=True, text=True)
mode = 'already-correct' in r.stdout
ok('A1: funding classified already-correct', mode)
if mode:
    p = vt.parse_psbt(open(os.path.join(tmp, 'out', 'emg0.psbt'), 'rb').read())
    _, ins2, outs2, _ = vt.parse_tx(p['tx'])
    dep_txid = vt.txid_of(vt.parse_psbt(
        open(os.path.join(tmp, 'out', 'deposit.psbt'), 'rb').read())['tx'])
    ok('A2: leaf spends the vault vout (1), not vout 0',
       ins2[0][1] == 1 and ins2[0][0] == dep_txid,
       '(leaf vout=%d)' % ins2[0][1])

print('--- B: hostapp build_scripts for N=200 (and N=40000) ---')
for n in (200, 40000):
    try:
        s_v, _ = vt.build_scripts({'k1': bytes.fromhex(pol['k1']),
                                   'k2': bytes.fromhex(pol['k2']),
                                   'k3': bytes.fromhex(pol['k3']), 'n': n})
        ok('B: build_scripts(N=%d) parses' % n,
           vp.parse_vault_script(s_v)['n'] == n)
    except SystemExit as e:
        ok('B: build_scripts(N=%d)' % n, False, '(SystemExit %s)' % e)
    except Exception as e:
        ok('B: build_scripts(N=%d) crashes' % n, False, '(%s: %s)' % (type(e).__name__, e))

print('--- C: unknown 0x01-prefixed input-map key ignored ---')
ins = [(hashlib.sha256(b'fund:C').digest(), 0, 0xFFFFFFFE)]
tx = vt.ser_tx(2, ins, [], 0)
wu = vt.ct_out(vp.p2wsh_spk(b'\x61' * 30), 100000)
im = vt.vi(1) + b'\x01' + vt.vi(len(wu)) + wu
bogus = vt.ct_out(b'\x21' * 34, 1000000)
im += vt.vi(3) + b'\x01\x66\x00' + vt.vi(len(bogus)) + bogus
im += b'\x00'
open(os.path.join(tmp, 'fund_c.psbt'), 'wb').write(vt.build_psbt(tx, [im], 0))
ps = vt.parse_psbt(open(os.path.join(tmp, 'fund_c.psbt'), 'rb').read())
tot = sum(v for _, v in ps['wutxos'])
ok('C: unknown 01-key not counted as witness utxo', tot == 100000,
   '(total_in=%d, wutxos=%d)' % (tot, len(ps['wutxos'])))

print('--- F: exit_spk == spk_e rejected at validation ---')
spk_e = vp.p2wsh_spk(b'\x52')
cfg = dict(n=1008, sv_hash=spk_v.hex(), spk_e=spk_e.hex(),
           k1_pubkey=pol['k1'], f0_max=10000, exit_spk=spk_e.hex())
sys.path.insert(0, os.path.join(HERE, 'shared'))
import vault as vmod
res, msg = vmod.validate_cfg(cfg)
ok('F: validate_cfg rejects exit_spk == spk_e', not res, '(%s)' % msg)

print('--- E: check_relevance(psbt, None) safe ---')
class U:
    def __init__(s, spk, val): s.scriptPubKey, s.nValue = spk, val
class I2:
    def __init__(s): s.utxo = U(b'\x00\x20' + b'\x01' * 32, 1); s.part_sigs = []
class P2:
    inputs = [I2()]; outputs = []; lock_time = 0
try:
    rel = vmod.check_relevance(P2(), None)
    ok('E: check_relevance(None cfg) returns (no crash)', rel is False)
except Exception as e:
    ok('E: check_relevance(psbt, None) uncaught %s' % type(e).__name__, False)

print()
n = sum(1 for _, c in R if c)
print('VERIFICATION SUMMARY: %d/%d fixed' % (n, len(R)))
for n, c in R:
    print('  %s %s' % ('FIXED' if c else 'STILL-BROKEN', n))
