# (c) Copyright 2026. Vault co-signer policy engine (CCC extension).
#
# Pure-python decision core for REV3_PROTOCOL_DRAFT.md (branched P2WSH vault S_v +
# emergency deepvault S_e). No device imports: runs on host (CPython) and target
# (MicroPython) so the exact signing rules can be unit-tested off-device.
#
# Enforces, for CCC key K3:
#   P1  emergency shape: 1-in/1-out to spk_e, out == in-F, 0 < F <= f0_max,
#       all nSequence == 0xFFFFFFFD, nLockTime == 0.
#   P2  spend-forbid: never sign a spend of spk_e...
#   P3  ...except the exit ceremony: 1-in(spk_e)/1-out to exit_dest, fee-bounded,
#       K1 partial sig already present in the PSBT.
#   INV-SEQ: vault-ladder spends commit nSequence == N (height-form CSV only).
#
# Also includes structural parsers for the S_v / S_e witness scripts
# (INV-BRANCH, INV-KEYLESS: recompute, never trust).

try:
    from uhashlib import sha256 as _sha256
except ImportError:
    from hashlib import sha256 as _sha256

OP_IF, OP_ELSE, OP_ENDIF = 0x63, 0x67, 0x68
OP_DROP = 0x75
OP_CLTV, OP_CSV = 0xB1, 0xB2
OP_CMS, OP_CSV_VER = 0xAE, 0xAD

SEQ_EMERGENCY = 0xFFFFFFFD          # CSV disable flag set, RBF on
SEQ_DISABLE_FLAG = 1 << 31
SEQ_TYPE_TIME = 1 << 22
SEQ_VALUE_MASK = 0xFFFF

TAPROOT_LEAF_VERSION_TAPSCRIPT = 0xC0

MAX_CSV_BLOCKS = 0xFFFF             # 16-bit height-form CSV; ~455 days max


class VaultViolation(Exception):
    pass


def decode_opcode(script, pos):
    # Return (opcode_int, payload, next_pos); payload is bytes or None.
    op = script[pos]
    pos += 1
    if 1 <= op <= 75:
        n = op
        if pos + n > len(script):
            raise VaultViolation("push past end")
        return op, script[pos:pos + n], pos + n
    if op == 0x4c:  # PUSHDATA1
        n = script[pos]
        pos += 1
        if pos + n > len(script):
            raise VaultViolation("push past end")
        return op, script[pos:pos + n], pos + n
    return op, None, pos


def push_number(b):
    # Minimal script-num encode of non-negative int b (CSV operand).
    if b == 0:
        return b""
    res = bytearray()
    while b:
        res.append(b & 0xFF)
        b >>= 8
    if res[-1] & 0x80:
        res.append(0)
    return bytes(res)


def decode_pushnum(payload):
    # Script-num decode of a 0..65535 push.
    if not payload:
        return 0
    n = 0
    for i, c in enumerate(payload):
        n |= c << (8 * i)
    n &= 0x7FFFFFFF & (0xFF << (8 * (len(payload) - 1))) | 0x7FFFFFFF >> (
        8 * (4 * 0)) if False else n  # keep simple: sign bit handled below
    if payload[-1] & 0x80:
        n &= ~(0x80 << (8 * (len(payload) - 1)))
        raise VaultViolation("negative pushnum")
    return n


def _expect(script, pos, op):
    if pos >= len(script) or script[pos] != op:
        raise VaultViolation("expect op_%02x" % op)
    return pos + 1


def _expect_pubkey(script, pos):
    op, payload, pos2 = decode_opcode(script, pos)
    if op != 33 or len(payload) != 33 or payload[0] not in (0x02, 0x03):
        raise VaultViolation("not a compressed pubkey")
    return payload, pos2


def parse_vault_script(wscript):
    # Structural parse of S_v (D-1'): OP_IF <N> OP_CSV OP_DROP <empty ELSE> OP_ENDIF
    #   OP_2 <K1> <K2> <K3> OP_3 OP_CHECKMULTISIG
    # INV-KEYLESS: both branches fall into the shared 2-of-3; the truthy branch ends
    # in CSV DROP (no bare OP_1 posture). Returns dict(n=..., keys=(k1,k2,k3)).
    if not wscript or len(wscript) > 140 or len(wscript) < 111:
        raise VaultViolation("S_v size out of range")
    pos = _expect(wscript, 0, OP_IF)
    op, payload, pos = decode_opcode(wscript, pos)
    if op == OP_IF + 0 or payload is None:
        raise VaultViolation("S_v: no N push")
    n = decode_pushnum(payload)
    if not (1 <= n <= MAX_CSV_BLOCKS):
        if payload:
            raise VaultViolation("S_v: N range")
    pos = _expect(wscript, pos, OP_CSV)
    pos = _expect(wscript, pos, OP_DROP)
    pos = _expect(wscript, pos, OP_ELSE)     # empty ELSE branch (deepvault exit sits at OP_ENDIF)
    pos = _expect(wscript, pos, OP_ENDIF)
    pos = _expect(wscript, pos, 0x52)        # OP_2
    k1, pos = _expect_pubkey(wscript, pos)
    k2, pos = _expect_pubkey(wscript, pos)
    k3, pos = _expect_pubkey(wscript, pos)
    pos = _expect(wscript, pos, 0x53)        # OP_3
    _expect(wscript, pos, OP_CMS)
    return dict(n=n, keys=(k1, k2, k3))


def parse_deepvault_script(wscript):
    # Structural parse of S_e (E-2): <K1> OP_CHECKSIGVERIFY OP_1 <K2> <K3> OP_2 OP_CMS
    if not wscript or len(wscript) != 106:
        raise VaultViolation("S_e size")
    k1, pos = _expect_pubkey(wscript, 0)
    pos = _expect(wscript, pos, OP_CSV_VER)
    pos = _expect(wscript, pos, 0x51)        # OP_1
    k2, pos = _expect_pubkey(wscript, pos)
    k3, pos = _expect_pubkey(wscript, pos)
    pos = _expect(wscript, pos, 0x52)        # OP_2
    _expect(wscript, pos, OP_CMS)
    return dict(k1=k1, k2=k2, k3=k3)


def p2wsh_spk(wscript):
    return b"\x00\x20" + _sha256(wscript).digest()


def sequence_class(seq):
    # 'emergency' | ('csv', n) | 'plain' | refuse time-form CSV
    if seq == SEQ_EMERGENCY:
        return ("emergency", 0)
    if seq & SEQ_DISABLE_FLAG:
        return ("plain", 0)
    if seq & SEQ_TYPE_TIME:
        return ("csv_time", 0)
    return ("csv", seq & SEQ_VALUE_MASK)


class VaultPolicy:
    # Decision object built from a plain dict (NVS-serializable):
    #   n, spk_v (hex), spk_e (hex), k1 (hex pubkey), f0_max, exit_dest (hex spk')
    def __init__(self, d):
        _h = lambda k: bytes(bytearray.fromhex(d[k])) if d.get(k) else None
        self.spk_v, self.spk_e, self.k1 = _h("sv_hash"), _h("spk_e"), _h("k1_pubkey")
        self.exit_dest = _h("exit_spk")
        self.n = d.get("n", 1008)
        self.f0_max = d.get("f0_max", 10000)

    def _classify(self, view):
        # view = {lock_time:int, inputs:[...], outputs:[...]}
        spends_e = any(i["spk"] == self.spk_e for i in view["inputs"])
        seqs = [i["sequence"] for i in view["inputs"]]
        if all(s == SEQ_EMERGENCY for s in seqs):
            return "exit" if spends_e else "emergency"
        for i in view["inputs"]:
            if i["spk"] == self.spk_v or spends_e:
                if spends_e:
                    return "exit"
        for s in seqs:
            cls, _n = sequence_class(s)
            if cls == "csv":
                return "ladder"
        return "other"

    def check(self, view):
        # Raise VaultViolation to block; return description string otherwise.
        if view["lock_time"] != 0:
            # sequences that disable CSV with set locktime = "Bad Locktime" shape
            if all(sequence_class(s)[0] != "csv" for s in
                   [i["sequence"] for i in view["inputs"]]):
                raise VaultViolation("locktime/sequence shape")
        kind = self._classify(view)
        if kind == "emergency":
            return self._check_emergency(view)
        if kind == "exit":
            return self._check_exit(view)
        if kind == "ladder":
            return self._check_ladder(view)
        raise VaultViolation("not a recognized vault class")

    def _check_emergency(self, view):
        # P1: exact sink shape
        if len(view["inputs"]) != 1:
            raise VaultViolation("P1: 1 input")
        if len(view["outputs"]) != 1:
            raise VaultViolation("P1: 1 output")
        out = view["outputs"][0]
        if out["spk"] != self.spk_e or out["is_change"]:
            raise VaultViolation("P1: dest")
        if view["inputs"][0]["spk"] != self.spk_v:
            raise VaultViolation("P1: must spend the vault")
        if view["lock_time"] != 0:
            raise VaultViolation("P1: locktime")
        for i in view["inputs"]:
            if sequence_class(i["sequence"])[0] != "emergency":
                raise VaultViolation("P1: sequence")
        fee = view["inputs"][0]["value"] - out["value"]
        if not (0 < fee <= self.f0_max):
            raise VaultViolation("P1: fee")
        return "emergency F=%d" % fee

    def _check_ladder(self, view):
        # INV-SEQ: vault spends are cadence-committed; N exactly, height form only.
        for i in view["inputs"]:
            if i["spk"] != self.spk_v:
                continue
            cls, n = sequence_class(i["sequence"])
            if cls == "csv_time":
                raise VaultViolation("SEQ: time-form refused")
            if cls != "csv" or n != self.n:
                raise VaultViolation("SEQ: nSequence != N")
        spent = sum(i["value"] for i in view["inputs"] if i["spk"] == self.spk_v)
        if any(o["spk"] == self.spk_v for o in view["outputs"]):
            return "ladder: state transition (%d sats spent)" % spent
        return "ladder: withdrawal (%d sats spent)" % spent

    def _check_exit(self, view):
        # P2 default-refuse; P3 the single exception.
        if view.get("no_exit"):
            raise VaultViolation("P2: sink spend forbidden")
        if len(view["inputs"]) != 1 or len(view["outputs"]) != 1:
            raise VaultViolation("P3: ceremonies are 1-in/1-out")
        if view["outputs"][0]["spk"] != self.exit_dest:
            raise VaultViolation("P3: must re-enroll to fresh spk_v'")
        fee = view["inputs"][0]["value"] - view["outputs"][0]["value"]
        if not (0 < fee <= self.f0_max):
            raise VaultViolation("P3: fee")
        # belt-and-braces behind the E-2 script: K1's sig must already be present
        if not any(self.k1 in (i.get("part_sigs") or []) for i in view["inputs"]):
            raise VaultViolation("P3: K1 co-signature required")
        return "exit ceremony F=%d" % fee
