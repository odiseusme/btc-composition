"""verify.py — the independent marker oracle.

DELIBERATELY DECOUPLED from the construction side. This module retranscribes
every grammar-logical constant from marker-grammar-DRAFT.md as its OWN literal
so a construction-side bug in grammar.py cannot mask itself. It imports ONLY
bookkeeping fields from grammar.py (STATUS, GRAMMAR_REVISION,
EXPECTED_GRAMMAR_SHA256, ASSUMED_SCAN_CAPACITY, REASON_CODES) and NOTHING from
txkit.py or donor.py. The Section 7 profile bounds are likewise retranscribed
here, NOT imported from grammar.PROFILE_SIGMASTATE_V1.

It carries its own from-scratch STRIPPED (NON-WITNESS) transaction parser (own
BIP144 marker/flag abort, strict framing), its own Section 2 membership
procedure (classify_output), its own Section 3 validity engine (verdict_tx),
and its own Section 7 profile classifier (classify_profile).

TWO LAYERS (Section 7). verdict_tx computes the ABSTRACT GRAMMAR VERDICT and
knows nothing about any implementation bound. classify_profile answers the
separate question "is this transaction in profile for sigmastate-v1?" and is
deliberately TOLERANT: it CLASSIFIES rather than aborting, so an out-of-profile
transaction (e.g. the full BIP144 witness form) yields a violations list
instead of an exception. The strict semantic path used by verdict_tx keeps its
rejection behavior unchanged.
"""

import hashlib
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

# Section 3 rule 7: the 21M BTC supply bound in satoshi (21e14). Own literal,
# integer arithmetic only — never a float.
_SUPPLY_BOUND_SATS = 2_100_000_000_000_000
_COMMITTED_HASH_HEX_LEN = 64        # Section 3 rule 7: 64 lowercase hex chars
_HEX_LOWER = "0123456789abcdef"     # Section 3 rule 7: lowercase charset only

# Section 7 profile bounds for "sigmastate-v1". Own literals, retranscribed
# from the document; NOT imported from grammar.PROFILE_SIGMASTATE_V1.
# generate.py cross-checks every one of these against grammar.py at each run.
_PROFILE_NAME = "sigmastate-v1"
_PROFILE_STRIPPED_ONLY = True       # Section 7 item 1: stripped/non-witness only
_PROFILE_MIN_INPUTS = 1             # Section 7 item 2: inputCount in {1, 2}
_PROFILE_MAX_INPUTS = 2             # Section 7 item 2
_PROFILE_MIN_OUTPUTS = 1            # Section 7 item 3: outputCount in {1..4}
_PROFILE_MAX_OUTPUTS = 4            # Section 7 item 3: scan capacity 4
_PROFILE_COMPACTSIZE_SINGLE_BYTE = True   # Section 7 item 4: every field < 0xfd
_PROFILE_COMPACTSIZE_MAX = 0xFD     # Section 7 item 4: single-byte, i.e. < 0xfd

# Section 7 profile constraint item numbers (the fixed order for the
# violations list; a transaction violating several records ALL of them).
_PROFILE_ITEM_STRIPPED = 1          # item 1: stripped/non-witness only
_PROFILE_ITEM_INPUTS = 2            # item 2: inputCount bounds
_PROFILE_ITEM_OUTPUTS = 3           # item 3: outputCount bounds
_PROFILE_ITEM_COMPACTSIZE = 4       # item 4: every CompactSize single-byte

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
    """Raised on a full BIP144 witness serialization.

    Section 1: the operative form is the STRIPPED (non-witness) serialization —
    the txid preimage. SegWit PAYMENTS remain fully verifiable in that form;
    what is unsupported is the witness serialization itself, which MUST be
    rejected rather than misparsed. "stripped/non-witness serialization only",
    not "legacy-only".
    """


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


def parse_stripped_tx(raw: bytes) -> dict:
    """From-scratch STRIPPED (non-witness) parser. Strict framing.

    This is the STRICT semantic path (used by verdict_tx): it aborts on the
    BIP144 marker/flag rather than misparsing it. Raises TxFramingError on
    truncation, incomplete CompactSize, or trailing bytes after locktime. Each
    output scriptPubKey is sliced EXACTLY by its outer CompactSize (Section 2
    script-slice boundary rule).

    classify_profile does NOT use this path — it has its own tolerant shape
    scanner, so that an out-of-profile witness transaction can be CLASSIFIED
    (violation item 1) instead of raising through the profile layer.
    """
    n = len(raw)
    if n < 4:
        raise TxFramingError("too short for version")
    off = 4  # skip 4-byte version

    # BIP144 abort: 0x00 marker followed by a nonzero flag byte. Section 1:
    # stripped/non-witness serialization only.
    if off + 1 < n and raw[off] == 0x00 and raw[off + 1] != 0x00:
        raise UnsupportedSerializationError(
            "unsupported serialization: BIP144 witness marker/flag; "
            "stripped/non-witness serialization only"
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


def _is_valid_committed_hash_text(text) -> bool:
    """Section 3 rule 7: exactly 64 LOWERCASE hex characters, nothing else.

    Length AND charset are both checked (uppercase hex is rejected — the
    document pins the text form). Returns a bool; never raises, so a malformed
    deal context fails the predicate closed rather than crashing the verifier.
    """
    if not isinstance(text, str):
        return False
    if len(text) != _COMMITTED_HASH_HEX_LEN:
        return False
    return all(c in _HEX_LOWER for c in text)


def _scan_shape(raw: bytes) -> dict:
    """TOLERANT structural shape scan for the Section 7 profile layer.

    Deliberately separate from parse_stripped_tx: this one does NOT reject the
    BIP144 witness form, it RECORDS it (so classify_profile can report item 1
    as a violation rather than raising). It extracts only what the profile
    needs — witness-form flag, input/output counts, and whether EVERY
    CompactSize field in the transaction is single-byte — and ignores script
    semantics entirely.

    Raises TxFramingError only when the bytes cannot be decoded structurally at
    all (truncation, incomplete CompactSize, trailing bytes).
    """
    n = len(raw)
    if n < 4:
        raise TxFramingError("too short for version")
    off = 4  # version

    # Every CompactSize seen anywhere in the transaction; profile item 4
    # requires all of them to be single-byte (< 0xfd).
    multibyte_compactsize = False

    def read_cs(o):
        nonlocal multibyte_compactsize
        if o >= n:
            raise TxFramingError("incomplete CompactSize prefix")
        if raw[o] >= _PROFILE_COMPACTSIZE_MAX:
            multibyte_compactsize = True
        return _read_compact_size(raw, o)

    # BIP144 witness form: 0x00 marker + NONZERO flag after the version. Note
    # the byte-level ambiguity: a stripped transaction with ZERO inputs and a
    # nonzero output count is indistinguishable from the witness marker/flag,
    # so it is read as the witness form here (and then either decodes as one,
    # violating item 1, or fails to decode at all). Both outcomes are fail-
    # closed; no such transaction can be in profile, which needs >= 1 input.
    is_witness = off + 1 < n and raw[off] == 0x00 and raw[off + 1] != 0x00
    if is_witness:
        off += 2  # skip marker + flag

    input_count, off = read_cs(off)
    for _ in range(input_count):
        if off + 36 > n:
            raise TxFramingError("truncated input outpoint")
        off += 36
        script_len, off = read_cs(off)          # scriptSig length
        if off + script_len > n:
            raise TxFramingError("truncated input scriptSig")
        off += script_len
        if off + 4 > n:
            raise TxFramingError("truncated input sequence")
        off += 4

    output_count, off = read_cs(off)
    for _ in range(output_count):
        if off + 8 > n:
            raise TxFramingError("truncated output value")
        off += 8
        script_len, off = read_cs(off)          # scriptPubKey length
        if off + script_len > n:
            raise TxFramingError("truncated output script")
        off += script_len

    if is_witness:
        # Witness stacks: one per input, each a CompactSize item count followed
        # by CompactSize-prefixed items. Walked only so that item 4 covers
        # EVERY CompactSize in the transaction and framing stays checkable.
        for _ in range(input_count):
            item_count, off = read_cs(off)
            for _ in range(item_count):
                item_len, off = read_cs(off)
                if off + item_len > n:
                    raise TxFramingError("truncated witness item")
                off += item_len

    if off + 4 > n:
        raise TxFramingError("truncated locktime")
    off += 4
    if off != n:
        raise TxFramingError("trailing bytes after locktime")

    return {
        "is_witness": is_witness,
        "input_count": input_count,
        "output_count": output_count,
        "multibyte_compactsize": multibyte_compactsize,
    }


def classify_profile(raw_tx: bytes) -> tuple:
    """Section 7: is this transaction IN PROFILE for "sigmastate-v1"?

    Returns (in_profile: bool, violations: list[int]) where violations lists
    EVERY violated constraint, as Section 7 item numbers in the fixed document
    order 1-4 (deterministic across implementations); it is empty iff
    in_profile is True.

    This CLASSIFIES; it does not abort. Out-of-profile transactions — the full
    BIP144 witness form (item 1), a multibyte CompactSize (item 4), and so on —
    return a violations list rather than raising. Only bytes too mangled to
    decode structurally at all propagate a TxFramingError.

    The profile verdict is a SEPARATE LAYER from the grammar verdict: it is
    equal to the grammar verdict when in profile, else REJECT-OUT-OF-PROFILE.
    Rejecting out of profile is fail-closed and always safe; it is never a
    grammar result. Note that vout is NOT a profile constraint (Section 7): in
    an in-profile transaction, vout >= 4 is necessarily MALFORMED under rule 6.
    """
    shape = _scan_shape(raw_tx)
    violations = []

    # Item 1: stripped (non-witness) serialization only.
    if _PROFILE_STRIPPED_ONLY and shape["is_witness"]:
        violations.append(_PROFILE_ITEM_STRIPPED)

    # Item 2: inputCount in {1, 2}.
    if not (_PROFILE_MIN_INPUTS <= shape["input_count"] <= _PROFILE_MAX_INPUTS):
        violations.append(_PROFILE_ITEM_INPUTS)

    # Item 3: outputCount in {1, 2, 3, 4} (scan capacity 4).
    if not (_PROFILE_MIN_OUTPUTS <= shape["output_count"]
            <= _PROFILE_MAX_OUTPUTS):
        violations.append(_PROFILE_ITEM_OUTPUTS)

    # Item 4: every CompactSize field single-byte (< 0xfd).
    if _PROFILE_COMPACTSIZE_SINGLE_BYTE and shape["multibyte_compactsize"]:
        violations.append(_PROFILE_ITEM_COMPACTSIZE)

    return (len(violations) == 0, violations)


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
      committed_script_hash (64 lowercase hex chars), committed_sats.
    Scan capacity is NOT applied here — grammar truth only, and the Section 7
    profile layer is not applied here either (see classify_profile).
    """
    tx = parse_stripped_tx(raw_tx)
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

    # Rule 7: outputs[vout] SPECIFICALLY satisfies the committed-payment
    # predicate, in the composed-vault ABI form:
    #     SHA256(outputs[vout].scriptPubKey) == committedScriptHash
    #     AND outputs[vout].value >= committedSats
    # NAMED OUTPUT ONLY: the predicate is applied to outputs[vout] and never
    # falls back to searching any other output for a match — "vout in range AND
    # some output matches" is the anyOutputMatches behavior this marker exists
    # to eliminate.
    #
    # REASON-CODE MAPPING (no new codes; the enum is fixed at twelve):
    #   PAYMENT_SCRIPT_MISMATCH  — script-domain failures ONLY: an empty
    #       scriptPubKey, a malformed committed-hash text, or a hash mismatch.
    #   PAYMENT_AMOUNT_TOO_LOW   — ALL amount-domain failures: committedSats
    #       outside (0, supply bound], an output value above the supply bound,
    #       or an output value below committedSats.
    #
    # All arithmetic is integer (Python ints); no float ever touches a satoshi.
    paid = outputs[vout]
    script = paid["script"]
    value = paid["value"]
    committed_sats = deal_context["committed_sats"]

    # Guard: non-empty scriptPubKey (script domain).
    if len(script) == 0:
        return ("MALFORMED", "PAYMENT_SCRIPT_MISMATCH", per_output)

    # Guard: 0 < committedSats <= supply bound (amount domain).
    if not (0 < committed_sats <= _SUPPLY_BOUND_SATS):
        return ("MALFORMED", "PAYMENT_AMOUNT_TOO_LOW", per_output)

    # Guard: the parsed output value is itself within the supply bound.
    if value > _SUPPLY_BOUND_SATS:
        return ("MALFORMED", "PAYMENT_AMOUNT_TOO_LOW", per_output)

    # Pays-at-least (amount domain).
    if value < committed_sats:
        return ("MALFORMED", "PAYMENT_AMOUNT_TOO_LOW", per_output)

    # The hash predicate (script domain). committed_script_hash is carried as
    # text: exactly 64 lowercase hex chars, validated for length AND charset,
    # then decoded to the 32 raw bytes before comparison. The digest is a
    # SINGLE SHA-256 over the raw scriptPubKey slice exactly as it appears in
    # the output — no CompactSize length prefix, no byte reversal, no second
    # hash. A malformed hash text is a script-domain failure, never an
    # exception: fail closed.
    committed_hash_text = deal_context["committed_script_hash"]
    if not _is_valid_committed_hash_text(committed_hash_text):
        return ("MALFORMED", "PAYMENT_SCRIPT_MISMATCH", per_output)
    committed_hash = bytes.fromhex(committed_hash_text)
    if hashlib.sha256(script).digest() != committed_hash:
        return ("MALFORMED", "PAYMENT_SCRIPT_MISMATCH", per_output)

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

    # (d) donor re-parse anchors, with THIS file's own strict parser (donor hex
    #     is a literal here; donor.py is NOT imported).
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
    tx = parse_stripped_tx(donor)
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

    # (e) BIP144 witness-form abort on the STRICT path (unchanged behavior).
    segwit = b"\x01\x00\x00\x00" + b"\x00\x01" + b"\xde\xad\xbe\xef"
    try:
        parse_stripped_tx(segwit)
    except UnsupportedSerializationError:
        pass
    else:
        raise AssertionError("BIP144 witness serialization was not rejected")

    # --- local synthetic-tx builders for (g) and (h) ---
    # Own minimal framing code, built from literals. txkit.py is NOT imported;
    # the oracle never shares construction machinery with the build side.
    def cs(n, wide=False):
        """CompactSize; wide=True forces the 0xfd 2-byte form (non-minimal)."""
        if wide or n >= 0xFD:
            return b"\xfd" + struct.pack("<H", n)
        return bytes([n])

    def mk_in(wide_ss=False):
        return (bytes(32) + struct.pack("<I", 0)
                + cs(0, wide_ss) + b"\xff\xff\xff\xff")

    def mk_out(value, script, wide_spk=False):
        return struct.pack("<Q", value) + cs(len(script), wide_spk) + script

    def mk_tx(outs, n_in=1, wide_in_count=False, wide_out_count=False,
              wide_ss=False, witness=False):
        raw = b"\x01\x00\x00\x00"
        if witness:
            raw += b"\x00\x01"                       # BIP144 marker + flag
        raw += cs(n_in, wide_in_count)
        raw += b"".join(mk_in(wide_ss) for _ in range(n_in))
        raw += cs(len(outs), wide_out_count)
        raw += b"".join(outs)
        if witness:                                  # one 2-byte item per input
            raw += b"".join(cs(1) + cs(2) + b"\xaa\xbb" for _ in range(n_in))
        return raw + b"\x00\x00\x00\x00"

    # (g) RULE-7 HASH PREDICATE, anchored to hardcoded known-answer pairs.
    # These digests were precomputed INDEPENDENTLY (2026-07-12) and are
    # transcribed here as literals: the expected values are never derived
    # through the code path under test.
    KAT_P2PKH = "76a9143f53b874d776eea1da76b623c5bb4c43c2ff9d6e88ac"
    KAT_P2PKH_SHA = (
        "3807e2ad511fda68d5e34212f1f03468b0f9c11b0302dfe687c201dfa0fc0e43"
    )
    KAT_OPRETURN = "6a01aa"
    KAT_OPRETURN_SHA = (
        "4a3148700b9079f44f2588a9ac832641439b27a627c7a59b2f6a5338c4959a94"
    )
    # Single SHA-256 over the RAW scriptPubKey bytes: no CompactSize prefix, no
    # byte reversal, no second hash.
    assert hashlib.sha256(bytes.fromhex(KAT_P2PKH)).hexdigest() == KAT_P2PKH_SHA
    assert hashlib.sha256(
        bytes.fromhex(KAT_OPRETURN)
    ).hexdigest() == KAT_OPRETURN_SHA

    # Canonical marker naming vout=1, built from the payload literal above.
    marker_script = bytes.fromhex("6a2b") + payload
    assert classify_output(marker_script) == ("CLAIMS", "CANONICAL")

    def rule7_tx(value, script_hex):
        return mk_tx([
            mk_out(0, marker_script),                       # index 0: marker
            mk_out(value, bytes.fromhex(script_hex)),       # index 1: named vout
        ])

    def deal(script_hash, sats):
        return {
            "expected_ergo_net": 0x01,
            "expected_btc_net": 0x01,
            "expected_vault_id": bytes.fromhex(displayed_id),
            "committed_script_hash": script_hash,
            "committed_sats": sats,
        }

    # positive: named output's script hashes to the committed hash, pays enough.
    assert verdict_tx(rule7_tx(20000, KAT_P2PKH),
                      deal(KAT_P2PKH_SHA, 20000))[:2] == ("VALID", None)
    # positive on the second pair (a different script shape; same convention).
    assert verdict_tx(rule7_tx(20000, KAT_OPRETURN),
                      deal(KAT_OPRETURN_SHA, 20000))[:2] == ("VALID", None)
    # over-payment is fine (pays-at-least).
    assert verdict_tx(rule7_tx(20001, KAT_P2PKH),
                      deal(KAT_P2PKH_SHA, 20000))[:2] == ("VALID", None)

    # negative: committed hash differing by ONE hex digit (last char 3 -> 4).
    one_off = KAT_P2PKH_SHA[:-1] + "4"
    assert one_off != KAT_P2PKH_SHA
    assert verdict_tx(rule7_tx(20000, KAT_P2PKH), deal(one_off, 20000))[:2] == \
        ("MALFORMED", "PAYMENT_SCRIPT_MISMATCH")
    # negative: the OTHER pair's hash against this script (cross-pair mismatch).
    assert verdict_tx(rule7_tx(20000, KAT_P2PKH),
                      deal(KAT_OPRETURN_SHA, 20000))[:2] == \
        ("MALFORMED", "PAYMENT_SCRIPT_MISMATCH")
    # negative: EMPTY scriptPubKey at the named output (script domain).
    assert verdict_tx(mk_tx([mk_out(0, marker_script), mk_out(20000, b"")]),
                      deal(KAT_P2PKH_SHA, 20000))[:2] == \
        ("MALFORMED", "PAYMENT_SCRIPT_MISMATCH")
    # negative: malformed committed-hash text (script domain, fails closed).
    for bad in ("", KAT_P2PKH_SHA[:63], KAT_P2PKH_SHA.upper(),
                KAT_P2PKH_SHA[:-1] + "g"):
        assert verdict_tx(rule7_tx(20000, KAT_P2PKH), deal(bad, 20000))[:2] == \
            ("MALFORMED", "PAYMENT_SCRIPT_MISMATCH"), bad
    # negative: value below committedSats (amount domain).
    assert verdict_tx(rule7_tx(19999, KAT_P2PKH),
                      deal(KAT_P2PKH_SHA, 20000))[:2] == \
        ("MALFORMED", "PAYMENT_AMOUNT_TOO_LOW")
    # negative: committedSats == 0 (outside (0, supply bound]).
    assert verdict_tx(rule7_tx(20000, KAT_P2PKH),
                      deal(KAT_P2PKH_SHA, 0))[:2] == \
        ("MALFORMED", "PAYMENT_AMOUNT_TOO_LOW")
    # negative: committedSats above the supply bound.
    assert verdict_tx(rule7_tx(20000, KAT_P2PKH),
                      deal(KAT_P2PKH_SHA, _SUPPLY_BOUND_SATS + 1))[:2] == \
        ("MALFORMED", "PAYMENT_AMOUNT_TOO_LOW")
    # negative: output VALUE above the supply bound (integer arithmetic).
    assert verdict_tx(rule7_tx(_SUPPLY_BOUND_SATS + 1, KAT_P2PKH),
                      deal(KAT_P2PKH_SHA, 20000))[:2] == \
        ("MALFORMED", "PAYMENT_AMOUNT_TOO_LOW")
    # the supply bound itself is INSIDE the closed interval on both sides.
    assert verdict_tx(rule7_tx(_SUPPLY_BOUND_SATS, KAT_P2PKH),
                      deal(KAT_P2PKH_SHA, _SUPPLY_BOUND_SATS))[:2] == \
        ("VALID", None)

    # (h) SECTION 7 PROFILE MATRIX.
    spk = bytes.fromhex(KAT_OPRETURN)
    out1 = mk_out(0, spk)

    def outs(k, wide_spk=False):
        return [mk_out(0, spk, wide_spk) for _ in range(k)]

    # in profile: the minimal shape, and both input-count boundaries.
    assert classify_profile(mk_tx([out1], n_in=1)) == (True, [])
    assert classify_profile(mk_tx([out1], n_in=2)) == (True, [])
    # inputs: 3 is over the max; 0 is under the min.
    assert classify_profile(mk_tx([out1], n_in=3)) == (False, [2])
    # A 0-input transaction with a NONZERO output count is byte-ambiguous with
    # the BIP144 marker/flag, so it cannot be posed here; 0-in/0-out is the
    # unambiguous form, and it violates items 2 AND 3 — the ORDER assertion.
    assert classify_profile(mk_tx([], n_in=0)) == (False, [2, 3])
    # outputs: 0 under the min; 4 at capacity (in profile); 5 over it.
    assert classify_profile(mk_tx([], n_in=1)) == (False, [3])
    assert classify_profile(mk_tx(outs(4))) == (True, [])
    assert classify_profile(mk_tx(outs(5))) == (False, [3])
    # item 4: a multibyte CompactSize at EACH field type flips it out of
    # profile, one field at a time, everything else in profile.
    assert classify_profile(mk_tx([out1], wide_in_count=True)) == (False, [4])
    assert classify_profile(mk_tx([out1], wide_out_count=True)) == (False, [4])
    assert classify_profile(mk_tx([out1], wide_ss=True)) == (False, [4])
    assert classify_profile(mk_tx(outs(1, wide_spk=True))) == (False, [4])
    # item 1: the full BIP144 witness form is CLASSIFIED, not raised.
    wit = mk_tx([out1], n_in=1, witness=True)
    assert classify_profile(wit) == (False, [1])
    # ...while the STRICT semantic path still rejects that same transaction.
    try:
        parse_stripped_tx(wit)
    except UnsupportedSerializationError:
        pass
    else:
        raise AssertionError("strict path accepted a BIP144 witness tx")
    # multiple violations at once, in Section 7 item order.
    assert classify_profile(
        mk_tx(outs(5), n_in=3, witness=True)
    ) == (False, [1, 2, 3])
    assert classify_profile(
        mk_tx(outs(5), n_in=3, witness=True, wide_out_count=True)
    ) == (False, [1, 2, 3, 4])
    assert classify_profile(mk_tx(outs(5), n_in=3)) == (False, [2, 3])

    print("verify.self_test: OK")


if __name__ == "__main__":
    self_test()
