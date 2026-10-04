# Codex32 unified branch compared with current upstream

This document compares the unified Codex32 integration with the **current default branch of `Coldcard/firmware`**, checked on October 4, 2026 (America/Chicago). At that check, upstream `HEAD` and `master` both resolved to [`3e32e32a49c551b35e7bb3cecbf910241f553537`](https://github.com/Coldcard/firmware/commit/3e32e32a49c551b35e7bb3cecbf910241f553537), the September 30 v5.6.3 release commit. The simulator-qualified integration source is [`641e96c3547df4155c1ff83ba055c4e16a21c9f0`](https://github.com/Rob1Ham/firmware/commit/641e96c3547df4155c1ff83ba055c4e16a21c9f0), identified by the annotated `codex32-test-2026-10-04-rc1` tag. Upstream is its merge base, so the comparison has no unrelated upstream commits to reconcile.

The fork's `origin/master` was separately checked at `ca06dfd2509eacfad333be9d35ed274559915d0e`, an older ancestor of this branch. It is not the baseline for the comparison below; using the named `upstream/master` ref prevents fork-only history from being mistaken for a difference in Coldcard's current implementation.

The tested source differs from upstream in **45 paths: 3,678 insertions and 181 deletions**. This document and the companion [maintainer summary](codex32-maintainer-summary.md) are later documentation-only additions to the same unified branch; the test tag remains on the source revision that was qualified. No STM32 build recipe, submodule gitlink, or `external/` source is changed by this branch.

To reproduce the source comparison:

```sh
git diff --stat 3e32e32a49c551b35e7bb3cecbf910241f553537 641e96c3547df4155c1ff83ba055c4e16a21c9f0
git diff --name-status 3e32e32a49c551b35e7bb3cecbf910241f553537 641e96c3547df4155c1ff83ba055c4e16a21c9f0
git log --first-parent --oneline 3e32e32a49c551b35e7bb3cecbf910241f553537..641e96c3547df4155c1ff83ba055c4e16a21c9f0
```

## Existing upstream implementation and PR provenance

Upstream already contains the initial Codex32 and Shamir Secret Sharing implementation from PR 819 (`571f0338`), plus follow-up input and UI commits. This branch **hardens and tests that implementation**; it does not introduce Codex32 from scratch. It retains the full heads of fork PRs [#62](https://github.com/Rob1Ham/firmware/pull/62), [#63](https://github.com/Rob1Ham/firmware/pull/63), [#64](https://github.com/Rob1Ham/firmware/pull/64), [#65](https://github.com/Rob1Ham/firmware/pull/65), [#66](https://github.com/Rob1Ham/firmware/pull/66), [#67](https://github.com/Rob1Ham/firmware/pull/67), [#68](https://github.com/Rob1Ham/firmware/pull/68), and [#69](https://github.com/Rob1Ham/firmware/pull/69) as merge ancestry. Their exact heads and merge order are pinned in `docs/codex32-input-manifest.json`.

| Input | Difference from upstream | Integration resolution |
| --- | --- | --- |
| #62 and #64 | Ambiguous checksum input; MS1 sizes beyond 128/256/512 bits | Combined the overlapping checksum edits without duplicate test definitions; added all six BIP 93 MS1 lengths. |
| #65 | Partial recovery shares could be saved under a seedless settings key, including with a temporary wallet active | Disallow Save & Exit without a configured master; allow continued collection or explicit discard. |
| #66 and #63 | Saved entries could bypass set validation; clearing occurred too early; recovered wallet identity was not authenticated | Validate saved shares and reconstructed wallet first, warn about unverified identity, retain state on cancellation, then clear under the original settings key before activation. |
| #67 | A 256-bit dice-only seed required only 99 fair D6 rolls, whose theoretical maximum is below 256 bits | Require 100 rolls and explain the fair, independent-roll assumption and limits of the frequency check. |
| #68 | Export of an unrelated derived or checksum-completed share could be signed by the active wallet | Sign only shares known to come from splitting the active wallet. |
| #69 | CW1 and CX1 recovery could be misunderstood as restoring the same wallet words/passphrase | Explain CW1 words plus empty initial passphrase and CX1 extended-key material before activation. |
| Integration fixes | A 160-bit seed has no padding symbol; completed derivation could leave saved partial state | Reject impossible `pad_val` (`fbe72467`); clear completed derivation state (`7649d1d9`). |

BIP 93 at `927b6de9915c9262615a6399de51b200f81e5aa4` is normative for **MS1**. CW1 and CX1 are firmware extensions. The pinned Python and Rust implementations were compared only within their documented capabilities; neither overrides BIP 93. See `docs/codex32-reference-capabilities.md`.

## User-visible and security behavior differences

| Behavior | Upstream `master` | Unified branch |
| --- | --- | --- |
| MS1 sizes | Raw 16, 32, and 64-byte master seeds (128, 256, 512 bits) | All six BIP 93 sizes: 16, 20, 24, 28, 32, 64 bytes. Parser, secret storage, split flow, and display agree. |
| 160-bit padding | Constructor could accept a nonzero padding value even though no padding symbol exists | Rejects that impossible value. |
| Checksum calculation at overlapping lengths | Parsed a complete share first, falling back to a checksum-less body after parse failure | At CW1 lengths 48/61 and MS1 lengths 48/54/61, explicitly asks whether to validate a complete share or add a checksum to the longer body. A failing complete checksum cannot silently select the other interpretation. |
| Recovery with saved partial shares | Parsed stored entries individually and cleared progress before reconstruction completed | Checks stored type, set identity, threshold, indices, size, and checksum; prompts before discarding invalid state; retains progress after reconstruction or validation failure. |
| Recovery activation | Reconstructed index `S` was activated after checksum validation | Validates usable wallet material, explains CW1/CX1 semantics, and requires an **UNVERIFIED** acknowledgement. Cancellation preserves the active wallet and pending shares. After acknowledgement, progress is cleared under the original master settings key before activation. |
| Blank master and partial-share saving | Allowed a save path even though seedless settings lack wallet-derived confidentiality | No Save & Exit path when the master is blank, even if a temporary wallet is active. Existing old flash copies are not claimed to be securely erased. |
| Derived-share state | Collected shares could remain in saved settings after completion or exit | Clears the saved partial set once a threshold is collected for derivation and on confirmed exit. |
| File export signature | A wallet with active secrets signed a share file even if the share belonged to another wallet | Signs a share only on the Shamir Split route, where the active-wallet relationship is known. Derived and checksum-completed share exports remain unsigned. |
| Dice-only generation | 50 rolls for 128-bit and 99 for 256-bit requests | 50 and 100 rolls respectively, with explicit limits on the entropy estimate. Dice input is still hashed; this change does not claim to debias it. |

The current branch does **not** add cryptographic proof that a reconstructed wallet is the original. A checksum and short fingerprint do not establish that identity. The user must compare an independently recorded address with the correct network, address type, and derivation path. The interval between clearing saved state and completing activation remains a hardware power-loss concern.

## Test, simulator, and release-process differences

- The new `testing/codex32_e2e_harness.py` owns a simulator process group, an isolated settings directory, and one pytest run. It checks simulator model and source/storage identity, freezes required test IDs, parses JUnit outcomes, records skips with exact dispositions, and returns failure on collection gaps, child errors, crashes, timeouts, or missing reports. A retry is diagnostic and cannot erase a failed first attempt. `testing/test_codex32_e2e_harness.py` exercises those failure modes.
- `unix/simulator.py` can use a harness-owned `CKCC_SIM_WORKDIR` across intentional restarts. `testing/run_codex32_restart_matrix.py` runs preparation, verification/discard, and post-discard verification in separate processes, three times per model. The older `testing/run_sim_tests.py` now propagates child failures and model selection instead of reporting false success.
- Pinned BIP 93 vectors, host conformance cases, Python/Rust differential adapters, a Python environment lock, exact simulator coverage and skip ledgers, and a local deterministic packaging script were added. The Python and Rust reference capability limits are stated explicitly.
- Existing UI and regression tests gained bounded waits for asynchronous Q1 QR display, first-time setup, wallet identity, Seed Vault, checksum, menu, and blocked-screen transitions. Test fixtures now restore chain and signing-warning settings, keep detached-signature checks consistent with cleanup, avoid stale address/QR UI state, and isolate/terminate a local Bitcoin Core regtest process. These are test reliability changes; they do not imply additional production firmware modifications.

The qualification recorded 254 passing Codex32 cases on each Mk4 and Mk5 and 284 on Q1, with no failures or errors. Each Mk run had 30 exact Q1-only structural exclusions, all exercised by Q1. The final source also passed 27/27 restart stages, 385/385 host tests, Mk4 decoder 81/81, Mk5 paper/address 60/60, and two Codex32 MicroPython unit tests per model. The pinned Python suite passed 23 and the Rust suite 12; comparisons of 34 published valid, 55 invalid, and 1,200 Python/360 Rust generated cases found zero disagreements within their shared capabilities. MK and Q1 compiled, key-0 **developer/test** signatures were checked, and unsigned sections matched an independent tagged checkout byte for byte.

Broader backup, Seed XOR, passphrase, UX, teleport, and signing regressions passed on earlier revisions with identical firmware source paths and simulator binary. They are source-equivalent evidence, **not** claimed as final-source reruns. Failed diagnostic attempts and required structural exclusions were not counted as passing tests. The local qualification report and build archive were not pushed; the original temporary artifact directory has since been cleaned, so a new raw evidence bundle must be generated for independent inspection. The source, test inputs, and reproduction steps are committed.

## Complete tested-revision path inventory

This lists every path changed by `git diff --name-status upstream/master..codex32-test-2026-10-04-rc1`. `A` means added; `M` means modified. The two documents created after the tag are listed separately at the end.

| Status | Path | Difference |
| --- | --- | --- |
| M | `.gitignore` | Excludes isolated virtual environments and generated Codex32 artifacts. |
| A | `docs/codex32-e2e-plan.md` | Review plan, qualification gates, progress, and historical findings. |
| A | `docs/codex32-goal-prompt.md` | Original executable local review and integration scope. |
| A | `docs/codex32-input-manifest.json` | PR heads, reference revisions, submodule pins, tool versions, locks, and build commands. |
| A | `docs/codex32-reference-capabilities.md` | BIP 93 authority and the limits of each reference comparison. |
| A | `docs/codex32-review-ledger.md` | Code invariants, conflict resolutions, tests, findings, and limits. |
| A | `docs/codex32-review-snapshot.json` | Initial source review snapshot. |
| M | `docs/codex32.md` | MS1 sizes, checksum ambiguity, share provenance, dice estimate, recovery and storage behavior, and remaining limits. |
| M | `docs/rolls.py` | 100-roll warning threshold for 256-bit dice input. |
| M | `docs/rolls_codex32.py` | 100-roll minimum for 256-bit Codex32 dice script. |
| M | `shared/actions.py` | MS1 display/split sizes; checksum choice; recovery, acknowledgement, saved-state, derivation, and signature-export flow. |
| M | `shared/codex32.py` | Six MS1 lengths, impossible-padding rejection, and saved-share set validation. |
| M | `shared/seed.py` | 100-roll 256-bit dice threshold and honest entropy warning. |
| M | `shared/stash.py` | Stores all six supported raw MS1 seed sizes. |
| M | `testing/api.py` | Bounded Bitcoin Core startup and process-group cleanup. |
| A | `testing/codex32-coverage-manifest.json` | Frozen required simulator test IDs. |
| A | `testing/codex32-skip-ledger-mk.json` | Exact Mk-only exclusions and Q1 counterpart dispositions. |
| A | `testing/codex32_e2e_harness.py` | Isolated fail-closed simulator runner and machine-readable evidence. |
| A | `testing/codex32_ref_python_adapter.py` | Python reference adapter for reviewed MS1 capabilities. |
| A | `testing/codex32_ref_rust_adapter.rs` | Rust reference adapter for reviewed parser capabilities. |
| M | `testing/conftest.py` | Native secp256k1 discovery, first-time setup wait, and VirtualDisk UX fixture. |
| M | `testing/devtest/menu_dump.py` | Avoids entering an interactive WIF Store action during menu enumeration. |
| M | `testing/devtest/unit_codex32.py` | All MS1 sizes and boundary checks in simulator MicroPython. |
| M | `testing/devtest/unit_codex32_boundaries.py` | Aligns boundary expectation with exact MS1 sizes. |
| A | `testing/fixtures/codex32-bip93-vectors.json` | Pinned published valid/invalid BIP 93 vectors. |
| A | `testing/package_codex32_local.py` | Checks qualified report, hashes, clean source, and annotated tag before deterministic local archive creation. |
| A | `testing/requirements-codex32.in` | Direct Codex32 test environment dependencies. |
| A | `testing/requirements-codex32.lock` | Pinned Python environment. |
| A | `testing/run_codex32_python_comparison.py` | Pinned Python differential driver. |
| A | `testing/run_codex32_restart_matrix.py` | Three-stage, three-model persistence runner. |
| A | `testing/run_codex32_rust_comparison.py` | Pinned Rust differential driver. |
| M | `testing/run_sim_tests.py` | Correct model forwarding, child status, empty selection, and retry outcome handling. |
| M | `testing/test_addr.py` | Leaves the address/QR screen before the next case. |
| M | `testing/test_codex32.py` | Full Codex32 UI routes, checksum choices, profiles, state transitions, exports, and identity assertions. |
| A | `testing/test_codex32_bip93.py` | Normative vector, round-trip, padding, and BIP32-root host tests. |
| A | `testing/test_codex32_e2e_harness.py` | Runner success/failure/timeout/selection/cleanup tests. |
| M | `testing/test_codex32_extensions.py` | CW1/CX1 and threshold semantics regression cases. |
| A | `testing/test_codex32_restart.py` | Separate-process recovery and discard assertions. |
| M | `testing/test_ephemeral.py` | Seed Vault readiness and 100-roll temporary-seed expectations. |
| M | `testing/test_paper.py` | Chain restoration and deterministic 100-roll paper-wallet cases. |
| M | `testing/test_rolls.py` | Script threshold expectations. |
| M | `testing/test_sign.py` | Explicit Testnet4 and restored SIGHASH warning policy for signing comparisons. |
| M | `testing/test_teleport.py` | Bounded wait for the Q1 blocked screen. |
| M | `testing/test_ux.py` | Q1 QR frame readiness, dice threshold, and explicit testnet wallet identity. |
| M | `unix/simulator.py` | Stable harness-owned storage directory for restart tests. |

Documentation-only paths added after the simulator-qualified tag: `docs/codex32-maintainer-summary.md` and this file. They do not alter firmware, tests, build recipes, or the tagged source. The original checkout's unrelated untracked work was not included.
