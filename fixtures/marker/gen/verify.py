"""verify.py — the independent marker oracle.

DELIBERATELY DECOUPLED from the construction side. This module retranscribes
every grammar-logical constant from marker-grammar-DRAFT.md as its OWN literal
so a construction-side bug in grammar.py cannot mask itself. It imports ONLY
bookkeeping fields from grammar.py (STATUS, GRAMMAR_REVISION,
EXPECTED_GRAMMAR_SHA256, ASSUMED_SCAN_CAPACITY, REASON_CODES) and NOTHING from
txkit.py or donor.py.

It carries its own from-scratch LEGACY-ONLY transaction parser (own SegWit
marker/flag abort, strict framing), its own Section 2 membership procedure
(classify_output), and its own Section 3 validity engine (verdict_tx).
"""

import struct

# Bookkeeping-only imports (Phase 4 whitelist). No layout constants.
from grammar import (
    STATUS,
    GRAMMAR_REVISION,
    EXPECTED_GRAMMAR_SHA256,
    ASSUMED_SCAN_CAPACITY,
    REASON_CODES,
)

# --- Grammar-logical literals, retranscribed from marker-grammar-DRAFT.md ---
# Each is its own copy; do NOT replace with a grammar.py import.
_MAGIC = b"\x45\x52\x47\x56"   # Section 1: ASCII "ERGV"
_VERSION = 0x01                # Section 1 payload table, offset 4
_ERGO_MAINNET = 0x01           # Section 1: 0x01 = Ergo mainnet
_ERGO_TESTNET = 0x02           # Section 1: 0x02 = Ergo testnet
_BTC_MAINNET = 0x01            # Section 1: 0x01 = Bitcoin mainnet
_BTC_TESTNET4 = 0x02           # Section 1: 0x02 = Bitcoin Testnet4 (BIP-94)
_PAYLOAD_LEN = 43              # Section 1: fixed total payload length
_DIRECT_PUSH = 0x2b            # Section 1: canonical direct push of 43 bytes
_SCRIPT_LEN = 45               # Section 1: 0x6a 0x2b + 43-byte payload
# Section 1 payload table field offsets (payload-relative):
_OFF_MAGIC = 0                 # offset 0, size 4
_OFF_VERSION = 4              # offset 4, size 1
_OFF_ERGO_NET = 5            # offset 5, size 1
_OFF_BTC_NET = 6             # offset 6, size 1
_OFF_VOUT = 7               # offset 7, size 4, uint32 LE decoded UNSIGNED
_OFF_VAULT_ID = 11          # offset 11, size 32

# Own copy of the reason-code enum (cross-checked against grammar.REASON_CODES).
_OWN_REASON_CODES = [
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


class UnsupportedSerializationError(ValueError):
    """Raised on a non-legacy (SegWit) serialization."""


class TxFramingError(ValueError):
    """Raised on truncated/over-long/incomplete transaction framing."""


def _read_compact_size(raw: bytes, off: int) -> tuple:
    """Strict CompactSize decode; return (value, next_offset)."""
    if off >= len(raw):
        raise TxFramingError("incomplete CompactSize prefix")
    first = raw[off]
    if first < 0xFD:
        return first, off + 1
    if first == 0xFD:
        if off + 3 > len(raw):
            raise TxFramingError("incomplete CompactSize (fd)")
        return struct.unpack_from("<H", raw, off + 1)[0], off + 3
    if first == 0xFE:
        if off + 5 > len(raw):
            raise TxFramingError("incomplete CompactSize (fe)")
        return struct.unpack_from("<I", raw, off + 1)[0], off + 5
    if off + 9 > len(raw):
        raise TxFramingError("incomplete CompactSize (ff)")
    return struct.unpack_from("<Q", raw, off + 1)[0], off + 9


def parse_legacy_tx(raw: bytes) -> dict:
    """From-scratch LEGACY-ONLY parser. Strict framing.

    Aborts on a SegWit marker/flag. Raises TxFramingError on truncation,
    incomplete CompactSize, or trailing bytes after locktime. Each output
    scriptPubKey is sliced EXACTLY by its outer CompactSize (Section 2
    script-slice boundary rule).
    """
    n = len(raw)
    if n < 4:
        raise TxFramingError("too short for version")
    off = 4  # skip 4-byte version

    # SegWit abort: 0x00 marker followed by a nonzero flag byte.
    if off + 1 < n and raw[off] == 0x00 and raw[off + 1] != 0x00:
        raise UnsupportedSerializationError(
            "unsupported serialization: SegWit marker/flag; legacy-only"
        )

    input_count, off = _read_compact_size(raw, off)
    for _ in range(input_count):
        if off + 36 > n:
            raise TxFramingError("truncated input outpoint")
        off += 36
        script_len, off = _read_compact_size(raw, off)
        if off + script_len > n:
            raise TxFramingError("truncated input scriptSig")
        off += script_len
        if off + 4 > n:
            raise TxFramingError("truncated input sequence")
        off += 4

    output_count_offset = off
    output_count, off = _read_compact_size(raw, off)
    outputs = []
    for _ in range(output_count):
        if off + 8 > n:
            raise TxFramingError("truncated output value")
        value = struct.unpack_from("<Q", raw, off)[0]
        off += 8
        script_len, off = _read_compact_size(raw, off)
        script_start = off
        if off + script_len > n:
            raise TxFramingError("truncated output script")
        # Exact script-slice boundary: outer CompactSize delimits the slice.
        script = raw[off:off + script_len]
        off += script_len
        outputs.append({
            "value": value,
            "script_start": script_start,
            "script": script,
        })

    locktime_offset = off
    if off + 4 > n:
        raise TxFramingError("truncated locktime")
    off += 4
    if off != n:
        raise TxFramingError("trailing bytes after locktime")

    return {
        "output_count_offset": output_count_offset,
        "output_count": output_count,
        "outputs": outputs,
        "locktime_offset": locktime_offset,
    }


def classify_output(script: bytes) -> tuple:
    """Section 2 membership + encoding for a single scriptPubKey slice.

    Returns (membership, encoding):
      membership in {IGNORED, CLAIMS}
      encoding   in {CANONICAL, NONCANONICAL, NOT_APPLICABLE}

    Implements the Section 2 detection procedure literally. Never allocates or
    skips declaredLength bytes: it only decodes enough of the length field to
    establish declaredLength >= 4 as unsigned, then checks four physical magic
    bytes at the first push start P.
    """
    # Rule 1: scriptPubKey begins with OP_RETURN.
    if len(script) < 1 or script[0] != 0x6a:
        return ("IGNORED", "NOT_APPLICABLE")

    # Rule 2: first push opcode → payload start P and declared length.
    if len(script) < 2:
        return ("IGNORED", "NOT_APPLICABLE")
    op = script[1]
    if 0x01 <= op <= 0x4b:                       # direct push
        declared = op
        P = 2
    elif op == 0x4c:                             # OP_PUSHDATA1
        if len(script) < 3:                      # incomplete length prefix
            return ("IGNORED", "NOT_APPLICABLE")
        declared = script[2]
        P = 3
    elif op == 0x4d:                             # OP_PUSHDATA2
        if len(script) < 4:                      # incomplete length prefix
            return ("IGNORED", "NOT_APPLICABLE")
        declared = script[2] | (script[3] << 8)  # unsigned LE
        P = 4
    elif op == 0x4e:                             # OP_PUSHDATA4
        if len(script) < 6:                      # incomplete length prefix
            return ("IGNORED", "NOT_APPLICABLE")
        # Unsigned LE: a high-bit value (0x80000004) stays positive.
        declared = (
            script[2]
            | (script[3] << 8)
            | (script[4] << 16)
            | (script[5] << 24)
        )
        P = 6
    else:                                        # not a data-push opcode
        return ("IGNORED", "NOT_APPLICABLE")

    # Rule 3: decoded declared length >= 4 (unsigned).
    if declared < 4:
        return ("IGNORED", "NOT_APPLICABLE")

    # Rule 4: four physical magic bytes present at P inside the slice.
    if len(script) < P + 4 or script[P:P + 4] != _MAGIC:
        return ("IGNORED", "NOT_APPLICABLE")

    # Magic present at the first push start → the output CLAIMS.
    # Rule 5 (truncation): a declared push extending beyond the slice still
    # CLAIMS (and is malformed under Section 3). No allocation performed.
    # Encoding: byte-exact 0x6a 0x2b + 43-byte payload is CANONICAL.
    if len(script) == _SCRIPT_LEN and op == _DIRECT_PUSH:
        return ("CLAIMS", "CANONICAL")
    return ("CLAIMS", "NONCANONICAL")


def verdict_tx(raw_tx: bytes, deal_context: dict) -> tuple:
    """Section 3 validity engine.

    Returns (grammar_verdict, reason_code, per_output) where:
      grammar_verdict in {NOT-A-SETTLEMENT, MALFORMED, VALID}
      reason_code is the FIRST failing Section 3 rule's code (None if VALID)
      per_output is the full [(membership, encoding), ...] list, computed for
                 EVERY output regardless of early tx-level failure.

    Deployment/deal facts come from deal_context (NOT imported):
      expected_ergo_net, expected_btc_net, expected_vault_id,
      committed_script, committed_sats.
    Scan capacity is NOT applied here — grammar truth only.
    """
    tx = parse_legacy_tx(raw_tx)
    outputs = tx["outputs"]
    output_count = tx["output_count"]

    # Labels for every output first (independent of tx-level outcome).
    per_output = [classify_output(o["script"]) for o in outputs]
    claimant_indices = [
        i for i, (m, _e) in enumerate(per_output) if m == "CLAIMS"
    ]

    # Rule 1: exactly one claimant across ALL outputs.
    if len(claimant_indices) == 0:
        return ("NOT-A-SETTLEMENT", "ZERO_CLAIMANTS", per_output)
    if len(claimant_indices) >= 2:
        return ("MALFORMED", "MULTIPLE_CLAIMANTS", per_output)

    marker_idx = claimant_indices[0]
    marker = outputs[marker_idx]
    _membership, encoding = per_output[marker_idx]

    # Rule 2: canonical byte form AND marker value == 0.
    if encoding != "CANONICAL":
        return ("MALFORMED", "NONCANONICAL_MARKER", per_output)
    if marker["value"] != 0:
        return ("MALFORMED", "NONZERO_MARKER_VALUE", per_output)

    # Canonical marker → its 43-byte payload is script[2:45].
    payload = marker["script"][2:2 + _PAYLOAD_LEN]

    # Rule 3: version.
    if payload[_OFF_VERSION] != _VERSION:
        return ("MALFORMED", "VERSION_MISMATCH", per_output)

    # Rule 4: both networks vs deployment constants (from deal_context).
    if payload[_OFF_ERGO_NET] != deal_context["expected_ergo_net"]:
        return ("MALFORMED", "ERGO_NETWORK_MISMATCH", per_output)
    if payload[_OFF_BTC_NET] != deal_context["expected_btc_net"]:
        return ("MALFORMED", "BITCOIN_NETWORK_MISMATCH", per_output)

    # Rule 5: vault_id.
    vault_id = payload[_OFF_VAULT_ID:_OFF_VAULT_ID + 32]
    if vault_id != deal_context["expected_vault_id"]:
        return ("MALFORMED", "VAULT_ID_MISMATCH", per_output)

    # Rule 6: vout unsigned, in range, and != marker index.
    vout = struct.unpack_from("<I", payload, _OFF_VOUT)[0]  # unsigned uint32 LE
    if vout >= output_count:
        return ("MALFORMED", "VOUT_OUT_OF_RANGE", per_output)
    if vout == marker_idx:
        return ("MALFORMED", "VOUT_IS_MARKER", per_output)

    # Rule 7: outputs[vout] SPECIFICALLY pays committed script >= committedSats.
    paid = outputs[vout]
    if paid["script"] != deal_context["committed_script"]:
        return ("MALFORMED", "PAYMENT_SCRIPT_MISMATCH", per_output)
    if paid["value"] < deal_context["committed_sats"]:
        return ("MALFORMED", "PAYMENT_AMOUNT_TOO_LOW", per_output)

    return ("VALID", None, per_output)


def self_test() -> None:
    # (f) reason-code cross-check first (used implicitly by everything else).
    assert _OWN_REASON_CODES == list(REASON_CODES), "reason-code enum drift"

    # (a) declared-empty PUSHDATA1 push; magic physically after does not claim.
    assert classify_output(bytes.fromhex("6a4c0045524756")) == \
        ("IGNORED", "NOT_APPLICABLE")

    # (b) unsigned PUSHDATA4 decode of 0x80000004 → CLAIMS, NONCANONICAL.
    assert classify_output(bytes.fromhex("6a4e0400008045524756")) == \
        ("CLAIMS", "NONCANONICAL")

    # (c) vault_id byte-order vector: literal-hex payload, no reversal anywhere.
    payload_hex = (
        "4552475601010101000000"
        "00112233445566778899aabbccddeeff00112233445566778899aabbccddeeff"
    )
    payload = bytes.fromhex(payload_hex)
    assert len(payload) == _PAYLOAD_LEN, len(payload)
    displayed_id = (
        "00112233445566778899aabbccddeeff00112233445566778899aabbccddeeff"
    )
    assert payload[11] == 0x00
    assert payload[11:43] == bytes.fromhex(displayed_id)  # NO reversal

    # (d) donor re-parse anchors, with THIS file's own parser (donor hex is a
    #     literal here; donor.py is NOT imported).
    donor_hex = (
        "0100000001754ed03940f9373d6796cc9b1dc97e6d06097f9aa5e2f8c5604f90e64d"
        "53e340010000006b483045022100a4347c689b6698079a5cb53189212a0fdc7037b0"
        "b3b22d557c2b84e4009bbaa1022028749cc4086a88bf60b7863e87614ce3235385c21"
        "46497977ce33f99458d0c300121039abf21fc7e635c52970010333ed867aee862f698"
        "5f019ec37ea23d2376d988fbffffffff02204e0000000000001976a9143f53b874d77"
        "6eea1da76b623c5bb4c43c2ff9d6e88ac0000000000000000266a244669727374204f"
        "5052657475726e204d6573736167652049207761732068657265203a2900000000"
    )
    donor = bytes.fromhex(donor_hex)
    tx = parse_legacy_tx(donor)
    assert tx["output_count_offset"] == 153, tx["output_count_offset"]
    assert tx["output_count"] == 2, tx["output_count"]
    out0, out1 = tx["outputs"]
    assert out0["value"] == 20000, out0["value"]
    assert out0["script_start"] == 163, out0["script_start"]
    assert len(out0["script"]) == 25, len(out0["script"])
    assert out0["script_start"] + len(out0["script"]) == 188
    assert len(out1["script"]) == 38, len(out1["script"])
    assert out1["script"][1] == 0x24, out1["script"][1]
    assert tx["locktime_offset"] == 235, tx["locktime_offset"]

    # (e) SegWit abort.
    segwit = b"\x01\x00\x00\x00" + b"\x00\x01" + b"\xde\xad\xbe\xef"
    try:
        parse_legacy_tx(segwit)
    except UnsupportedSerializationError:
        pass
    else:
        raise AssertionError("SegWit serialization was not rejected")

    print("verify.self_test: OK")


if __name__ == "__main__":
    self_test()
