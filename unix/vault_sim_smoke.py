# Device-context smoke test for the vault co-signer work.
#
# Runs INSIDE the coldcard-mpy simulator binary (micropython), with the
# real nvstore settings object - exercising vault.py / vault_policy.py on
# the actual device path (uhashlib, ubinascii, NVS round-trip).
#
# Run from unix/work:
#   MICROPYPATH=:../shared ../coldcard-mpy ../vault_sim_smoke.py
#
# Expected root below was computed independently on CPython host:
#   leaves: leaf_hash(i, bytes([i])*(60+i)) for i in 0..4
#   750024e529e68a0e2bb6abe0e6b58aab3e327573d1ca1ba193ff942924a993e9

import sys

# mimic sim_boot.py's nvstore setup (without the socket / main boot)
import nvstore
from sim_settings import sim_defaults
nvstore.SettingsObject.default_values = lambda _: dict(sim_defaults)
nvstore.MK4_WORKDIR = './settings/'
nvstore.SettingsObject._deny_slot = lambda *a: None

import glob
s = nvstore.SettingsObject()
s.load()
glob.settings = s

# start clean: a previous crashed run may have left a stale 'vault' key
if s.get('vault', None):
    s.remove_key('vault')
    s.save()

import vault, vault_policy as vp
from ubinascii import hexlify

def b2h(b):
    return str(hexlify(b), 'ascii')

R = []
def ok(name, cond):
    R.append((name, bool(cond)))
    if not cond:
        print('    FAIL: %s' % name)

# --- settings + enable lifecycle on the REAL nvstore --------------------
ok('vault disabled by default', not vault.is_enabled())
res, msg = vault.set_enabled(True)
ok('enable refused when empty', (not res) and 'no policy' in msg)

K1 = b'\x02' + b'\x01' * 32
SPK_V = vp.p2wsh_spk(b'\x51')
SPK_E = vp.p2wsh_spk(b'\x52')
EXIT_SPK = vp.p2wsh_spk(b'\x53')
N = 1008
CFG = dict(n=N, sv_hash=b2h(SPK_V), spk_e=b2h(SPK_E),
           k1_pubkey=b2h(K1), f0_max=10000, exit_spk=b2h(EXIT_SPK))

vault.save_cfg(dict(CFG))
ok('enrolled dark', not vault.is_enabled())
res, msg = vault.set_enabled(True)
ok('enable works', res and vault.is_enabled())

# force a synchronous NVS write, then re-load from disk into a fresh object
s.save()
s2 = nvstore.SettingsObject()
s2.load()
ok('nvs round-trip', s2.get('vault', {}).get('enabled') == 1)
ok('nvs fields kept', s2.get('vault', {}).get('sv_hash') == b2h(SPK_V))

# --- relevance + policy on the mpy runtime ------------------------------
class UTXO:
    def __init__(self, spk, val):
        self.scriptPubKey, self.nValue = spk, val
class Inp:
    def __init__(self, spk, val, seq, part=None):
        self.utxo = UTXO(spk, val); self.sequence = seq
        self.part_sigs = part or []
class Out:
    def __init__(self, spk, val):
        self.scriptPubKey, self.nValue = spk, val
class P:
    def __init__(self, ins, outs, lt=0, txn=b''):
        self.inputs, self.outputs, self.lock_time, self.txn = ins, outs, lt, txn

def p_emg(fee=500, txn=b''):
    return P([Inp(SPK_V, 10000 + fee, vp.SEQ_EMERGENCY)],
             [Out(SPK_E, 10000)], txn=txn)

appr, msg = vault.VaultMode.could_sign(p_emg())
ok('approve emergency (mpy)', appr and 'emergency' in msg.lower())

bad = P([Inp(SPK_V, 12000, N - 10)], [Out(vp.p2wsh_spk(b'\x54'), 11000)])
appr, msg = vault.VaultMode.could_sign(bad)
ok('refuse wrong-N ladder (mpy)', not appr)

# --- lattice commitment on the mpy runtime ------------------------------
members = [p_emg(txn=bytes([i]) * (60 + i)) for i in range(5)]
root_hex, cnt = vault.enroll_lattice(CFG, members)
ok('lattice count (mpy)', cnt == 5)
ok('lattice known-answer root', root_hex ==
   '750024e529e68a0e2bb6abe0e6b58aab3e327573d1ca1ba193ff942924a993e9')

vault.store_lattice(root_hex, cnt)
ok('lattice stored', vault._cfg().get('lattice_count') == 5)

# --- ledger ----------------------------------------------------------------
vault.vault_log('SIM-SMOKE')
try:
    lines = open('vault.log').read().splitlines()
except Exception:
    lines = []
ok('vault.log written', any('SIM-SMOKE' in l for l in lines))

# --- vault_menu import (device modules present, no display driving) -------
try:
    import vault_menu
    m = vault_menu.VaultConfigMenu()
    labels = [i.label for i in m.items]
    ok('menu constructs', ('[OFF] Vault Mode' in labels or '[ON] Vault Mode' in labels)
       and 'Enroll Lattice' in labels)
except Exception as e:
    ok('menu constructs', False)
    print('    menu error: %s' % e)

# --- cleanup: leave the simulator settings clean ---------------------------
vault.wipe()
s.save()
ok('wiped', not vault._cfg())

fails = [n for n, c in R if not c]
print('VAULT SIM SMOKE: %d/%d checks pass' % (len(R) - len(fails), len(R)))
for n in fails:
    print('    FAIL: %s' % n)
sys.exit(1 if fails else 0)
