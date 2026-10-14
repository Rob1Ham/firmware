# Host-runnable tests for shared/vault.py
# Run: python3 testing/test_vault.py     (no device, no pytest required)
import sys, os, types, tempfile, atexit, shutil

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'shared'))

# fake the glob/settings module before vault.py touches it
# NOTE: a plain dict whose KEY is 'get' still exposes dict.get (keys are not
# attributes on builtins) — so the shim must be a real object with a method.
_store = {'vault': None}

class _FakeSettings:
    def get(self, k, d=None):
        return _store.get(k, d)

glob_mod = types.ModuleType('glob')
glob_mod.settings = _FakeSettings()
sys.modules['glob'] = glob_mod

import vault
import vault_policy as vp

R = []
def ok(name, cond): R.append((name, bool(cond)))

os.chdir(tempfile.mkdtemp(prefix='vlog-'))   # ledger goes to a scratch dir
atexit.register(shutil.rmtree, os.getcwd(), True)

# --- fixtures: S_v-shaped vault spk, arbitrary distinct sink/warm/exit spks ----
K1 = b'\x02' + b'\x01' * 32
K2 = b'\x02' + b'\x02' * 32
K3 = b'\x02' + b'\x03' * 32
N = 1008

def pd(k): return bytes([len(k)]) + k
WS_V = b'\x63\x02\xf0\x03\xb2\x75\x67\x68\x52' + pd(K1) + pd(K2) + pd(K3) + b'\x53\xae'
SPK_V = vp.p2wsh_spk(WS_V)
SPK_E = vp.p2wsh_spk(b'\x51')            # stands in for the deepvault sink spk
EXIT_SPK = vp.p2wsh_spk(b'\x52')
WARM_SPK = vp.p2wsh_spk(b'\x53')

CFG = dict(n=N, sv_hash=SPK_V.hex(), spk_e=SPK_E.hex(),
           k1_pubkey=K1.hex(), f0_max=10000, exit_spk=EXIT_SPK.hex())

class UTXO:
    def __init__(s, spk, val): s.scriptPubKey, s.nValue = spk, val
class Inp:
    def __init__(s, spk, val, seq, part=None):
        s.utxo = UTXO(spk, val); s.sequence = seq; s.part_sigs = part or []
class Out:
    def __init__(s, spk, val): s.scriptPubKey, s.nValue = spk, val
class P:
    def __init__(s, ins, outs, lt=0): s.inputs, s.outputs, s.lock_time = ins, outs, lt

def enable(cfg): _store['vault'] = cfg
def p_emg(fee=500, seq=0xfffffffd): return P([Inp(SPK_V, 10_000 + fee, seq)], [Out(SPK_E, 10_000)])
def p_other(): return P([Inp(WARM_SPK, 5000, 0xfffffffd)], [Out(WARM_SPK, 4500)])

# --- 1 feature flag -------------------------------------------------------------
enable(None);            ok('flag off', not vault.is_enabled())
enable(dict(CFG, enabled=1)); ok('flag on', vault.is_enabled())
enable(dict(CFG, enabled=0)); ok('flag off again', not vault.is_enabled())

# --- 2 relevance -----------------------------------------------------------------
enable(dict(CFG, enabled=1))
ok('relevant vault in', vault.check_relevance(p_emg(), CFG))
ok('irrelevant', not vault.check_relevance(p_other(), CFG))

# --- 3 auto-approve a canonical emergency -----------------------------------------
appr, msg = vault.VaultMode.could_sign(p_emg())
ok('approve emergency', appr)
ok('class named', 'emergency' in msg.lower())

# --- 4 refuse a ladder spend with wrong cadence N-10 ------------------------------
bad = P([Inp(SPK_V, 12000, N - 10)], [Out(WARM_SPK, 11000)])
appr, msg = vault.VaultMode.could_sign(bad)
ok('refuse wrong-N ladder', not appr)
ok('reason mentions seq', 'seq' in msg.lower())

# --- 4b refuse sink entry that is not the emergency class (INV-SINK) --------------
sinky = P([Inp(SPK_V, 12000, N)], [Out(SPK_E, 11000)])
appr, msg = vault.VaultMode.could_sign(sinky)
ok('refuse ladder sink entry', not appr)

# --- 5 strict mode -----------------------------------------------------------------
enable(dict(CFG, enabled=1, strict=1))
appr, msg = vault.VaultMode.could_sign(p_other())
ok('strict refuses non-vault', not appr)
ok('strict reason', 'strict' in msg.lower())
enable(dict(CFG, enabled=1))
appr, msg = vault.VaultMode.could_sign(p_other())
ok('non-strict passes non-vault', appr)

# --- 6 fail-closed view builder ------------------------------------------------------
class BareInp:
    part_sigs = []; sequence = 0xfffffffd          # no .utxo at all
class P2:
    inputs = [BareInp()]; outputs = [Out(WARM_SPK, 1)]; lock_time = 0
appr, msg = vault.could_sign(CFG, P2())
ok('missing utxo refuses', not appr)
ok('reason missing utxo', 'witness_utxo' in msg)

# --- 7 vault_log append ----------------------------------------------------------------
vault.vault_log('TEST1'); vault.vault_log('TEST2')
lines = open('vault.log').read().splitlines()
ok('log has entries', len(lines) >= 2)   # earlier could_sign calls also log
ok('log content', any('TEST1' in l for l in lines) and any('TEST2' in l for l in lines))

fails = [n for n, c in R if not c]
print('VAULT GLUE: %d/%d checks pass' % (len(R) - len(fails), len(R)))
for n in fails: print('    FAIL: %s' % n)
sys.exit(1 if fails else 0)
