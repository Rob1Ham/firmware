# TENTATIVE Plan Element — Enrollment-Time Lattice Commitment (Merkle Root)

Status: **TENTATIVE** — scoped to enrollment/deposit-time only, per
discussion 2026-10-14. NOT a spend-time enforcement mechanism.

## T1 Purpose

Host constructs the ENTIRE pre-signed vault PSBT lattice (state
transitions + per-state emergency txs, REV3 D-3 / 5.1: every state has
its signed 2-of-3 assembly set). Host hashes the set into a Merkle tree,
displays ROOT on its UI. The DEVICE, during enrollment, receives the
same set, recomputes ROOT, displays it. User eyeballs host-root ==
device-root => cryptographic proof host and device agree on the exact
committed batch BEFORE any deposit funds the vault. Device stores root
(+leaf count) in settings["vaultcfg"].

## T2 Why not spend-time?

Deliberate scope decision (user, 2026-10-14): no per-spend membership
proofs required. Runtime enforcement remains the shape rules (P1/P2/P3,
INV-SEQ) which were designed to stand alone. Residual risk, documented:
device cannot prove a specific later PSBT belonged to the enrolled
batch; a shape-valid non-member tx could still be signed IF the
attacker can feed it with matching policy cfg. Mitigations: root is
re-displayed at every deposit; enrollment REPLACES cfg and root
together; shape rules unchanged.

## T3 Leaf definition (deterministic, order-robust)

    leaf_i = dSHA256( LE32(i) || unsigned_tx_serialized_bytes_i )

- unsigned tx = the PSBT global unsigned transaction; excludes all
  partial sigs (sigs may legitimately vary/assemble later); txid-equal
  txs hash equal regardless of PSBT key-ordering across producers.
- LE32(i) = little-endian leaf index; position-binding kills reorder
  ambiguity; index doubles as canonical lattice ordering (host must
  emit set in deterministic state order).
- dSHA256 = sha256d everywhere (Bitcoin convention).

## T4 Tree construction (Bitcoin-style)

- internal = dSHA256(left || right); odd level duplicates last node.
- Empty set REFUSED; count cap (2^16 leaves; above => error).
- Root_display: hex first 8 + last 8 bytes + leaf count, e.g.
  `ROOT 84f2...9c0d (37 leaves)`. Full 64-hex behind menu item
  "Show commitment root".

## T5 Device-side enrollment flow (machine level)

1. Receives, in ONE session: sv_script, se_script, n, f0_max,
   k1_pubkey, exit_spk, then the FULL PSBT set (streamed).
2. parse_vault_script / parse_deepvault_script template checks
   (INV-KEYLESS/INV-BRANCH); derive spk_v/spk_e.
3. For EACH streamed PSBT: build view (same builder as spend-time
   hook) => VaultPolicy.check(view) — full-batch shape validation at
   enrollment; any failure aborts enrollment with reason + index.
4. Extract unsigned-tx bytes per PSBT; hash leaves with index
   prefix; STREAM the tree: keep O(log n) stack of combined node
   hashes per height ("carry tree"); input peak RAM ~= a few KB =>
   fine on Mk4/Q. (Reference impl may first do the naive two-pass
   O(n) nodes array for test parity.)
5. Display root (short form + count). Chooser y/n: user compares to
   host UI root. On 'n': wipe session, no settings write, back out.
6. On 'y': stable-marshal policy dict INCLUDING lattice_root/
   lattice_count into settings["vaultcfg"].

## T6 Deposit-time gating

- The funding/deposit tx pays INTO spk_v; it is NOT a lattice member
  (lattice members all SPEND the vault). It flows through the normal
  sign path; vault mode refuses auto-sign of it (not vault-relevant
  as spend; user-confirmed path).
- "Begin deposit" UX: menu item shows stored lattice_root (+count)
  from cfg; instructs user to compare to host's current commitment
  for THIS funding operation; only then proceed to broadcast/export.

## T7 Implementation plan (concrete)

1. shared/vault_policy.py += pure funcs:
   - `sha256d(b)` (uhashlib/hashlib shim already present)
   - `leaf_hash(index, unsigned_tx_bytes)`
   - `lattice_root(leaf_iter)` streaming carry-tree; returns
     (root_bytes, count); refuses >2^16.
   - `LatticeCheck` helper: given cfg + PSBT set iter, run per-PSBT
     check + collect leaves => root (host-testable).
2. Testing: extend testing/test_vault_policy.py-style suite:
   - fixture lattice of N valid PSBTs => fixed root vector (cross-
     check vs tiny reference tree built differently = parity test).
   - parity: naive 2-level memo vs streaming => same root, several N
     incl. odd counts (dup-last correctness).
   - tamper: swap leaf order => root differs; one paid-output sat
     changed => root differs; remove one leaf => root differs.
   - enrollment-dry: cfg + set assembly => stored dict fields.
3. shared/vault.py VaultFeature.enroll(session_stream) wiring (build
   with step 2 of device-mode commit sequence; skeleton step does not
   need it).
4. USB enroll-transport message: framed chunks, declared total PSBT
   count, per-chunk ACK (pattern after existing multisig/COLDCARD
   upload flows in auth.py/ckcc protocol); exact framing decided at
   implementation time — flagged here as the one build-uncertainty.
5. Menu items: "Enroll vault (scripts + lattice)", "Show commitment
   root", wipe includes lattice fields.

## T8 Explicit non-goals

- No Merkle inclusion proof verifies at spend time (out of scope).
- No user review UI for the PSBT LIST itself (root-only display).
- No attestation/secure-element binding of root in this rev.
