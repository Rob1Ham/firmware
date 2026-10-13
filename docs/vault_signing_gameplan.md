# Vault Co-Signer (CCC) — Signing-Logic Implementation Gameplan

Spec: Valve/valve-flow/docs/REV3_PROTOCOL_DRAFT.md. Scope: signing-time policy only.
Hook: shared/ccc.py SpendingPolicy.meets_policy (via CCCFeature.could_cosign, auth.py).
Pure core: shared/vault_policy.py (stdlib-only) + testing/test_vault_policy.py host tests.

Rules: P1 emergency (1-in/1-out spk_e, 0<F<=F_MAX, seq 0xFFFFFFFD, locktime 0);
P2 spend-forbid spk_e; P3 exit needs K1 partial + re-enroll to spk_v';
INV-SEQ ladder nSeq == N; INV-KEYLESS branch-multisig shared-tail templates for S_v (113 B)
and E-2 (106 B). Commits: docs -> vault_policy.py -> tests -> ccc.py hook -> progress doc.
