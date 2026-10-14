# Vault co-signing - working status (2026-10-13)

Branch: vault-cosign-policy (base f28e1b2)

## What exists
- docs/vault_signing_gameplan.md - gameplan (hook points, P1-P3/INV-SEQ rules, design, commit plan)
- shared/vault_policy.py - pure stdlib decision module (S_v/S_e structural parsers, sequence classes, P1/P2/P3 checks)
- testing/test_vault_policy.py - CPython host test suite

## Test state right now
HOST TESTS FAILING

## Honest debt
- Commit 3975301 claimed "all 45 checks passing" while P3 was failing - false message, superseded here.
- ccc.py: NO signing-hook adapter yet (view build + VaultPolicy.check call in SpendingPolicy.meets_policy) - pending.
- Minimal vault-deposit menu UI (user requested) NOT implemented yet.
- MicroPython/device run untested; everything host-side only.

## Next steps
1. Wire ccc.py hook: build {'lock_time','inputs','outputs'} view from psbt.PSBT, call VaultPolicy.check, raise SpendPolicyViolation on VaultViolation, fail-closed on missing UTXO data.
2. Minimal test-only Vault menu (Cadence N, Max fee F) - no warnings.
3. Simulator + pytest integration run.
