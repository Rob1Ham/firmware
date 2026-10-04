# Codex32 reference comparison contract

BIP 93 at `927b6de9915c9262615a6399de51b200f81e5aa4` is the normative MS1
source. Its pinned text SHA256 is
`c847c6e513b64ee6ab10975690757d64a875f77c0e75866a86b733f3985784ec`.
The Python and Rust references provide independent comparisons, within the
capabilities below. No majority vote can override a BIP 93 vector.

| Rule or operation | Firmware under test | Python 0.6.2 at `8ab3bae9` | Rust 0.1.0 at `1a1c22aa` |
| --- | --- | --- | --- |
| MS1 parsing and checksums | Six BIP 93 byte sizes: 16, 20, 24, 28, 32, 64 | Separate `decode('ms', encoded)` adapter, all six sizes | `Codex32String::from_string`, short/long checksum; parser accepts additional lengths without the firmware's MS1 profile filter |
| HRP | MS1 normative; CW1/CX1 separate firmware extensions | Adapter explicitly requests `ms`; no CW1/CX1 comparison | HRP-agnostic parser; an accepted non-MS string is outside the MS1 profile |
| Case, payload and padding | Uniform case; exact symbols preserved through round trip | Adapter reports decoded seed and legal padding separately | Adapter reports decoded seed bytes; the older API does not expose a padding value directly |
| Threshold recovery | Exactly k distinct matching shares | Reference suite exercises its own interpolation API; adapter currently compares decoding only | `interpolate_at` checks at least k, so over-threshold behavior is not an acceptance oracle for firmware's exact-k rule |
| Wallet roots | Published BIP 93 xprv vectors checked against firmware's BIP32 implementation | No external-wallet vote in adapter | No external-wallet vote in adapter |

The Python adapter runs under its own Python 3.11.5 environment, avoiding the
firmware test tree's `bip32.py` name collision. Its response records package
version, module path, commit, case ID, operation, result and exception class.
The Rust adapter compiles the pinned reference crate unchanged, reads one
Codex32 string per line, and reports decoded bytes or a structured parser
error. It also reports parser panics. Both comparison drivers verify the exact
reference checkout commit before running.

For the current integration, the Python suite passed 23 tests. The Python
differential checked 34 published valid vectors, 55 published invalid vectors
and 1,200 deterministic generated MS1 cases with zero disagreements. The Rust
suite passed 12 tests. The Rust differential checked the same 34 valid and
55 invalid vectors plus 360 generated cases with zero disagreements. The
machine-readable reports are under the local `artifacts/codex32/` directory.
