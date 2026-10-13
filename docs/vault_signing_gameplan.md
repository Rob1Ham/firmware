# Vault Co-Signer (CCC) — Signing-Logic Implementation Gameplan

Spec source: `Valve/valve-flow/docs/REV3_PROTOCOL_DRAFT.md` (branched P2WSH vault `S_v`
+ emergency deepvault `S_e`). This plan covers **only signing-time policy enforcement**
as an extension of the existing Coldcard co-signer feature (`ccc.py`, "CCC"). No UI/menu
work — every rule below is enforced inside the sign/no-sign decision path.

## 0. Where the device already decides (recon results)

| what | file:lines | notes |
|---|---|---|
| Co-sign decision | `shared/ccc.py:228-352` `CCCFeature` | `could_cosign(psbt)` → `pol.meets_policy(psbt)`; raises `SpendPolicyViolation`; then `sign_psbt()` signs. |
| Policy storage | `shared/ccc.py:46` `SpendingPolicy(dict)` | NVS-backed dict: `vel`, `block_h`, `addrs` (whitelist, ≤25), `web2fa`, `mag`. Change-exemption at the whitelist loop. |
| Signing-time hook | `shared/auth.py:~445` | `CCCFeature.could_cosign(self.psbt)` after `consider_inputs()/consider_outputs()`, before user approval. |
| PSBT facts available | `shared/psbt.py` | per input: `witness_utxo/utxo.scriptPubKey`, `sequence`, `part_sigs` (pubkey→sig); global: `num_inputs`, `lock_time`, `output_iter()` → `CTxOut(nValue, scriptPubKey)`; `total_value_out`, `total_change_value`. |
| Bare-multisig limits | `shared/multisig.py:25-51` | `disassemble_multisig*` asserts a *bare* `OP_CHECKMULTISIG` script — the branched `S_v` (113 B) fails these by design. |

Key architectural fact: the enforcement point is per-PSBT (each batch item arrives as its
own PSBT), *after* input UTXO metadata is available, *before* any signature is produced.

## 1. Rules to enforce (E-CORE, formalized in whitepaper §5.5)

Let `spk_e` = deepvault scriptPubKey (hex), `S_v` = vault witness script, `K1` = device-A
key, `N` = vault cadence blocks.

- **P1 (positive, emergency shape)** — sign iff exactly: 1 input; 1 output paying `spk_e`;
  `out == in − F`, `0 < F ≤ F_MAX`; every input `nSequence == 0xFFFFFFFD` (CSV-disabled,
  RBF); `nLockTime == 0`.
- **P2 (negative, spend-forbid)** — never sign any PSBT with an input whose
  `scriptPubKey == spk_e`, unless the P3 exception applies.
- **P3 (sole exception, exit ceremony)** — a `spk_e`-spending PSBT is signable iff it
  re-enrolls **all** value to a fresh `spk_v'` (1-in/1-out of the sink UTXO) **and** the
  PSBT already carries K1's partial signature (belt-and-braces; E-2 also enforces K1 at
  script level).
- **INV-SEQ (sequence discipline, §5.3)** — on `S_v` inputs with CSV enabled
  (`nSequence` of height form), the committed value must equal `N` (the cadence), i.e.
  only the timelocked branch is signable for ladder spending; `0xFFFFFFFD` is reserved
  for the emergency class.
- **INV-KEYLESS (template)** — `S_v` must be exactly
  `OP_IF <N> OP_CSV OP_DROP OP_ELSE OP_ENDIF 2-of-3` (the D-1′ fix): both branches end
  in the shared `OP_CHECKMULTISIG`, so no selector-only/keyless spend exists. The
  template is validated structurally (by parsing, not by trusting a hash alone).
- **E-2 sink template** — `S_e` = `<K1> OP_CHECKSIGVERIFY OP_1 <K2> <K3> OP_2
  OP_CHECKMULTISIG` (106 B), enforced when the sink is created/enrolled.

## 2. Design: one pure module + one thin hook

- New **`shared/vault_policy.py`** — import-free (stdlib only), MicroPython-safe, so the
  decision core is host-testable. Exposes:
  - `parse_vault_script(script) -> {n, keys}` — structural INV-BRANCH/INV-KEYLESS parse.
  - `parse_deepvault_script(script) -> {keys, k1}` — E-2 structural parse.
  - `decode_sequence(seq) -> 'csv' | 'emergency' | 'disabled'` — BIP-68 flag decode.
  - `class VaultViolation(Exception)` — module-local error type.
  - `class VaultPolicy` — holds `n`, `sv_hash`, `spk_e`, `k1_pubkey`, `f0_max`,
    `exit_dest`; methods `check_withdrawal(view)`, `check_emergency(view)`,
    `check_exit(view)`; each raising `VaultViolation`.
- **`shared/ccc.py`** gains a `check_vault()` step called at the end of
  `SpendingPolicy.meets_policy()` when the policy dict contains a `'vault'` entry. It
  builds a duck-typed *view* of the PSBT (using only the documented psbt.py fields),
  catches `VaultViolation` and re-raises `SpendPolicyViolation` so the existing
  failure/warning plumbing in `auth.py` keeps working unchanged.
- Policy dict extension (stored via existing NVS write-thru): `pol['vault'] = {
  'n': ..., 'sv_hash': hex, 'spk_e': hex, 'k1': hex, 'f0_max': int, 'exit_dest': hex }`.

## 3. Commit sequence

1. `docs: add vault co-signer signing-logic gameplan` — this file.
2. `feat(vault): pure vault-policy decision module (P1–P3, sequence classes)` —
   `shared/vault_policy.py`.
3. `feat(vault): structural parse of branched vault and deepvault scripts` —
   template validators + INV-KEYLESS structural assertions (same module; separate
   commit only if split, else folded into 2).
4. `test(vault): host unit tests for vault policy engine` — `testing/test_vault_policy.py`,
   runs under plain python3/pytest without a device.
5. `feat(ccc): hook vault policy into co-signing enforcement` — `shared/ccc.py`
   integration + `SpendPolicyViolation` mapping.
6. `docs(vault): record session progress and residual risks` — progress log.

## 4. Explicitly out of scope (per instruction)

Menus, setup/UX flows (`PolicyConfigMenu*`, `SPAddrWhitelist`), enrollment ceremony
protocols, QR/PSBT transport changes, simulator UX tests. The policy object is designed
so those can be added later without re-touching the decision core.

## 5. Residual risks / notes

- Non-segwit or missing-UTXO inputs can't yield `scriptPubKey` — the view treats a
  missing UTXO as a policy failure (fail-closed) for sink rules.
- CCC's fatal-warnings mode already rejects weird locktime shapes; INV-SEQ adds the
  per-class positive check so a *correct-looking* but wrong-N sequence is refused, not
  merely warned.
- `update_last_signed()` height-ratchet stays height-form only; emergency signatures
  (`0xFFFFFFFD`, locktime 0) must not ratchet — enforced by ratchet guard in hook.
