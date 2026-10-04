# Codex32 review and simulator release plan

## Qualification progress — October 3, 2026 (America/Chicago)

All eight PR heads (#62–69) are merged locally on `codex/codex32-e2e`.
The input pins and build commands are in `codex32-input-manifest.json`; the
file/function review and finding ledger is `codex32-review-ledger.md`, and the
reference capability table is `codex32-reference-capabilities.md`.
The original checkout and review worktrees remain untouched.

The Unix MicroPython simulator and unsigned STM32 MK/Q1 targets compile from
this checkout. MK/Q1 `rng-code-check` passed. The cross compile needs the
command-line `CFLAGS_EXTRA=-Wno-error=dangling-pointer` workaround for modern
GCC against pinned MicroPython; the Unix build uses `CWARN=-Wall` for current
Clang. Host BIP93, extension, harness and dice-script tests passed together:
381 passed, zero skipped or failed. The pinned Python reference suite passed
23 tests, Rust suite 12 tests; differential adapters found no disagreements
for the stated capability sets. The simulator's Codex32 MicroPython unit lane
passed 2/2 on each of Mk4, Mk5 and Q1. A nonheadless Q1 QR capture/decode lane
passed 4/4 after clearing a stale X11 `DISPLAY` value. Three independent
save/restart/discard repetitions passed on all three models.
MK and Q1 key-zero developer/test images and DFU containers were built locally;
`signit check` verified both signatures and hardware-compatibility fields.
Signature timestamps and ECDSA nonces make signed bytes vary across builds;
unsigned compiled sections provide a separate comparison basis.

The first full Codex32 suites exposed a test-fixture error: signature
verification removed `.sig` files before the fixture checked that they still
existed. This was fixed in a focused local commit. The failed first attempts
remain in `artifacts/codex32/2026-10-03-integration/`. Full corrected suites,
adjacent regressions, final clean qualification and tag reproduction remain
open gates; no test-release tag has been created.

## Integration progress — October 3, 2026 (America/Chicago)

The isolated `codex/codex32-e2e` branch starts at the specified
`3e32e32a49c551b35e7bb3cecbf910241f553537` base. GitHub metadata was
refreshed for PRs #62–69; the selected full commit pins are in
`codex32-input-manifest.json`. All eight PR heads have been merged locally,
preserving their constituent commits. PRs #62 and #64 overlapped in checksum
documentation and tests; the merge retained distinct MS1 and CW1 cases. PRs
#63 and #66 overlapped in recovery. The combined flow validates reconstructed
wallet material, shows the #69 CW1/CX1 profile explanation when applicable,
requests #63's unverified-recovery acknowledgement, clears saved progress
under the original settings key, and then activates. These are source-level
integration results; simulator execution and release qualification are still
pending.

The original checkout and review worktrees remain untouched. Top-level
submodules were initialized at their pinned revisions in the integration
checkout. A fully recursive update was stopped after it entered unrelated
ESP-IDF dependencies; build-specific nested submodules will be initialized
explicitly. No simulator or embedded build has yet passed on this branch.

Prepared on October 3, 2026, America/Chicago. This is an initial source assessment and an implementation plan for the local testing release. It does not certify a completed firmware audit or simulator qualification. The exact revisions and checks performed are recorded in `codex32-review-snapshot.json`; the executable follow-up instruction is in `codex32-goal-prompt.md`.

The proposed starting point is `review/codex32-base-2026-09-30`, followed by the six Codex32 PRs, integration fixes, a reliable test runner, and a locally tagged release backed by test evidence. BIP 93 governs the standard MS1 profile. The Python and Rust implementations provide independent comparisons within their documented capabilities.

## What the initial evaluation established

### Source and PR inventory

The working checkout is `master` at `ca06dfd2509eacfad333be9d35ed274559915d0e`. It has modified/untracked submodule contents and unrelated untracked review files. Preserve them. Existing review branches already have separate worktrees; do not reset or repurpose those worktrees.

The common PR base is `3e32e32a49c551b35e7bb3cecbf910241f553537`. It contains upstream [Coldcard/firmware PR 819](https://github.com/Coldcard/firmware/pull/819), merged September 28, 2026, through commit `571f0338301b4d91d07dba64a63ccf5424d16edb`. Do not apply PR 819 again. The review base differs from this checkout's master across 186 files; starting from master and applying only the six fixes would omit their required feature base.

All six fork PRs were open at inspection. Their GitHub check rollups were empty. PR descriptions report host checks but explicitly say simulator integration was not run. Those reported host counts are not independent validation from this assessment.

| PR | Scope | Reviewed head |
| --- | --- | --- |
| [62](https://github.com/Rob1Ham/firmware/pull/62) | Explicit confirmation of overlapping checksum-input lengths | `91b38eea25aaa874061d2545a19f6f31fd326adb` |
| [63](https://github.com/Rob1Ham/firmware/pull/63) | Acknowledge unverified recovery before activation | `ee38283522984081d2e9b848efd790bc2e41e975` |
| [64](https://github.com/Rob1Ham/firmware/pull/64) | All six BIP 93 master-seed sizes and related checksum-input handling | `d95352b34b34a1c87d8e3cd90fe45ee45b2e4d72` |
| [65](https://github.com/Rob1Ham/firmware/pull/65) | Disable pending-share persistence with a blank master | `49bdc723d9a5ee9ddadab7e989f9917e247cf0b0` |
| [66](https://github.com/Rob1Ham/firmware/pull/66) | Validate saved recovery state and delay clearing it | `698811ad0adb9f1a41c4dd7ec971097d4959f002` |
| [67](https://github.com/Rob1Ham/firmware/pull/67) | 100-roll threshold for 256-bit dice-only generation | `89281257377c065fb5d924242bec94914cb26586` |

PRs 62 and 64 received additional commits during this assessment. Use full commit pins and record any later change as a new input snapshot.

### Confirmed integration and tooling issues

1. **PRs 62 and 64 conflict in `docs/codex32.md` and `testing/test_codex32.py`.** Their latest heads contain equivalent checksum-input logic. Consolidate the implementation, preserve the CW1 and MS1 coverage, and remove duplicate test definitions. Python can silently replace an earlier function with a later function of the same name, so successful collection alone is insufficient.
2. **PRs 63 and 66 conflict in `shared/actions.py`.** Resolve recovery as: reconstruct, validate wallet material, obtain the unverified-recovery acknowledgement, clear saved progress under the original settings key, then activate. Cancellation must occur before clearing or activation. Recheck all import return paths and prompts; textual resolution alone does not establish this ordering.
3. **`testing/run_sim_tests.py` is unsuitable as a release gate without changes.** Its parallel path does not aggregate child exit codes; its sequential path does not return a failing process status. Its retry logic can also turn an error with no cached failing test IDs into success through an empty `all(...)`. Track original failures, collection failures, timeouts, crashes, and retries explicitly.
4. **Headless success omits display coverage.** Q1 QR image checks skip in headless mode. The parallel runner also does not consistently forward its headless setting. Require a separate display/QR lane and audit option forwarding.
5. **Persistence tests need real simulator storage.** The base deliberately starts `test_codex32.py` without `--eff`. Use isolated persistent directories for restart tests, and fresh directories for unrelated scenarios.
6. **Model selection must be explicit.** The reviewed runner defaults to Mk5 and provides `--mk4` and `--q1`. Old comments and the `--turbo` description still refer to Mk4. Test the actual selected hardware identity rather than trusting labels.

All 15 PR pairs received a `git merge-tree --write-tree` check in a temporary clone. Only the two pairs above conflicted. This is not proof that the complete six-PR merge is conflict-free or semantically correct.

### Earlier findings that need reconciliation

The existing September 23 disclosure is useful history, but it describes an older PR revision. At the reviewed base, `generate_share` already requires exactly the threshold number of inputs. `shared/backups.py` also excludes `c32_shares` during both backup creation and restoration. Preserve and validate these protections; do not report them as still absent.

PR 63 is an acknowledgement mechanism. It does not authenticate the reconstructed wallet or implement a trusted-address comparison. A fingerprint and a short set identifier are not substitutes for such verification. Treat verified recovery as a separately specified enhancement, not an implied result of this release.

PR 66 still documents a window between clearing pending settings and completing activation. Simulator tests can characterize failure behavior, but cannot establish atomic transactions across real secure elements and flash. The local release notes must state that limit.

## Reference implementations and conformance contract

Pin and retain these sources before implementing the harness:

| Source | Revision | Role |
| --- | --- | --- |
| [BIP 93](https://github.com/bitcoin/bips/blob/927b6de9915c9262615a6399de51b200f81e5aa4/bip-0093.mediawiki) | `927b6de9915c9262615a6399de51b200f81e5aa4` | Normative rules, valid/invalid vectors, expected master seeds and roots |
| [Python reference](https://github.com/BenWestgate/python-codex32/tree/8ab3bae9e5e0877b74cbaca52b2f05229e172f3e) | `8ab3bae9e5e0877b74cbaca52b2f05229e172f3e` | Current default branch, package version 0.6.2 |
| [Rust reference](https://github.com/BlockstreamResearch/codex32/tree/1a1c22aa895d78f2d385303feb9491d155e14cf7/reference/rust-codex32) | `1a1c22aa895d78f2d385303feb9491d155e14cf7` | Independent field arithmetic and encoding implementation |

The earlier local Python comparison used `22990b954e0a6d7f7b417a2a35e503e9ea97ead2`, described there as 1.0.0rc1. That revision was not checked out or tested in this assessment. Add it as a separately pinned comparison if needed; do not silently substitute it for the linked repository's default branch.

The inspected [Python decoder](https://github.com/BenWestgate/python-codex32/blob/8ab3bae9e5e0877b74cbaca52b2f05229e172f3e/src/codex32/bip93.py) allows MS seed lengths from 16 through 64 in steps of four and defaults to CRC padding on generation. The inspected [Rust implementation](https://github.com/BlockstreamResearch/codex32/blob/1a1c22aa895d78f2d385303feb9491d155e14cf7/reference/rust-codex32/src/lib.rs) has older length-selection logic and an interpolation precondition that checks a minimum number of inputs. These differences mean neither repository head is a universal accept/reject oracle for current BIP 93.

Build a capability table and a small, reviewed adapter for each reference. Report disagreements by rule and revision. Normalize case for comparison, explicitly supply identical padding when comparing encoded strings, and compare payload symbols before discarding padding. Never decide validity by majority vote among implementations. Keep external code unchanged and apply profile restrictions in clearly identified adapters.

For the pinned BIP: MS seeds are 16/20/24/28/32/64 bytes, encoded in 48/54/61/67/74/127 characters. Thresholds are 0 or 2–9; threshold 0 requires index S. Preserve legal nonzero padding. Recovery requires matching headers, distinct indices, and exactly k inputs. The short checksum applies through expanded length 93, long through 96–1023, and 94/95 are excluded. Invalid checksums cannot activate wallets; correction suggestions require user confirmation. These rules come from the pinned [specification](https://github.com/bitcoin/bips/blob/927b6de9915c9262615a6399de51b200f81e5aa4/bip-0093.mediawiki).

CW1 and CX1 are firmware extensions with separate contracts in `docs/codex32-extensions.md` and `docs/codex32-extension-vectors.json`. Test CW1 as 16/24/32-byte BIP39 entropy and CX1 as a 64-byte chain-code/private-scalar representation. Do not reinterpret either as an MS1 BIP32 seed or claim reference-wallet support for them.

## Checks completed in this assessment

| Check | Result | Limit |
| --- | --- | --- |
| Rust `cargo test --offline` | 12 passed; zero failed | Bundled reference tests only; two compiler lifetime-style warnings |
| BIP valid-string parsing and round trips on review base | 31 of 34 distinct strings passed | The three additional master-seed sizes were unsupported |
| Same valid-string check on pinned PR 64 | 34 of 34 passed | CPython execution of the module, not firmware UI or storage |
| BIP vector 2 recovery | Passed on base and PR 64 | Public standard test data |
| All ten 3-of-5 subsets from BIP vector 3 | Passed on base and PR 64 | Public standard test data |
| Pairwise PR integration | 13 clean pairs, two conflicting pairs | Temporary Git tree merges only |
| Host readiness | ARM64 macOS; Rust, ARM GCC, SDL2 tools, pkg-config, xterm, uv and Docker executables found | Daemons, compiler compatibility and library linkage not qualified |

The default Python is 3.14.7. The inspected environment lacks pytest, mnemonic, bip32, SDL2 Python bindings, ckcc, serial, zbar and pysecp256k1. No root `ENV` or built `coldcard-mpy` was found. Do not equate these observations with the absence of every possible environment elsewhere on the machine. No firmware build, Python reference suite, simulator suite, or hardware test was run.

## Phase 1 preserve and pin the inputs

Create an isolated worktree or checkout and a new `codex/codex32-e2e` branch from the pinned review base. Inspect attached worktrees before allocating one; explicitly specify the base rather than accepting a default branch. Copy these planning documents into the integration checkout without copying unrelated working changes.

Record the base, every PR head and constituent commit, all reference revisions, recursive submodule revisions, platform, tool versions, environment lock files, and build commands in a machine-readable manifest. Recheck PR metadata once before freezing the inputs. If a head changed, review that delta, update the snapshot, and then keep the selected inputs fixed for the qualification run.

Initialize the integration checkout's own submodules at their recorded revisions. The base pins MicroPython to `3d227feca2b5067fbd024a30d7118cf148d0d3df`, libngu to `4d9af8424ac9183cb3cbb546978c4d05190231e9`, ckcc-protocol to `650c54b5215a7cfe077cd02bb83c884aa984d32c`, and mpy-qr to `11347d83f4eb325b10676a4eb8e17deccfe0df44`. Do not reuse modified submodule working trees as build inputs.

Deliverable: a reproducible input manifest and a baseline build/test inventory with every unavailable check clearly labeled.

## Phase 2 complete the code review and integrate

Review the entire Codex32 feature and its callers, not just the six patches. Maintain a checklist with file/function, expected invariant, evidence, finding, resolution commit, and test ID.

| Area | Review focus |
| --- | --- |
| `shared/codex32.py` | Parsing and constructors, ASCII/case handling, lengths, checksums, field operations, padding, interpolation preconditions, saved-state validation |
| `shared/actions.py`, `shared/seed.py`, `shared/flow.py` | Import, generation, quiz, checksum calculation, split/recover/derive, confirmation ordering, cancellation, master versus temporary wallet |
| `shared/stash.py`, `shared/pincodes.py`, `shared/nvstore.py` | Native representation, usable BIP32 roots, wallet switching, setting-key changes, pending progress, cleanup |
| `shared/backups.py`, `shared/teleport.py` | Backup and restore compatibility, exclusion of pending shares, full-backup paths |
| `shared/decoders.py`, scanner, NFC, UX and export code | Input routing, bounds, formatting, transport round trips, sensitive screens and output |
| RNG bindings, `ngu.random.bytes` callers, dice paths | Correct source and requested byte counts, fresh IDs/masks, entropy accounting, separation of supplemental and dice-only modes |
| Build manifests and tests | Frozen module inclusion, supported device families, production/debug differences, meaningful expectations and test discovery |

Suggested integration order: 64, 62, 65, 66, 63, 67. Keep original commit provenance through merges or `cherry-pick -x`; record any empty/superseded change explicitly. Resolve the two known conflict groups as cohesive integration commits. Inspect the complete resulting diff, including changes that merged automatically.

Review against current source rather than reproducing old disclosure demonstrations. Use public standard vectors and synthetic test wallets for correctness and protection checks. Keep new review work focused on defensive invariants and remediation.

Deliverable: integrated source, reviewed conflict resolutions, updated documentation, and a finding ledger that distinguishes fixed issues, intentional limitations, and open release blockers.

## Phase 3 make the harness trustworthy

Extend existing pytest fixtures and simulator support. A proposed layout is `testing/codex32_harness/` with a CLI runner, reference adapters, a device matrix, a manifest writer, and evidence collection. Keep pure host tests independently runnable with `--noconftest`; import firmware helpers through an explicit module path.

Run each external reference in its own environment/process. Firmware tests contain their own `testing/bip32.py`, while python-codex32 imports the external `bip32` package; putting both on one import path risks comparing the wrong implementation. Adapter responses should carry implementation ID, commit, operation, input case ID, result and structured error category.

The runner must:

- Propagate failing child exit codes, collection errors, empty required selections, crashes, timeouts and missing evidence to a nonzero final status.
- Preserve first-attempt failures when retrying. A retry may diagnose a flake; it cannot erase the original outcome or silently qualify the release.
- Give each job an owned process group, socket, storage directory, log and JUnit file. Clean up only those owned resources; avoid the current global client-socket cleanup pattern.
- Wait for a bounded readiness handshake and verify the reported model. Socket existence alone is insufficient readiness evidence.
- Forward model, headless, marks and timeout options consistently. Start with two concurrent simulator jobs and raise concurrency only after isolation is established.
- Keep settings across planned restart steps, and reset between unrelated scenarios. Separate ordinary fast runs from login, seedless, one-time, slow and display cases.
- Emit collected/passed/failed/error/skipped/xfail counts, skip reasons, durations, first/retry outcomes and artifact paths. Check required test IDs against an explicit coverage manifest.
- Record the actual binary hash, source revision, imported source paths and frozen-module/build provenance. Detect accidental execution of another checkout's simulator.

Test the harness itself with harmless dummy subprocesses that pass, fail, crash, time out, collect zero tests and write incomplete reports. Verify process cleanup and cancellation. These are essential tests because a false success would invalidate all firmware evidence.

## Phase 4 implement the test matrix

Use the following layers. Retain the existing test suite and add focused coverage where the review identifies gaps.

| Layer | Required coverage | Evidence |
| --- | --- | --- |
| Host conformance | Every published valid and invalid BIP vector; all six MS sizes; extension vectors; padding alternatives; format and checksum boundaries | JUnit, vector IDs, source pins |
| Mathematical properties | Thresholds 2–9; distinct indices; ordering independence; split/recover/derive agreement; preserved padding; exact-threshold and metadata validation | Deterministic seed and case counts |
| Differential checks | Firmware against pinned BIP expectations, Python and Rust where supported; payload and derived-root identity | Disagreement report with rule and capability classification |
| Firmware runtime | `devtest/unit_codex32.py`, `unit_codex32_boundaries.py`, native stash encoding and backup helpers under the actual MicroPython build | Runtime identity and simulator logs |
| Simulator workflows | Generation, recording quiz, import, checksum calculation, split, derive, recovery, export, save/resume, cancellation | Screen/story assertions, state snapshots and JUnit |
| Wallet identity | Root/xpub, selected derived addresses, an offline signing round trip, wallet identity after restart and backup restore | Independent expected public outputs and signature validation |
| Regression | Backup, temporary seeds, BIP39 passphrases, Seed Vault, dice, paper wallet, decoders, QR/NFC, signing and telemetry-free export paths | Per-module results and explicit exclusions |

The minimum simulator models are Mk4, Mk5 and Q1. For each, cover blank master, configured master, temporary wallet over a configured master, and temporary wallet over a blank master. Include Seed Vault enabled/disabled and supported passphrase states where the workflow reaches them.

Exercise manual entry, MicroSD, virtual disk, NFC, and Q1 scanning where supported. For exports, include text/file integrity, display/QR decoding and simulated NFC payloads. Mark unavailable transports as structurally inapplicable, with a reason. Cover every supported route at least once and use pairwise combinations for the wider matrix; require full combinations for persistence and wallet-change invariants.

Keep separate cases for complete checksummed strings and intentional bodies without checksums. The overlapping CW1 and MS1 lengths require both confirm and cancel coverage. Test ordinary invalid input, retry, input length limits and case handling at the UI boundary without weakening the parser contract.

For recovery and persistence, assert that declining acknowledgement leaves the active wallet and saved progress unchanged, invalid wallet material does not activate, blank-master sessions do not persist new shares, configured-master save/resume works across process restart, and explicit discard has the documented effect. Confirm pending state stays excluded from backup and teleport output. Characterize the documented clear/activation failure window without claiming physical secure erasure or hardware atomicity.

For BIP39 extension recovery, verify entropy-to-mnemonic and passphrase semantics. For CX1, verify chain-code/scalar ordering and public wallet identity. For MS1, compare expected BIP32 roots directly. Comparing only the four-byte fingerprint is insufficient to detect an accidental wrong-wallet result.

For dice generation, cover the 49/50 and 99/100 boundaries, cancellation, and effects on Codex32, BIP39 and paper-wallet flows. Check deterministic hash derivation against the verification scripts. Frequency checks and statistical sampling do not prove entropy quality; simulator RNG behavior cannot validate the physical RNG.

Proposed bounded property budget: 1,000 deterministic cases per MS size, distributed across thresholds and legal padding; all subsets for small share sets; deterministic sampled subsets for larger sets. Measure runtime and split slow cases into a declared lane. Preserve case seeds for diagnosis. Do not claim exhaustive coverage of the full input space.

Use public/synthetic secrets only. Keep private test material in local test artifacts when needed, and prefer case IDs and public wallet outputs in summaries. No broadcasting or live wallet balances are needed for the signing checks.

## Phase 5 build and run in increasing scope

Create compatible, pinned environments instead of installing into system Python. First qualify a Python version against the repository's older dependency pins, including pytest 6.2.5 and mnemonic 0.18. Lock VCS dependencies currently pointing at `master`. Record native secp256k1, SDL2 and QR-decoder linkage. Rust has no crate dependencies at the inspected reference revision.

Build the simulator from the isolated checkout using its `unix/Makefile` setup and libngu targets. Read the current recipes before execution: setup can initialize submodules and build helper runtimes. Address macOS ARM64 issues in focused, documented commits if necessary; a pinned Linux build environment is an alternative when native tooling cannot reproduce the required runtime.

Run in this order:

1. Host conformance and reference smoke tests; validate test discovery and adapter provenance.
2. Simulator readiness and simple existing unit tests on each model.
3. MicroPython Codex32 unit tests, then targeted Codex32 UI and extension suites.
4. Save/resume and lifecycle tests with explicit process restart and persistent storage.
5. Q1 display/QR lane with image decoding enabled; manual completion of genuinely attended cases is recorded separately.
6. Adjacent regression modules, including `test_backup.py`, `test_ephemeral.py`, `test_bip39pw.py`, `test_teleport.py`, `test_decoders.py`, `test_seed_xor.py`, `test_rolls.py`, `test_paper.py`, `test_ux.py`, `test_addr.py` and focused signing tests.
7. Broad simulator suite, then declared one-time, slow, seedless and login cases. Record any Bitcoin Core dependent cases separately; use an isolated local test node if required.
8. A clean rerun of all required release lanes on the final source revision. Three isolated repetitions of persistence and cancellation scenarios are the proposed flake check.

Existing useful entry points include `pytest --noconftest testing/test_codex32_extensions.py`, `testing/test_codex32.py`, and `testing/test_unit.py` tests named `test_codex32` and `test_codex32_boundaries`. Run standalone dice/script tests explicitly: the simulator wrapper filters out `test_rolls.py`. Exact launch commands must be documented after the repaired runner and environment are verified.

Compile the embedded MK and Q1 targets as a separate lane, using `stm32/MK-Makefile` and `stm32/Q1-Makefile` plus the inspected `dockerfile.build`/`repro-build.sh` path where appropriate. MK serves Mk4/Mk5. Some README references still name the older MK4 makefile. Record image digests, compiler versions, size reports, firmware hashes and signing-key identity. A simulator run executes a Unix MicroPython build, not the resulting STM32 firmware image; compile success is distinct evidence.

Use developer/test signing only for any installable local artifacts. Inspect recipes before using `release`, `rc1`, `rc2` or `repro`: some perform commits, timestamp/block-height updates, signing, tagging or factory-image assembly. Implement an explicit local packaging target rather than inheriting publication or installation side effects.

## Phase 6 commits and local release evidence

Suggested commit sequence after preserving PR provenance:

1. Resolve combined Codex32 behavior and update its tests/docs.
2. Correct simulator runner status, isolation and option forwarding, with harness self-tests.
3. Add pinned fixtures/reference adapters and conformance coverage.
4. Add simulator lifecycle, wallet-identity and transport coverage.
5. Fix issues discovered by these checks in focused commits with corresponding regression coverage.
6. Add environment locks, repeatable build/package commands, qualification report and release notes.

Keep source and small public fixtures in Git. Store bulky logs, screenshots, simulator binaries and embedded images in an ignored `artifacts/codex32/<run-id>/` directory. Package a local archive with an input/build manifest, source commit, test results, skip ledger, first-failure/retry records, limitations, and SHA256SUMS. Avoid committing generated secrets or unrelated audit material.

Create an annotated local tag such as `codex32-test-2026-10-03-rc1`, using the actual packaging date when it differs. The tag identifies exactly the tested source commit. If the source changes after qualification, rerun affected gates and issue a new RC; never move an existing tag. Retest from a clean checkout of that tag before calling the release reproducible. Account explicitly for timestamps and other expected binary variation rather than silently ignoring differences.

Keep the work local: the follow-up authorizes local commits and a local tag. Pushing, merging hosted PRs, publishing a GitHub release and flashing physical hardware are separate actions.

## Completion criteria

- The review checklist covers the feature and its integration boundaries, and all six pinned PRs are incorporated or explicitly accounted for as superseded.
- Required conformance, runtime, simulator, display and embedded compilation lanes pass on the final commit. Every required test is collected; skips and expected failures have specific dispositions.
- The harness proves it fails on errors and retains retry history. It does not label a partially executed matrix as a full pass.
- No unresolved release-blocking correctness or state-preservation finding remains. Intended limitations, including unverified recovery and simulator/hardware differences, are explicit in the release report.
- An annotated local tag, local test artifacts, hashes, commit history and repeatable commands identify the same source revision.
- A clean tagged checkout can repeat the required qualification commands. Missing dependencies, hardware-only checks or attended work are reported honestly; they cannot be counted as executed simulator evidence.

The next stage should begin with Phase 1 and proceed through these gates. The current assessment has not started that build-and-qualification goal.
