"""Marker construction constants and canonical builders (primitive facts only).

This module holds the CONSTRUCTION side of the marker grammar: the field
layout, magic/version/network constants, and the two canonical builders. It is
imported by families.py and generate.py. verify.py (the independent oracle)
does NOT import layout constants from here; it retranscribes them from
marker-grammar-DRAFT.md and may import only the bookkeeping fields.

No layout magic numbers are written as literals: PAYLOAD_LEN, PUSH_OPCODE, and
SCRIPT_LEN are all derived from FIELDS. The one hardcoded literal in this file
is the canonical-marker golden in self_test, which is an independently computed
transcription used to catch construction drift.
"""

import struct

# --- Primitive protocol constants (marker-grammar-DRAFT.md Section 1) ---
MAGIC = b"ERGV"                 # ASCII "ERGV" = 0x45 0x52 0x47 0x56
VERSION = 0x01

# Network enums (Section 1 payload table).
ERGO_NET_MAINNET = 0x01
ERGO_NET_TESTNET = 0x02
BTC_NET_MAINNET = 0x01          # Bitcoin mainnet
BTC_NET_TESTNET4 = 0x02         # Bitcoin Testnet4 (BIP-94)

# --- Field layout; everything dimensional derives from this. ---
FIELDS = [
    ("magic", 4),
    ("version", 1),
    ("ergo_net", 1),
    ("btc_net", 1),
    ("vout", 4),
    ("vault_id", 32),
]

_sizes = [size for _, size in FIELDS]

# Cumulative-sum offsets, keyed by field name (payload-relative).
OFFSETS = {}
_acc = 0
for _name, _size in FIELDS:
    OFFSETS[_name] = _acc
    _acc += _size

PAYLOAD_LEN = sum(_sizes)
assert PAYLOAD_LEN <= 0x4b, "payload exceeds direct-push range (0x4b)"
PUSH_OPCODE = PAYLOAD_LEN               # direct push of PAYLOAD_LEN bytes
SCRIPT_LEN = PAYLOAD_LEN + 2            # OP_RETURN + push opcode + payload

# --- Bookkeeping fields (verify.py imports these; not layout-logical). ---
STATUS = "PRE-FREEZE"
GRAMMAR_REVISION = "v3"
EXPECTED_GRAMMAR_SHA256 = (
    "65e0e0ef71a80a627fd7163aa9edf6d9539d0f142309e2ee6efee841630bc893"
)

# --- Deployment constants (this fixture set's deal context). ---
DEPLOY_ERGO_NET = 0x01          # Ergo mainnet
DEPLOY_BTC_NET = 0x01           # Bitcoin mainnet

ASSUMED_SCAN_CAPACITY = 300

EXPECTED_VAULT_ID = bytes.fromhex("00112233445566778899aabbccddeeff" * 2)

# Near-miss magics for the first-push / namespace negatives (N6f/g/h).
# Computed from MAGIC, never written as literals.
NEAR_MISS_MAGICS = [
    MAGIC[:3] + bytes([MAGIC[3] + 1]),   # ERGW
    MAGIC[:3] + bytes([MAGIC[3] - 1]),   # ERGU
    MAGIC.lower(),                        # ergv
]

# Fixed reason-code enum (Section 3). The shared list; verify.py cross-checks
# its own copy against this.
REASON_CODES = [
    "ZERO_CLAIMANTS",
    "MULTIPLE_CLAIMANTS",
    "NONCANONICAL_MARKER",
    "NONZERO_MARKER_VALUE",
    "VERSION_MISMATCH",
    "ERGO_NETWORK_MISMATCH",
    "BITCOIN_NETWORK_MISMATCH",
    "VAULT_ID_MISMATCH",
    "VOUT_OUT_OF_RANGE",
    "VOUT_IS_MARKER",
    "PAYMENT_SCRIPT_MISMATCH",
    "PAYMENT_AMOUNT_TOO_LOW",
]


def build_canonical_payload(vout: int, vault_id: bytes) -> bytes:
    """Assemble the 43-byte payload in FIELDS order.

    magic/version/networks come from this module's deployment constants; vout
    is packed uint32 LE unsigned ("<I"); vault_id is spliced raw (no reversal).
    """
    if len(vault_id) != 32:
        raise ValueError("vault_id must be 32 bytes")
    values = {
        "magic": MAGIC,
        "version": bytes([VERSION]),
        "ergo_net": bytes([DEPLOY_ERGO_NET]),
        "btc_net": bytes([DEPLOY_BTC_NET]),
        "vout": struct.pack("<I", vout),
        "vault_id": vault_id,
    }
    parts = []
    for name, size in FIELDS:
        chunk = values[name]
        assert len(chunk) == size, f"field {name} wrong size"
        parts.append(chunk)
    payload = b"".join(parts)
    assert len(payload) == PAYLOAD_LEN, "assembled payload wrong length"
    return payload


def build_canonical_marker_script(payload: bytes) -> bytes:
    """Canonical marker scriptPubKey: OP_RETURN + direct push + payload."""
    assert len(payload) == PAYLOAD_LEN, "payload wrong length for canonical push"
    return bytes([0x6a, PUSH_OPCODE]) + payload


def self_test() -> None:
    # Derived-dimension sanity.
    assert OFFSETS == {
        "magic": 0, "version": 4, "ergo_net": 5, "btc_net": 6,
        "vout": 7, "vault_id": 11,
    }, OFFSETS
    assert PAYLOAD_LEN == 43, PAYLOAD_LEN
    assert PUSH_OPCODE == 0x2b, PUSH_OPCODE
    assert SCRIPT_LEN == 45, SCRIPT_LEN

    # CANONICAL-MARKER GOLDEN: independently computed and verified 2026-07-11,
    # transcribed here as a literal (NOT regenerated from this module's own
    # constants). Catches wrong field order, wrong deployment network bytes,
    # wrong vault id, and wrong offsets at correct total length.
    golden = (
        "6a2b455247560101010100000000112233445566778899aabbccddeeff"
        "00112233445566778899aabbccddeeff"
    )
    built = build_canonical_marker_script(
        build_canonical_payload(1, EXPECTED_VAULT_ID)
    )
    assert built.hex() == golden, built.hex()

    # Near-miss magics are the expected near-values of "ERGV".
    assert NEAR_MISS_MAGICS[0] == b"ERGW", NEAR_MISS_MAGICS[0]
    assert NEAR_MISS_MAGICS[1] == b"ERGU", NEAR_MISS_MAGICS[1]
    assert NEAR_MISS_MAGICS[2] == b"ergv", NEAR_MISS_MAGICS[2]

    print("grammar.self_test: OK")


if __name__ == "__main__":
    self_test()
