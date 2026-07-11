"""families.py — the fixture case registry.

CASES maps case_id -> CaseSpec. Each CaseSpec carries the raw transaction bytes
plus the EXPECTED oracle outcome (per-output labels, grammar_verdict,
reason_code, capacity_expectation) and the deal context. generate.py replays
verify.verdict_tx / classify_output over each case and requires exact agreement;
these expectations are therefore assertions, not the source of truth.

Construction discipline:
  * Every base is the donor via txkit.parse_tx_sections + rebuild_outputs.
  * txkit.txout raw-splices scripts verbatim (malformed framing survives).
  * Malformed PUSH FRAMING is assembled by hand from raw bytes, but payload
    CONTENT comes from grammar.build_canonical_payload (or derivations) so a
    grammar change propagates into the families.
  * Field-level negatives mutate the canonical payload at grammar.OFFSETS.
  * Complete hardcoded marker hex lives ONLY in the grammar.py / verify.py
    goldens, never here.

expected_claimant_indices is intentionally NOT stored; generate.py derives it
from the labels (a single marker-index field cannot represent the two-claimant
cases N2, N4d-f, N15a).
"""

import hashlib
from dataclasses import dataclass, field

import donor
import grammar
import txkit

# --- Donor-derived, verified anchors ---
DONOR = bytes.fromhex(donor.DONOR_HEX)
_SEC = txkit.parse_tx_sections(DONOR)
COMMITTED_SCRIPT = _SEC["outputs"][0]["script"]      # 25-byte P2PKH
COMMITTED_SATS = 20000
UNRELATED_OPRETURN = _SEC["outputs"][1]["script"]    # "First OPReturn..."; IGNORED

EXPECTED_VAULT_ID = grammar.EXPECTED_VAULT_ID
OTHER_VAULT_ID = bytes.fromhex("ff" * 32)            # a different, valid-length id

# Canonical payload used as CONTENT for hand-framed malformed markers.
CANON_PAYLOAD = grammar.build_canonical_payload(1, EXPECTED_VAULT_ID)
MAGIC4 = CANON_PAYLOAD[:4]                            # the four magic bytes

# A P2PKH to a different key: a qualifying-shape payment to the WRONG script.
WRONG_SCRIPT = b"\x76\xa9\x14" + bytes(20) + b"\x88\xac"

# Deal context shared by every case (constant; no case overrides it).
DEFAULT_DEAL = {
    "expected_ergo_net": grammar.DEPLOY_ERGO_NET,
    "expected_btc_net": grammar.DEPLOY_BTC_NET,
    "expected_vault_id": EXPECTED_VAULT_ID,
    "committed_script": COMMITTED_SCRIPT,
    "committed_sats": COMMITTED_SATS,
}

# Label shorthands (must match verify.classify_output return strings).
CANON = ("CLAIMS", "CANONICAL")
NONCANON = ("CLAIMS", "NONCANONICAL")


@dataclass
class CaseSpec:
    family: str
    label: str
    raw_tx: bytes
    labels: dict                       # sparse: idx -> (membership, encoding)
    grammar_verdict: str
    reason_code: object                # str or None
    capacity_expectation: object       # dict or None
    deal_context: dict
    notes: str
    capacity: object = None            # reserved; unused today


CASES = {}


def _add(case_id, **kw):
    assert case_id not in CASES, f"duplicate case {case_id}"
    kw.setdefault("capacity_expectation", None)
    kw.setdefault("deal_context", DEFAULT_DEAL)
    CASES[case_id] = CaseSpec(**kw)


# --- construction helpers ---
def canon_marker(vout, vault=EXPECTED_VAULT_ID, value=0):
    script = grammar.build_canonical_marker_script(
        grammar.build_canonical_payload(vout, vault)
    )
    return txkit.txout(value, script)


def payment(value=COMMITTED_SATS, script=COMMITTED_SCRIPT):
    return txkit.txout(value, script)


def filler():
    return txkit.txout(0, b"\x6a\x01\xaa")


def raw_out(value, script):
    return txkit.txout(value, script)


def build(outs):
    return txkit.rebuild_outputs(DONOR, list(outs))


# =====================================================================
# POSITIVES
# =====================================================================
_add("P1a", family="P1", label="canonical marker first, payment after",
     raw_tx=build([canon_marker(1), payment()]),
     labels={0: CANON}, grammar_verdict="VALID", reason_code=None,
     notes="marker at index 0, vout=1 names the payment")

_add("P1b", family="P1", label="canonical marker middle, payment before",
     raw_tx=build([payment(), canon_marker(0), filler()]),
     labels={1: CANON}, grammar_verdict="VALID", reason_code=None,
     notes="marker at index 1, vout=0 names the earlier payment")

_add("P1c", family="P1", label="canonical marker last, payment before",
     raw_tx=build([payment(), canon_marker(0)]),
     labels={1: CANON}, grammar_verdict="VALID", reason_code=None,
     notes="marker at index 1 (last), vout=0 names the payment")

_add("P1d", family="P1", label="canonical marker middle, payment after",
     raw_tx=build([filler(), canon_marker(2), payment()]),
     labels={1: CANON}, grammar_verdict="VALID", reason_code=None,
     notes="marker at index 1, vout=2 names the later payment")

_add("P2a", family="P2", label="unrelated OP_RETURN before canonical marker",
     raw_tx=build([raw_out(0, UNRELATED_OPRETURN), canon_marker(2), payment()]),
     labels={1: CANON}, grammar_verdict="VALID", reason_code=None,
     notes="donor's real OP_RETURN (non-magic) ignored; marker at 1, vout=2")

_add("P2b", family="P2", label="unrelated OP_RETURN after canonical marker",
     raw_tx=build([canon_marker(1), payment(), raw_out(0, UNRELATED_OPRETURN)]),
     labels={0: CANON}, grammar_verdict="VALID", reason_code=None,
     notes="unrelated OP_RETURN after marker ignored; marker at 0, vout=1")

_add("P3", family="P3", label="two qualifying payments, named vout is one",
     raw_tx=build([payment(), canon_marker(0), payment()]),
     labels={1: CANON}, grammar_verdict="VALID", reason_code=None,
     notes="outputs 0 and 2 both qualify; vout=0 names one -> valid")

_add("P4", family="P4", label="vout == outputCount-1 (upper boundary)",
     raw_tx=build([canon_marker(2), filler(), payment()]),
     labels={0: CANON}, grammar_verdict="VALID", reason_code=None,
     notes="3 outputs, vout=2 = outputCount-1, payment at 2")

_add("P5", family="P5", label="vout=1 encoded 01 00 00 00 (LE control)",
     raw_tx=build([canon_marker(1), payment(), filler()]),
     labels={0: CANON}, grammar_verdict="VALID", reason_code=None,
     notes="vout packed little-endian 01000000; payment at index 1")

# P6: 257 outputs, marker at 0, payment at 256, vout=256 (00 01 00 00).
_p6 = [canon_marker(256)] + [filler() for _ in range(255)] + [payment()]
_add("P6", family="P6", label="vout=256 (00 01 00 00), 257 outputs",
     raw_tx=build(_p6),
     labels={0: CANON}, grammar_verdict="VALID", reason_code=None,
     notes="257 outputs within scan capacity; payment at index 256")


# =====================================================================
# CLAIMANT-COUNT AND ENCODING NEGATIVES
# =====================================================================
_add("N1", family="N1", label="zero claimants (payment, no marker)",
     raw_tx=build([payment(), filler()]),
     labels={}, grammar_verdict="NOT-A-SETTLEMENT", reason_code="ZERO_CLAIMANTS",
     notes="no output claims the magic")

_add("N2a", family="N2", label="two canonical claimants, same vault_id",
     raw_tx=build([canon_marker(2), canon_marker(2), payment()]),
     labels={0: CANON, 1: CANON}, grammar_verdict="MALFORMED",
     reason_code="MULTIPLE_CLAIMANTS",
     notes="two canonical markers -> ambiguity")

_add("N2b", family="N2", label="two canonical claimants, different vault_ids",
     raw_tx=build([canon_marker(2), canon_marker(2, vault=OTHER_VAULT_ID),
                   payment()]),
     labels={0: CANON, 1: CANON}, grammar_verdict="MALFORMED",
     reason_code="MULTIPLE_CLAIMANTS",
     notes="two canonical markers naming different vaults -> ambiguity")

# N3 same-magic non-canonical (framing hand-built, content canonical).
_add("N3a", family="N3", label="wrong payload length 42",
     raw_tx=build([raw_out(0, bytes([0x6a, 42]) + CANON_PAYLOAD[:-1]), payment()]),
     labels={0: NONCANON}, grammar_verdict="MALFORMED",
     reason_code="NONCANONICAL_MARKER",
     notes="direct push of 42 bytes; claims but non-canonical")

_add("N3b", family="N3", label="wrong payload length 44",
     raw_tx=build([raw_out(0, bytes([0x6a, 44]) + CANON_PAYLOAD + b"\x00"),
                   payment()]),
     labels={0: NONCANON}, grammar_verdict="MALFORMED",
     reason_code="NONCANONICAL_MARKER",
     notes="direct push of 44 bytes; claims but non-canonical")

_add("N3c", family="N3", label="declared 43 but physically truncated",
     raw_tx=build([raw_out(0, bytes([0x6a, 0x2b]) + CANON_PAYLOAD[:40]),
                   payment()]),
     labels={0: NONCANON}, grammar_verdict="MALFORMED",
     reason_code="NONCANONICAL_MARKER",
     notes="declared 43, only 40 payload bytes; truncation rule -> claims")

_add("N3d", family="N3", label="declared 43 with a trailing byte",
     raw_tx=build([raw_out(0, bytes([0x6a, 0x2b]) + CANON_PAYLOAD + b"\x00"),
                   payment()]),
     labels={0: NONCANON}, grammar_verdict="MALFORMED",
     reason_code="NONCANONICAL_MARKER",
     notes="canonical push plus one trailing byte; non-canonical")

_add("N3e", family="N3", label="declared 43 with a trailing second push",
     raw_tx=build([raw_out(0, bytes([0x6a, 0x2b]) + CANON_PAYLOAD + b"\x01\xaa"),
                   payment()]),
     labels={0: NONCANON}, grammar_verdict="MALFORMED",
     reason_code="NONCANONICAL_MARKER",
     notes="canonical push plus a trailing second push; non-canonical")

# N4 non-canonical push encodings.
_n4a_script = b"\x6a\x4c\x2b" + CANON_PAYLOAD                       # PUSHDATA1
_n4b_script = b"\x6a\x4d\x2b\x00" + CANON_PAYLOAD                   # PUSHDATA2
_n4c_script = b"\x6a\x4e" + bytes.fromhex("2b000000") + CANON_PAYLOAD  # PUSHDATA4

_add("N4a", family="N4", label="PUSHDATA1 encoding alone",
     raw_tx=build([raw_out(0, _n4a_script), payment()]),
     labels={0: NONCANON}, grammar_verdict="MALFORMED",
     reason_code="NONCANONICAL_MARKER",
     notes="correct payload via PUSHDATA1; non-canonical claimant")

_add("N4b", family="N4", label="PUSHDATA2 encoding alone",
     raw_tx=build([raw_out(0, _n4b_script), payment()]),
     labels={0: NONCANON}, grammar_verdict="MALFORMED",
     reason_code="NONCANONICAL_MARKER",
     notes="correct payload via PUSHDATA2; non-canonical claimant")

_add("N4c", family="N4", label="PUSHDATA4 encoding alone",
     raw_tx=build([raw_out(0, _n4c_script), payment()]),
     labels={0: NONCANON}, grammar_verdict="MALFORMED",
     reason_code="NONCANONICAL_MARKER",
     notes="correct payload via PUSHDATA4; non-canonical claimant")

_add("N4d", family="N4", label="canonical + PUSHDATA1 -> two claimants",
     raw_tx=build([canon_marker(2), raw_out(0, _n4a_script), payment()]),
     labels={0: CANON, 1: NONCANON}, grammar_verdict="MALFORMED",
     reason_code="MULTIPLE_CLAIMANTS",
     notes="re-encoded second claimant cannot smuggle past exactly-one")

_add("N4e", family="N4", label="canonical + PUSHDATA2 -> two claimants",
     raw_tx=build([canon_marker(2), raw_out(0, _n4b_script), payment()]),
     labels={0: CANON, 1: NONCANON}, grammar_verdict="MALFORMED",
     reason_code="MULTIPLE_CLAIMANTS",
     notes="re-encoded second claimant cannot smuggle past exactly-one")

_add("N4f", family="N4", label="canonical + PUSHDATA4 -> two claimants",
     raw_tx=build([canon_marker(2), raw_out(0, _n4c_script), payment()]),
     labels={0: CANON, 1: NONCANON}, grammar_verdict="MALFORMED",
     reason_code="MULTIPLE_CLAIMANTS",
     notes="re-encoded second claimant cannot smuggle past exactly-one")

# N5 push-length semantics.
_add("N5a", family="N5", label="PUSHDATA1 declared 0 then magic (ignored)",
     raw_tx=build([raw_out(0, b"\x6a\x4c\x00" + MAGIC4), payment()]),
     labels={}, grammar_verdict="NOT-A-SETTLEMENT", reason_code="ZERO_CLAIMANTS",
     notes="declared length 0 < 4 -> does not claim")

_add("N5b", family="N5", label="PUSHDATA1 declared 1 then magic (ignored)",
     raw_tx=build([raw_out(0, b"\x6a\x4c\x01" + MAGIC4), payment()]),
     labels={}, grammar_verdict="NOT-A-SETTLEMENT", reason_code="ZERO_CLAIMANTS",
     notes="declared length 1 < 4 -> does not claim")

_add("N5c", family="N5", label="PUSHDATA1 declared 2 then magic (ignored)",
     raw_tx=build([raw_out(0, b"\x6a\x4c\x02" + MAGIC4), payment()]),
     labels={}, grammar_verdict="NOT-A-SETTLEMENT", reason_code="ZERO_CLAIMANTS",
     notes="declared length 2 < 4 -> does not claim")

_add("N5d", family="N5", label="PUSHDATA1 declared 3 then magic (ignored)",
     raw_tx=build([raw_out(0, b"\x6a\x4c\x03" + MAGIC4), payment()]),
     labels={}, grammar_verdict="NOT-A-SETTLEMENT", reason_code="ZERO_CLAIMANTS",
     notes="declared length 3 < 4 -> does not claim")

_add("N5e", family="N5", label="declared >=4 magic present, push beyond slice",
     raw_tx=build([raw_out(0, b"\x6a\x4c\x2b" + MAGIC4), payment()]),
     labels={0: NONCANON}, grammar_verdict="MALFORMED",
     reason_code="NONCANONICAL_MARKER",
     notes="PUSHDATA1 declared 43, only 4 physical magic bytes; claims (trunc)")

_add("N5f", family="N5", label="slice ends before four magic bytes (ignored)",
     raw_tx=build([raw_out(0, b"\x6a\x05" + MAGIC4[:3]), payment()]),
     labels={}, grammar_verdict="NOT-A-SETTLEMENT", reason_code="ZERO_CLAIMANTS",
     notes="direct push declared 5, only 3 physical bytes; magic incomplete")

_add("N5g", family="N5", label="incomplete PUSHDATA1 length prefix (ignored)",
     raw_tx=build([raw_out(0, b"\x6a\x4c"), payment()]),
     labels={}, grammar_verdict="NOT-A-SETTLEMENT", reason_code="ZERO_CLAIMANTS",
     notes="no length byte after 0x4c -> no decodable push")

_add("N5h", family="N5", label="incomplete PUSHDATA2 length prefix (ignored)",
     raw_tx=build([raw_out(0, b"\x6a\x4d\x00"), payment()]),
     labels={}, grammar_verdict="NOT-A-SETTLEMENT", reason_code="ZERO_CLAIMANTS",
     notes="only 1 of 2 length bytes after 0x4d -> no decodable push")

_add("N5i", family="N5", label="incomplete PUSHDATA4 length prefix (ignored)",
     raw_tx=build([raw_out(0, b"\x6a\x4e\x00\x00\x00"), payment()]),
     labels={}, grammar_verdict="NOT-A-SETTLEMENT", reason_code="ZERO_CLAIMANTS",
     notes="only 3 of 4 length bytes after 0x4e -> no decodable push")

_add("N5j", family="N5", label="PUSHDATA4 length 0x80000004 with magic (claims)",
     raw_tx=build([raw_out(0, b"\x6a\x4e" + bytes.fromhex("04000080") + MAGIC4),
                   payment()]),
     labels={0: NONCANON}, grammar_verdict="MALFORMED",
     reason_code="NONCANONICAL_MARKER",
     notes="unsigned decode keeps 0x80000004 positive; claims, malformed")

# N6 first-push / namespace rule.
_add("N6a", family="N6", label="empty first push then magic second push",
     raw_tx=build([raw_out(0, b"\x6a\x00\x04" + MAGIC4), payment()]),
     labels={}, grammar_verdict="NOT-A-SETTLEMENT", reason_code="ZERO_CLAIMANTS",
     notes="OP_0 empty first push; magic in second push -> ignored")

_add("N6b", family="N6", label="unrelated first push then magic second push",
     raw_tx=build([raw_out(0, b"\x6a\x04\xde\xad\xbe\xef\x04" + MAGIC4), payment()]),
     labels={}, grammar_verdict="NOT-A-SETTLEMENT", reason_code="ZERO_CLAIMANTS",
     notes="non-magic first push; magic in second push -> ignored")

_add("N6c", family="N6", label="magic embedded in P2WSH program",
     raw_tx=build([raw_out(0, b"\x00\x20" + MAGIC4 + bytes(28)), payment()]),
     labels={}, grammar_verdict="NOT-A-SETTLEMENT", reason_code="ZERO_CLAIMANTS",
     notes="0x00 0x20 witness v0 program; not OP_RETURN -> ignored")

_add("N6d", family="N6", label="magic embedded in P2TR program",
     raw_tx=build([raw_out(0, b"\x51\x20" + MAGIC4 + bytes(28)), payment()]),
     labels={}, grammar_verdict="NOT-A-SETTLEMENT", reason_code="ZERO_CLAIMANTS",
     notes="0x51 0x20 witness v1 program; not OP_RETURN -> ignored")

_add("N6e", family="N6", label="script not starting 0x6a",
     raw_tx=build([raw_out(0, b"\x76\xa9\x14" + MAGIC4 + bytes(16) + b"\x88\xac"),
                   payment()]),
     labels={}, grammar_verdict="NOT-A-SETTLEMENT", reason_code="ZERO_CLAIMANTS",
     notes="P2PKH-shaped, magic in hash160; first byte != 0x6a -> ignored")

_add("N6f", family="N6", label="near-miss magic ERGW",
     raw_tx=build([raw_out(0, bytes([0x6a, 0x2b])
                           + grammar.NEAR_MISS_MAGICS[0] + CANON_PAYLOAD[4:]),
                   payment()]),
     labels={}, grammar_verdict="NOT-A-SETTLEMENT", reason_code="ZERO_CLAIMANTS",
     notes="canonical framing but magic ERGW != ERGV -> ignored")

_add("N6g", family="N6", label="near-miss magic ERGU",
     raw_tx=build([raw_out(0, bytes([0x6a, 0x2b])
                           + grammar.NEAR_MISS_MAGICS[1] + CANON_PAYLOAD[4:]),
                   payment()]),
     labels={}, grammar_verdict="NOT-A-SETTLEMENT", reason_code="ZERO_CLAIMANTS",
     notes="canonical framing but magic ERGU != ERGV -> ignored")

_add("N6h", family="N6", label="near-miss magic ergv (lowercase)",
     raw_tx=build([raw_out(0, bytes([0x6a, 0x2b])
                           + grammar.NEAR_MISS_MAGICS[2] + CANON_PAYLOAD[4:]),
                   payment()]),
     labels={}, grammar_verdict="NOT-A-SETTLEMENT", reason_code="ZERO_CLAIMANTS",
     notes="canonical framing but magic ergv != ERGV -> ignored")


# =====================================================================
# FIELD NEGATIVES
# =====================================================================
def _mutate(payload, offset, newbytes):
    b = bytearray(payload)
    b[offset:offset + len(newbytes)] = newbytes
    return bytes(b)


def _marker_from_payload(payload, value=0):
    return txkit.txout(value, grammar.build_canonical_marker_script(payload))


# N7 unknown version.
_n7_payload = _mutate(grammar.build_canonical_payload(1, EXPECTED_VAULT_ID),
                      grammar.OFFSETS["version"], b"\x02")
_add("N7", family="N7", label="unknown version 0x02",
     raw_tx=build([_marker_from_payload(_n7_payload), payment()]),
     labels={0: CANON}, grammar_verdict="MALFORMED",
     reason_code="VERSION_MISMATCH",
     notes="canonical framing, version byte mutated to 0x02")

# N8 network mismatches.
_n8a = _mutate(grammar.build_canonical_payload(1, EXPECTED_VAULT_ID),
               grammar.OFFSETS["ergo_net"], b"\x02")
_add("N8a", family="N8", label="ergo_net wrong (0x02 testnet)",
     raw_tx=build([_marker_from_payload(_n8a), payment()]),
     labels={0: CANON}, grammar_verdict="MALFORMED",
     reason_code="ERGO_NETWORK_MISMATCH",
     notes="ergo_net = testnet vs mainnet deployment")

_n8b = _mutate(grammar.build_canonical_payload(1, EXPECTED_VAULT_ID),
               grammar.OFFSETS["btc_net"], b"\x02")
_add("N8b", family="N8", label="btc_net wrong (0x02 Testnet4)",
     raw_tx=build([_marker_from_payload(_n8b), payment()]),
     labels={0: CANON}, grammar_verdict="MALFORMED",
     reason_code="BITCOIN_NETWORK_MISMATCH",
     notes="btc_net = Testnet4 vs mainnet deployment")

_n8c = _mutate(grammar.build_canonical_payload(1, EXPECTED_VAULT_ID),
               grammar.OFFSETS["ergo_net"], b"\xff")
_add("N8c", family="N8", label="ergo_net unlisted enum 0xff",
     raw_tx=build([_marker_from_payload(_n8c), payment()]),
     labels={0: CANON}, grammar_verdict="MALFORMED",
     reason_code="ERGO_NETWORK_MISMATCH",
     notes="ergo_net unlisted value -> malformed")

_n8d = _mutate(grammar.build_canonical_payload(1, EXPECTED_VAULT_ID),
               grammar.OFFSETS["btc_net"], b"\xff")
_add("N8d", family="N8", label="btc_net unlisted enum 0xff",
     raw_tx=build([_marker_from_payload(_n8d), payment()]),
     labels={0: CANON}, grammar_verdict="MALFORMED",
     reason_code="BITCOIN_NETWORK_MISMATCH",
     notes="btc_net unlisted value -> malformed")

# N9 vault_id mismatches (built from EXPECTED via the canonical builder).
# N9a uses sha256(EXPECTED_VAULT_ID): deterministic, 32 bytes, with no
# algebraic relation to a bit-flip or a byte-reversal. This deliberately avoids
# the collision seen when a candidate (e.g. XOR 0xFF) coincides with N9c's
# reversal for a palindromic EXPECTED_VAULT_ID; sha256 survives any vault-id
# change at freeze. The assert below makes that collision class unable to
# silently return.
_n9a_vault = hashlib.sha256(EXPECTED_VAULT_ID).digest()
_add("N9a", family="N9", label="vault_id = sha256(EXPECTED_VAULT_ID)",
     raw_tx=build([canon_marker(1, vault=_n9a_vault), payment()]),
     labels={0: CANON}, grammar_verdict="MALFORMED",
     reason_code="VAULT_ID_MISMATCH",
     notes="unrelated 32-byte id (sha256 of the expected id); no flip/reversal relation")

_n9b_vault = bytes([EXPECTED_VAULT_ID[0] ^ 0x01]) + EXPECTED_VAULT_ID[1:]
_add("N9b", family="N9", label="vault_id one-byte mismatch",
     raw_tx=build([canon_marker(1, vault=_n9b_vault), payment()]),
     labels={0: CANON}, grammar_verdict="MALFORMED",
     reason_code="VAULT_ID_MISMATCH",
     notes="first vault_id byte flipped by one bit")

_n9c_vault = EXPECTED_VAULT_ID[::-1]
_add("N9c", family="N9", label="vault_id full byte reversal",
     raw_tx=build([canon_marker(1, vault=_n9c_vault), payment()]),
     labels={0: CANON}, grammar_verdict="MALFORMED",
     reason_code="VAULT_ID_MISMATCH",
     notes="reversed id (the display-order-confusion counterexample)")

# The three N9 vault ids must be pairwise distinct AND each differ from
# EXPECTED_VAULT_ID, so the XOR-equals-reversal collision class (which made two
# N9 vectors byte-identical for the palindromic expected id) can never silently
# return, whatever EXPECTED_VAULT_ID is set to at freeze.
_n9_vaults = {
    "N9a": _n9a_vault, "N9b": _n9b_vault, "N9c": _n9c_vault,
    "EXPECTED": EXPECTED_VAULT_ID,
}
for _a in _n9_vaults:
    assert len(_n9_vaults[_a]) == 32, f"{_a} vault id not 32 bytes"
_n9_pairs = list(_n9_vaults.items())
for _i in range(len(_n9_pairs)):
    for _j in range(_i + 1, len(_n9_pairs)):
        (_na, _va), (_nb, _vb) = _n9_pairs[_i], _n9_pairs[_j]
        assert _va != _vb, f"N9 vault-id collision: {_na} == {_nb}"

# N10 vout encoded big-endian.
_n10 = _mutate(grammar.build_canonical_payload(1, EXPECTED_VAULT_ID),
               grammar.OFFSETS["vout"], bytes.fromhex("00000001"))
_add("N10", family="N10", label="vout intended 1 encoded big-endian",
     raw_tx=build([_marker_from_payload(_n10), payment()]),
     labels={0: CANON}, grammar_verdict="MALFORMED",
     reason_code="VOUT_OUT_OF_RANGE",
     notes="00 00 00 01 decodes unsigned LE to 16777216 -> out of range")

# N11 vout out of range.
_add("N11a", family="N11", label="vout == outputCount",
     raw_tx=build([canon_marker(2), payment()]),
     labels={0: CANON}, grammar_verdict="MALFORMED",
     reason_code="VOUT_OUT_OF_RANGE",
     notes="2 outputs, vout=2 not < outputCount")

_add("N11b", family="N11", label="vout == markerOutputIndex",
     raw_tx=build([canon_marker(0), payment()]),
     labels={0: CANON}, grammar_verdict="MALFORMED",
     reason_code="VOUT_IS_MARKER",
     notes="marker at index 0 names vout=0 (itself)")

_add("N11c", family="N11", label="vout == 0xffffffff",
     raw_tx=build([canon_marker(0xFFFFFFFF), payment()]),
     labels={0: CANON}, grammar_verdict="MALFORMED",
     reason_code="VOUT_OUT_OF_RANGE",
     notes="high-bit-set vout decoded unsigned -> far out of range")

# N12 nonzero marker value.
_add("N12", family="N12", label="nonzero value on canonical marker",
     raw_tx=build([canon_marker(1, value=1), payment()]),
     labels={0: CANON}, grammar_verdict="MALFORMED",
     reason_code="NONZERO_MARKER_VALUE",
     notes="canonical script but marker output value = 1 satoshi")


# =====================================================================
# INDEXED-PAYMENT NEGATIVES
# =====================================================================
_add("N13", family="N13", label="named output fails; another output qualifies",
     raw_tx=build([canon_marker(1),
                   payment(script=WRONG_SCRIPT),   # index 1: named, wrong script
                   payment()]),                    # index 2: qualifies, ignored
     labels={0: CANON}, grammar_verdict="MALFORMED",
     reason_code="PAYMENT_SCRIPT_MISMATCH",
     notes="anyOutputMatches killer: only the NAMED output counts")

_add("N14a", family="N14", label="named output right script, amount too low",
     raw_tx=build([canon_marker(1), payment(value=COMMITTED_SATS - 1)]),
     labels={0: CANON}, grammar_verdict="MALFORMED",
     reason_code="PAYMENT_AMOUNT_TOO_LOW",
     notes="committed script, value 19999 < 20000")

_add("N14b", family="N14", label="named output sufficient amount, wrong script",
     raw_tx=build([canon_marker(1), payment(script=WRONG_SCRIPT)]),
     labels={0: CANON}, grammar_verdict="MALFORMED",
     reason_code="PAYMENT_SCRIPT_MISMATCH",
     notes="value 20000 but wrong script at the named vout")


# =====================================================================
# SCAN-BOUND NEGATIVES
# =====================================================================
_n15a = ([canon_marker(1), payment()]
         + [filler() for _ in range(297)]
         + [canon_marker(1)])
_add("N15a", family="N15", label="second claimant at last of 300 outputs",
     raw_tx=build(_n15a),
     labels={0: CANON, 299: CANON}, grammar_verdict="MALFORMED",
     reason_code="MULTIPLE_CLAIMANTS", capacity_expectation=None,
     notes="300 outputs; hidden second claimant last -> full scan catches it")

_n15b = [canon_marker(1), payment()] + [filler() for _ in range(298)]
_add("N15b", family="N15", label="one claimant, 300 outputs (at capacity)",
     raw_tx=build(_n15b),
     labels={0: CANON}, grammar_verdict="VALID", reason_code=None,
     capacity_expectation=None,
     notes="300 outputs == assumed scan capacity; valid")

_n15c = [canon_marker(1), payment()] + [filler() for _ in range(299)]
_add("N15c", family="N15", label="one claimant, 301 outputs (over capacity)",
     raw_tx=build(_n15c),
     labels={0: CANON}, grammar_verdict="VALID", reason_code=None,
     capacity_expectation={
         "minimum_capacity": 301,
         "below_minimum": "REJECT_SCAN_CAPACITY",
         "at_or_above_minimum": "USE_GRAMMAR_VERDICT",
     },
     notes="301 > assumed scan capacity 300; grammar valid but capacity-gated")


# --- required-set assertion ---
REQUIRED_CASES = [
    "P1a", "P1b", "P1c", "P1d", "P2a", "P2b", "P3", "P4", "P5", "P6",
    "N1", "N2a", "N2b", "N3a", "N3b", "N3c", "N3d", "N3e",
    "N4a", "N4b", "N4c", "N4d", "N4e", "N4f",
    "N5a", "N5b", "N5c", "N5d", "N5e", "N5f", "N5g", "N5h", "N5i", "N5j",
    "N6a", "N6b", "N6c", "N6d", "N6e", "N6f", "N6g", "N6h",
    "N7", "N8a", "N8b", "N8c", "N8d", "N9a", "N9b", "N9c", "N10",
    "N11a", "N11b", "N11c", "N12", "N13", "N14a", "N14b",
    "N15a", "N15b", "N15c",
]

assert set(CASES) == set(REQUIRED_CASES), (
    "case set mismatch: "
    f"missing={sorted(set(REQUIRED_CASES) - set(CASES))} "
    f"extra={sorted(set(CASES) - set(REQUIRED_CASES))}"
)


def self_test() -> None:
    assert set(CASES) == set(REQUIRED_CASES)
    assert len(CASES) == len(REQUIRED_CASES) == 61, len(CASES)
    for cid, c in CASES.items():
        assert isinstance(c.raw_tx, bytes) and len(c.raw_tx) > 0, cid
        assert c.grammar_verdict in (
            "VALID", "MALFORMED", "NOT-A-SETTLEMENT"), cid
    print("families.self_test: OK ({} cases)".format(len(CASES)))


if __name__ == "__main__":
    self_test()
