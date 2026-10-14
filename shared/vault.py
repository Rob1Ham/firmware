# (c) Copyright 2026 for the vault co-sign policy work; license per COPYING-CC.
#
# shared/vault.py
#
# Glue between the vault policy core (shared/vault_policy.py) and the rest of
# the firmware. Per the gameplans this module intentionally holds ONLY:
#   - feature-on detection for vault mode (settings key 'vault')
#   - the relevance check over a candidate PSBT
#   - the spend-path view builder consumed by vault_policy.VaultPolicy
#   - the append-only vault signing ledger
#
# The rule layer stays in vault_policy.py; signature math stays in auth.py.
# This file gates reachability of the existing sign step and nothing more.
#
# Host-testable: python3 testing/test_vault.py
#
# pyright: reportMissingImports=false

from vault_policy import VaultPolicy, VaultViolation

VAULT_LOG = 'vault.log'


def _cfg():
    try:
        from glob import settings
        return settings.get('vault') or {}
    except Exception:
        return {}


def is_enabled():
    # Vault mode active iff operator enrolled a policy and flipped it on.
    try:
        return bool(_cfg().get('enabled'))
    except Exception:
        return False


def is_strict():
    # Dedicated-signer posture: refuse EVERY non-vault spend outright.
    try:
        return bool(_cfg().get('strict'))
    except Exception:
        return False


def _h2b(x):
    return bytes(bytearray.fromhex(x)) if x else None


def check_relevance(psbt, cfg):
    # A tx must pass policy iff any input spends the vault or the sink.
    spk_v, spk_e = _h2b(cfg.get('sv_hash')), _h2b(cfg.get('spk_e'))
    if not (spk_v or spk_e):
        return False
    try:
        for inp in psbt.inputs:
            u = getattr(inp, 'utxo', None)
            if u is None:
                continue
            if (spk_v and u.scriptPubKey == spk_v) \
                    or (spk_e and u.scriptPubKey == spk_e):
                return True
    except AttributeError:
        return True     # odd shape: treat as relevant, policy will judge
    return False


def view_from_psbt(psbt):
    # Build the policy view from a live PSBT. Fail-closed: raise
    # VaultViolation whenever a needed fact is uncollectable so the caller
    # refuses instead of approving on partial information.
    view = {'lock_time': getattr(psbt, 'lock_time', 0), 'inputs': [], 'outputs': []}
    for inp in psbt.inputs:
        u = getattr(inp, 'utxo', None)
        if u is None:
            raise VaultViolation('missing witness_utxo')
        part = getattr(inp, 'part_sigs', None)
        view['inputs'].append({
            'spk': bytes(u.scriptPubKey),
            'value': getattr(u, 'nValue', None),
            'sequence': getattr(inp, 'sequence', None),
            'part_sigs': list(part) if part else [],
        })
    for o in psbt.outputs:
        view['outputs'].append({
            'spk': bytes(o.scriptPubKey),
            'value': getattr(o, 'nValue', None),
        })
    return view


def could_sign(cfg, psbt):
    # Policy entry used by auth.py. Returns (approve, msg); never raises:
    # failures collapse to (False, reason).
    try:
        desc = VaultPolicy(cfg).check(view_from_psbt(psbt))
        return True, desc
    except VaultViolation as e:
        return False, str(e)
    except Exception as e:
        return False, 'vault policy error: %s' % (e,)


def vault_log(msg, logfile=VAULT_LOG):
    # Append-only ledger on internal flash. Never raises: logging must not be
    # able to break signing; a refusal is still surfaced via UX.
    try:
        try:
            y = str(__import__('utime').ticks_ms())
        except Exception:
            try:
                y = str(__import__('time').time())
            except Exception:
                y = '?'
        line = '[%s] %s\n' % (y, msg)
        try:
            with open(logfile, 'a') as fd:
                fd.write(line)
        except OSError:
            with open(logfile, 'w') as fd:
                fd.write(line)
    except Exception:
        pass


class VaultMode:
    # Marker/handle class, CCCFeature style, so auth.py call sites read like
    # the existing feature blocks. All methods class-level.

    @classmethod
    def is_enabled(cls):
        return is_enabled()

    @classmethod
    def could_sign(cls, psbt):
        # Full decision path for the signing choke point: relevance gate,
        # policy evaluation, strict-mode handling, ledger write.
        cfg = _cfg()
        if not check_relevance(psbt, cfg):
            if is_strict():
                vault_log('REFUSE non-vault spend (strict)')
                return False, 'strict vault signer refuses non-vault spend'
            return True, 'not vault-relevant'
        appr, msg = could_sign(cfg, psbt)
        if not appr:
            vault_log('REFUSE %s' % msg)
            return False, msg
        vault_log('APPR %s' % msg)
        return True, msg

# EOF
