# Gameplan — Vault Co-Signer Device Mode (Mk4/Q)

(Recreated 2026-10-14 after an earlier draft failed to persist; condensed.)

## Goal

New device mode parallel to CCC co-signer: when enabled, every PSBT sign
request whose inputs touch the vault spk (`spk_v`) or sink (`spk_e`) must
pass `shared/vault_policy.py` `VaultPolicy(policy).check(view)` before any
signature is emitted. Non-compliant => hard refuse (mirrors
`SpendPolicyViolation`). Signature math is never touched — the mode only
gates reachability of the existing sign step.

## Hook-point options evaluated

1. **Inside `SpendingPolicy.meets_policy` (ccc.py)** with cfg under
   `pol["vault"]`: reuses CCC NVS dict + enable + refuse path for free.
   Risk: CCC velocity/block_h ratchet misfires on vault txs (nLockTime==0).
   Use as thin delegation only (belt & suspenders), and skip ratchet for
   vault-classified txs.
2. **Standalone `shared/vault.py` `VaultFeature` mirroring
   `CCCFeature`/`SSSPFeature`** (own settings key, own toggle, called from
   auth.py adjacent to `CCCFeature.could_cosign` ~line 445-447, right
   after `consider_inputs` ~431 populated facts, before approval/sign at
   ~629-686). Clean separation, minimal blast radius. **RECOMMENDED.**
3. Multisig-wallet-attached — REJECTED: `multisig.py:31-51` cannot parse
   the branched S_v template, so vault PSBTs do not load on that path.

## Enforcement point (per-PSBT)

`VaultFeature.could_sign(psbt)` in auth.py at the CCC hook site:

- mode disabled => return immediately, zero interference with stock flow.
- relevance gate: no input spk matches cfg `spk_v`/`spk_e` => not a vault
  tx => pass through to normal user-confirm (settings flag
  `vault_strict` can flip this to refuse-everything = dedicated signer).
- vault-relevant => build view, `VaultPolicy(cfg).check(view)`:
  - pass => mark `psbt.vault_ok`, auto-sign without prompt (that IS the
    co-signer UX).
  - `VaultViolation` => refuse w/ on-screen reason; no partial sig.

## View construction (facts verified in psbt.py)

    view = {
      "lock_time": psbt.lock_time,
      "inputs":  [{"spk": i.witness_utxo.scriptPubKey, "value": i.amount,
                   "sequence": tx-vin-level nSequence see caveat C1,
                   "part_sigs": list(i.part_sigs) (33B SEC keys)} ...],
      "outputs": [{"spk": o.scriptPubKey, "value": o.nValue} ...],
    }

Fail-closed: witness_utxo/amount missing, sequence None, non-witness
legacy input touching cfg spks, lock_time unparseable, cfg scripts failing
template parse at use time => refuse.

## Policy storage (NVS)

settings key `"vault"` (StorableDict-style, mirrors SpendingPolicy):
`enabled, strict, sv_script, se_script, spk_v, spk_e, k1_pubkey, n,
f0_max, exit_spk, lattice_root, lattice_count`. Templates validated with
`parse_vault_script`/`parse_deepvault_script` BEFORE storing =
INV-KEYLESS/INV-BRANCH enforced at enrollment.

## Enrollment (incl. tentative lattice commitment)

scripts+params+full PSBT set in ONE enrollment session => template checks
=> per-PSBT shape check (full lattice validated at enrollment) =>
lattice root derived + displayed => user eyeball-confirms vs host =>
stable-marshal -> settings["vault"] See LATTICE PLAN doc for the root
commitment (tentative element).

## Menu (minimal, test-only; idiom: PolicyConfigMenuBase/CCCConfigMenu,
flow.py MenuSystem; chooser y/n/a)

"Vault Co-Signer" under Advanced/Tools: On/Off toggle (enable refused
until enrolled+cfg valid) / "Enroll vault (scripts + lattice)" (USB push)
/ Cadence N = <value> / Max fee = <value> / Exit destination spk = <hex>
/ "Show commitment root" / "Wipe policy" (full cfg clear). No scare
screens per directive; one-line confirms.

## Invariant mapping

INV-KEYLESS/INV-BRANCH: parse_vault_script rejects empty-ELSE/keyless
branch shapes at enrollment AND first use. INV-SEQ:
view.inputs[].sequence; ladder requires exactly n; emergency requires
0xFFFFFFFD; time-form CSV refused. INV-SINK: _check_emergency permits
only pinned spk_e output; sink-entry guard (~f2fd20f) rejects any output
paying spk_e unless the tx classifies emergency. INV-K1: P3 requires K1
partial sig in part_sigs. CHK-A: auto-sign only on vault_ok; else refuse.

## Landable commit sequence (each independent)

1. shared/vault.py skeleton + NVS cfg (dead code, reviewable alone).
2. auth.py hook + view builder + refuse/auto-sign (strict flag off).
3. ccc.py delegation to vault policy when pol["vault"] present; skip
   velocity ratchet for vault txs.
4. VaultPolicyConfigMenu minimal menu + enroll/show/wipe.
5. Savings: lattice commitment module funcs + enroll flow (see LATTICE
   PLAN), host tests, simulator run (testing/test_ccc.py idiom).

## Out of scope

i18n, scare-warning UX, SSSP integration, P2TR (whitepaper D-7),
Mk3 backport, enroll-transport hardening/attestation.
