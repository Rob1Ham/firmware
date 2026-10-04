# Codex32 integration: maintainer summary

Prepared October 4, 2026. This is a review request for a simulator-tested firmware integration, not a hardware or production release.

## Source to review

- Unified branch: [`codex/codex32-e2e`](https://github.com/Rob1Ham/firmware/tree/codex/codex32-e2e)
- Tested commit: [`641e96c3`](https://github.com/Rob1Ham/firmware/commit/641e96c3547df4155c1ff83ba055c4e16a21c9f0)
- Annotated test-release tag: [`codex32-test-2026-10-04-rc1`](https://github.com/Rob1Ham/firmware/tree/codex32-test-2026-10-04-rc1)
- Detailed [review ledger](https://github.com/Rob1Ham/firmware/blob/codex/codex32-e2e/docs/codex32-review-ledger.md), [input pins](https://github.com/Rob1Ham/firmware/blob/codex/codex32-e2e/docs/codex32-input-manifest.json), and [test plan](https://github.com/Rob1Ham/firmware/blob/codex/codex32-e2e/docs/codex32-e2e-plan.md)
- [Complete comparison with the current upstream implementation](codex32-upstream-comparison.md), including a path-by-path inventory of the changes

The branch integrates the full commits of PRs #62–69, retaining their provenance. BIP 93 is the authority for MS1. CW1 and CX1 are firmware extensions, with their separate behavior documented in the branch. The integration resolves overlapping checksum and recovery changes, then adds focused correctness and test-infrastructure fixes.

## Findings resolved

- Reject an impossible padding value for a 160-bit MS1 seed (`fbe72467`).
- Clear completed Codex32 derivation state so stale partial shares cannot follow a wallet transition (`7649d1d9`).
- Consolidate the checksum-length choice from PRs #62/#64 and the recovery sequence from PRs #63/#66/#69. Recovery validates wallet material, requests acknowledgement, clears saved progress under the original settings key, then activates. Cancellation preserves the active wallet and progress.
- Keep pending shares out of seedless settings, backup, and teleport paths; require the 256-bit dice threshold; avoid signing unrelated share exports.
- Make the simulator harness fail on missing selections, child failures, timeouts, crashes, and incomplete evidence. Earlier failed diagnostic attempts were retained and not counted as passes.

## Qualification at the tagged commit

| Gate | Recorded result |
| --- | --- |
| Codex32 simulator, Mk4 / Mk5 / Q1 | 254 / 254 / 284 passed; zero failures or errors. Each Mk run excluded 30 Q1-only cases whose exact IDs passed on Q1. |
| Persistence | 27 of 27 save, restart, and discard stages passed across three independent process repetitions per model. |
| Host BIP 93, extension, harness, and dice tests | 385 passed; zero skipped, failed, or errored. |
| Pinned references | Python suite 23 passed; Rust suite 12 passed. Both comparisons covered 34 published valid and 55 invalid vectors. Python checked 1,200 generated cases and Rust 360, with zero disagreements within their documented common capabilities. |
| Supporting simulator lanes | Mk4 decoder 81, Mk5 paper/address 60, and Codex32 MicroPython unit tests 2 per model passed on the tagged source. Q1 live QR capture/decoding and wallet-identity flows were exercised. |
| Embedded firmware | MK (Mk4/Mk5) and Q1 targets compiled. Developer/test key 0 signatures and DFU containers were checked. An independent tagged checkout produced byte-identical unsigned firmware sections. |

Additional backup, Seed XOR, passphrase, UX, teleport, and signing regressions passed on earlier revisions with identical firmware source paths and simulator binary. They are **source-equivalent evidence**, not represented as reruns of every regression on the final commit. Their exact revisions and counts were recorded in the local qualification report.

## Review limits and evidence handoff

Recovery acknowledgement does not authenticate the reconstructed wallet. A user must compare a known address with the original network, derivation path, and address type. Simulator results do not establish physical RNG quality, secure-element behavior, flash erasure atomicity, or power-loss recovery. No hardware was flashed.

The qualification report, logs, signed test images, and release archive were generated locally and were not pushed with this Git branch. The original temporary artifact directory was subsequently cleaned, so a fresh artifact bundle is needed before maintainers can independently inspect the raw run evidence. The branch contains the pinned inputs, harness, test cases, and reproduction instructions. The tag identifies the source that was tested; the tag is not a production release claim.
