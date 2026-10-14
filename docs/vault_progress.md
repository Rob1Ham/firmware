# Vault work — progress ledger (2026-10-14)

Branch `vault-cosign-policy` on coldcard-vault (Coldcard firmware fork).

## Done and committed

- `shared/vault_policy.py` — pure stdlib decision core (structural S_v/S_e
  parsers, sequence classification, P1/P2/P3 + INV-SEQ/INV-SINK checks,
  `decode_sequence`). Suite `testing/test_vault_policy.py` (host, CPython):
  **7/7 tests pass ("ALL VAULT TESTS PASS", 45 checks)** — verified by
  user run; local harness returned corrupt output mid-session so the pass
  was user-verified, then re-verified at commit time below.
- `docs/vault_signing_gameplan.md` — hook recon + ruleset + design.
- `docs/vault_device_mode_gameplan.md` — device-mode integration plan
  (Option 2: standalone `VaultFeature`; Option 1: CCC `meets_policy`
  delegation; view builder spec; NVS `vault`; minimal menu; 5-commit
  landing order).
- `docs/vault_lattice_commitment_plan.md` — TENTATIVE enrollment-time
  Merkle commitment over the vault PSBT lattice (leaf = dSHA256 of
  LE32(index)+unsigned-tx bytes; Bitcoin-style dup-last tree; device
  recomputes + displays root at enrollment; deposit gates on stored root;
  explicit no-spend-time-membership scoping decision + residual risk).

## Known history (kept honest)

- Commit `3975301` ("all 45 checks passing") was committed while tests
  were FAILING; the actual fixes (key alignment sv_hash/k1_pubkey/
  exit_spk, `.get("is_change")`, sink-entry guard, locktime rule) landed
  in the follow-up commit shipped with this ledger.
- Two docs drafts (device-mode plan, progress) were lost to failed shell
  heredocs during the session; both were rewritten via direct file writes.
- `ccc.py` once gained a stray `from menu import SystemMenu` (no such
  class); reverted in the fix commit.

## NOT done (next)

1. DONE 2026-10-14 (second attempt) — `shared/vault.py` `VaultMode` glue +
   auth.py hook + host test suite. See "Session 2026-10-14 (b)" below.
2. DONE 2026-10-14 — `ccc.py` `meets_policy` skips the height-based
   velocity ratchet for vault-relevant txs (they pin nLockTime==0, which
   the ratchet would always refuse); warnings / magnitude / whitelist
   still apply (belt-and-suspenders).
3. DONE 2026-10-14 — `shared/vault_menu.py` `VaultConfigMenu` + flow.py
   'Vault Co-Sign' item in the Spending Policy submenu. Menu: Vault Mode
   on/off (refused until enrolled + valid), Enroll Policy via JSON file
   (USB/SD, enrolls dark), Cadence N, Max Fee, Exit Destination,
   Commitment Root, Wipe. Settings key is `vault`; gameplan docs updated
   from `vaultcfg` to match the implementation.
4. DONE 2026-10-14 — lattice commitment implemented per plan:
   `vault_policy.py` gained `sha256d`/`leaf_hash` (T3: dSHA256 of
   LE32(index)+unsigned-tx bytes)/`lattice_root` (T4: Bitcoin-style
   dup-last Merkle over a streamed carry-stack, O(log n) RAM, 2^16 leaf
   cap, empty-set refused); `vault.py` gained `enroll_lattice`
   (full-batch shape validation w/ leaf-indexed errors + root, never
   writes settings) and `store_lattice` (persists lattice_root/
   lattice_count only after user confirms root == host root);
   `vault_menu.py` gained 'Enroll Lattice' (file-by-file .psbt selection,
   root short-form display, confirm-then-store) and the root+count
   display. Parity proven vs a naive two-pass reference tree across
   13 batch sizes incl. odd counts. USB framed transport (plan T7.4)
   simplified to the existing file picker.
5. DONE 2026-10-14 — simulator run (unix/ port). Built coldcard-mpy on a
   constrained host: submodules re-initialized, mpy-cross built first,
   `MICROPY_PY_FFI=0` (no libffi-dev, no sudo) +
   `CFLAGS_EXTRA="-Wno-error=dangling-pointer -Wno-error=enum-int-mismatch"`
   (old mpy vs new gcc). Two real bugs found and fixed by the simulator:
   (a) `vault.py`/`vault_policy.py` used `bytearray.fromhex`, which mpy
   v1.12 lacks -> replaced with `ubinascii`/`binascii` `unhexlify`
   (with ImportError fallback for host); (b) frozen `unix/variant/ckcc.py`
   `get_sim_root_dirs` assumed FFI libc getcwd -> no-FFI fallback to
   `cwd='.'` (launcher runs with cwd=unix/work). Validation, two tiers:
   (1) `unix/vault_sim_smoke.py` — device-context smoke run inside
   coldcard-mpy with real nvstore (SettingsObject + MK4_WORKDIR):
   14/14 checks incl. NVS round-trip, mpy-path emergency-approve and
   wrong-N ladder refuse, known-answer lattice root (computed
   independently on CPython host)
   `750024e529e68a0e2bb6abe0e6b58aab3e327573d1ca1ba193ff942924a993e9`
   (5 leaves, cross-runtime agreement), vault.log written,
   VaultConfigMenu constructs, wipe; (2) full headless firmware boot
   `python3 ./simulator.py --headless` — clean through sim_boot ->
   main -> 'Start: mainline' (flow.py vault_menu import chain) with no
   tracebacks. Host suites re-verified green after the portability
   fixes: policy 8/8, glue 34/34.

## Session 2026-10-14 (b) — vault mode glue landed (for real)

- `shared/vault.py` (153 lines): `VaultMode` class, CCCFeature-style.
  Settings key `vault` (dict): `enabled`, `strict`, plus policy fields
  `sv_hash`, `spk_e`, `k1_pubkey`, `n`, `f0_max`, `exit_spk`. Relevance
  sniff on input utxo spk; fail-closed view builder (missing
  witness_utxo -> refuse); `could_sign` returns `(ok, msg)`, never
  raises; append-only `vault.log` ledger (never raises).
- `shared/auth.py` hook: in `interact()` immediately after
  `CCCFeature.could_cosign` (L445): if `VaultMode.is_enabled()`, call
  `VaultMode.could_sign(self.psbt)`; refusal -> `self.failure(v_msg,
  title='VAULT')`. Unexpected vault errors also block (fail closed).
- `testing/test_vault.py`: 17-check host suite (feature flag, relevance,
  emergency approve, wrong-N ladder refuse, INV-SINK refuse, strict mode,
  missing-utxo fail-closed, vault_log). Runs in a mkdtemp so vault.log
  never dirties the repo.
- Test reality: **pytest is not installed on this box.** Suites run
  DIRECTLY: `python3 testing/test_vault_policy.py` -> "ALL VAULT TESTS
  PASS (7)" (45 checks); `python3 testing/test_vault.py` ->
  "VAULT GLUE: 17/17 checks pass". Any earlier pytest-count claims were
  garbled harness output.

## Session 2026-10-14 (b) — kept honest

- Every commit claimed after `de3867d` in the prior session silently
  no-op'd; HEAD was still `de3867d` at session start. The on-disk file
  edits survived; the commits and several ledger appends did not. This
  session re-verified and re-landed everything with in-call `git log`
  verification.
- Glue-suite bug found by user run: the fake settings object was a
  plain dict with a `get` KEY — builtin `dict.get` is not shadowed by
  keys, so `settings.get('vault')` returned None and every vault-relevant
  tx degraded to "not vault-relevant" (10/17 pass). Fixed with a real
  `_FakeSettings` class shim -> 17/17.
- Second test bug: `vault.log` assertion expected exactly 2 lines but
  earlier `could_sign` calls also append; relaxed to `>= 2`.
