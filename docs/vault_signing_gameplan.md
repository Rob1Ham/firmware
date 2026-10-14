# Gameplan — Vault Signin
g Logic (CCC Co-Signer Extension)

Source spec: valve-flow `docs/REV3_PROTOCOL_DRAFT.md`. Scope: signing-logic
enforcement only (no UX), delivered as a host-testable pure module plus a
thin firmware hook. See `vault_device_mode_gameplan.md` for the device-mode
integration plan and `vault_lattice_commitment_plan.md` for the (tentative)
enrollment-time Merkle commitment.

## Verified hook recon (this checkout, base f28e1b2)

- `shared/ccc.py` (1288 lines): `SpendingPolicy` NVS dict
  (`vel/block_h/addrs/web2fa/mag`), `meets_policy` ~L80, velocity ratchet
  L100-116 (height-only, ratchets `block_h`), whitelist L118-136
  (`MAX_WHITELIST=25` L26), `CCCFeature.could_cosign` L313-343,
  `CCCFeature.sign_psbt` L345-352.
- `shared/auth.py`: CCC import L373, `CCCFeature.could_cosign(self.psbt)`
  L445-447 (after `consider_inputs` L431), web2fa L588, `CCCFeature.sign_psbt`
  L629.
- `shared/psbt.py`: per-input `witness_utxo`/`.utxo.scriptPubKey`,
  `PSBT_IN_SEQUENCE` parse L1011, `part_sigs` dict L614, `output_iter()`
  L1205, `input_iter` L1285, `lock_time` L1143.
- `shared/multisig.py` L31-51: bare OP_CHECKMULTISIG only — branched S_v
  intentionally fails stock multisig parsing; vault spends must be
  recognized structurally (template parse), never via the multisig path.

## Rules enforced by `shared/vault_policy.py` (`VaultPolicy(d).check(view)`)

- **P1** emergency: 1-in(`spk_v`)/1-out to pinned `spk_e`,
  `0 < fee <= f0_max`, all `nSequence == 0xFFFFFFFD`, `nLockTime == 0`.
- **P2** spend-forbid: never sign a spend OF `spk_e`.
- **P3** sole exception: exit ceremony 1-in(`spk_e`)/1-out to pinned
  `exit_spk`, fee window, K1 partial sig present in PSBT.
- **INV-SEQ**: ladder class commits `nSequence == N` (height-form CSV only;
  time-form refused — REV3 §7a); all vault classes commit `nLockTime == 0`.
- **INV-SINK**: any tx paying an output to `spk_e` must classify as
  emergency (ladder-shaped sink entry refused).
- **INV-KEYLESS / INV-BRANCH**: `parse_vault_script` — OP_IF/`<N>`/CSV/
  DROP/empty-ELSE/ENDIF/OP_2/<K1..K3>/OP_3/OP_CMS (113 B). 
  `parse_deepvault_script` — E-2 (106 B), K1 CSV_VER + 1-of-{K2,K3}.

Policy dict (NVS-serializable): `n, sv_hash` (hex spk), `spk_e` (hex),
`k1_pubkey` (hex), `f0_max` (sats), `exit_spk` (hex).

View (duck-typed, built from live PSBT): `{lock_time, inputs:[{spk, value,
sequence, part_sigs}], outputs:[{spk, value}]}`. Non-washers: fail closed
(missing witness_utxo/amount/sequence => refuse).

## Firmware hook (per device-mode gameplan, Option 2 + delegation)

- `shared/vault.py` `VaultFeature` mirrors `CCCFeature`; hooked in auth.py
  next to `could_cosign` (build view; refuse or auto-sign).
- Belt-and-suspenders: `SpendingPolicy.meets_policy` delegates when
  `pol["vault"]` present; skip CCC velocity ratchet for vault txs
  (nLockTime==0).

## Host tests

`testing/test_vault_policy.py` — stdlib-only, runs `python3
testing/test_vault_policy.py`; 7 tests / 45 checks covering sequence
labels, S_v parse (+5 rejections incl. Rev2 keyless shape), E-2 parse,
P1 (good + 7 rejections), ladder sequences, P2, P3.

## Out of scope here

Menus/UX, lattice implementation, SSSP, P2TR, simulator wiring.
