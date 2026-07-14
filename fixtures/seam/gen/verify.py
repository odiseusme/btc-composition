"""verify.py — the independent seam oracle (skeleton, task 0.3).

DELIBERATELY DECOUPLED from the construction side, exactly as the marker
oracle is. This module checks the emitted artifacts against literals it
transcribes ITSELF, from the pinned documents, so that a construction-side
bug cannot mask itself by being read back through its own constant.

WHAT IT IMPORTS: STATUS, EXPECTED_GRAMMAR_SHA256, EXPECTED_SPEC_SHA256 from
constants.py. That is the whole list, and every one of them is bookkeeping —
a freeze marker and two doc-hash pins, none of which this module could
independently derive without simply re-hashing the same files the gate
already hashed.

WHAT IT IMPORTS FROM adapters.py AND generate.py: nothing. Not a helper, not
a path, not a stage name. It re-derives the artifact's structure from the
emitted JSON by hand. check_scaffolding.py check (e) proves this by AST, not
by convention: an oracle that reached into the generator's serializer would
be re-running the generator, not checking it.

WHAT IT TRANSCRIBES AS ITS OWN LITERALS at this stage: the 4-byte ASCII
payload magic (marker-grammar-DRAFT.md Section 1) and the 21M supply bound
in satoshi (Section 3 rule 7). generate.cross_check_transcriptions() compares
each against the construction side's copy at every run; a disagreement is a
build failure, never a warning.

SCOPE. Task 0.3 emits two scaffolding artifacts and this oracle verifies
exactly those:

  probe-magic.json    a tx_set-adapter record whose bytes embed the magic at
                      a declared offset, with a manifest stub carrying the
                      grammar and SPEC hashes its bytes depend on. It is the
                      magic-DEPENDENT target for the 0.6 regeneration test.

  control-plain.json  a header_template-adapter record with no grammar
                      dependency: no magic in its bytes and no pin hash in
                      its manifest stub. It is the INVARIANT control for the
                      same test — flipping the magic must not move it.

The supply bound is transcribed and self-tested here even though no 0.3
artifact carries an amount yet: the literal, and the integer-not-float
discipline around it, are what Phase 1's amount cases (family V12) will
check against, and cross_check_transcriptions() compares it every run from
day one rather than the day it first has a fixture to reject.
"""

import json
import sys
from pathlib import Path

# Bookkeeping-only imports. No layout, no adapters, no generator.
from constants import (
    STATUS,
    EXPECTED_GRAMMAR_SHA256,
    EXPECTED_SPEC_SHA256,
)

# --- Own literals, retranscribed from the pinned documents ------------------
# Do NOT replace either of these with an import: the cross-check exists to
# compare two independent copies, and an import turns it into a tautology.

# marker-grammar-DRAFT.md Section 1: the payload magic, ASCII "ERGV".
_MAGIC = b"\x45\x52\x47\x56"
_MAGIC_LEN = 4

# marker-grammar-DRAFT.md Section 3 rule 7: the 21M BTC supply bound in
# satoshi. Integer arithmetic only — never a float, never 21e14.
_SUPPLY_BOUND_SATS = 2_100_000_000_000_000

# --- Artifact locations -----------------------------------------------------
SEAM_DIR = Path(__file__).resolve().parents[1]
VECTORS_DIR = SEAM_DIR / "vectors"

# The 0.3 scaffolding inventory. The oracle names what it expects to find so
# that a missing artifact fails as loudly as a corrupt one.
PROBE_ID = "probe-magic"
CONTROL_ID = "control-plain"
ARTIFACTS = {
    PROBE_ID: "probe-magic.json",
    CONTROL_ID: "control-plain.json",
}

# The pinned documents a record's bytes may declare a dependency on, and the
# manifest-stub field each one's hash is carried in.
_PIN_FIELDS = {
    "marker-grammar-DRAFT.md": ("grammar_doc_sha256", EXPECTED_GRAMMAR_SHA256),
    "composition-handoff-SPEC.md": ("spec_sha256", EXPECTED_SPEC_SHA256),
}


class OracleError(AssertionError):
    """An emitted artifact does not match what the oracle independently expects."""


def _require(condition, message):
    if not condition:
        raise OracleError(message)


def check_supply_bound(value):
    """The lane's amount discipline, in one place: integer satoshis, in range.

    bool is an int subclass and a float can compare equal to an integer bound,
    so both are rejected by TYPE before any comparison is made.
    """
    _require(
        isinstance(value, int) and not isinstance(value, bool),
        f"satoshi amount {value!r} is not an integer",
    )
    _require(
        0 <= value <= _SUPPLY_BOUND_SATS,
        f"satoshi amount {value} outside [0, {_SUPPLY_BOUND_SATS}]",
    )
    return value


def load_artifact(path):
    """Read an emitted artifact as BYTES first; return (raw, record).

    Bytes first, because two of the things this oracle checks — LF-only
    output, and the absence of the magic from the control — are properties of
    the FILE, not of the object a JSON parser hands back.
    """
    _require(path.exists(), f"{path.name}: missing (the generator did not emit it)")
    raw = path.read_bytes()
    _require(b"\r" not in raw, f"{path.name}: contains a CR byte; output is LF-only")
    try:
        record = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise OracleError(f"{path.name}: not valid UTF-8 JSON ({exc})") from exc
    _require(isinstance(record, dict), f"{path.name}: top level is not an object")
    return raw, record


def _stage(name, record, stage_name):
    """Pull the one envelope for a stage, re-deriving nothing from the generator."""
    stages = record.get("stages")
    _require(isinstance(stages, list) and stages, f"{name}: no stages list")
    matching = [s for s in stages if isinstance(s, dict) and s.get("stage") == stage_name]
    _require(
        len(matching) == 1,
        f"{name}: expected exactly one {stage_name} stage, found {len(matching)}",
    )
    serialized = matching[0].get("serialized")
    _require(isinstance(serialized, dict), f"{name}: {stage_name} stage carries no serialized data")
    return serialized


def _decode_bytes(name, serialized, field="bytes_hex"):
    hex_text = serialized.get(field)
    _require(isinstance(hex_text, str), f"{name}: {field} is not hex text")
    _require(len(hex_text) % 2 == 0, f"{name}: {field} is odd-length hex")
    try:
        raw = bytes.fromhex(hex_text)
    except ValueError as exc:
        raise OracleError(f"{name}: {field} is not hex ({exc})") from exc
    declared_len = serialized.get("length")
    _require(
        declared_len == len(raw),
        f"{name}: declared length {declared_len!r} != {len(raw)} decoded bytes",
    )
    return raw


def _check_manifest_stub(name, record, expected_docs):
    """The stub carries EXACTLY the pin hashes of the docs it declares, no more.

    'Exactly' is the load-bearing word. The 0.2 invalidation set is derived by
    scanning these fields for a moved pin's old value, so a record carrying a
    hash it does not depend on would be regenerated for nothing, and a record
    omitting one it does depend on would be silently skipped — the failure
    mode that matters.
    """
    stub = record.get("manifest_stub")
    _require(isinstance(stub, dict), f"{name}: no manifest_stub")
    _require(
        set(stub) == {"depends_on", "pin_hashes"},
        f"{name}: manifest_stub keys {sorted(stub)} != ['depends_on', 'pin_hashes']",
    )

    depends_on = stub["depends_on"]
    _require(isinstance(depends_on, list), f"{name}: manifest_stub.depends_on is not a list")
    _require(
        depends_on == sorted(expected_docs),
        f"{name}: declares dependencies {depends_on} != {sorted(expected_docs)}",
    )

    pin_hashes = stub["pin_hashes"]
    _require(isinstance(pin_hashes, dict), f"{name}: manifest_stub.pin_hashes is not an object")
    expected = {
        _PIN_FIELDS[doc][0]: _PIN_FIELDS[doc][1] for doc in expected_docs
    }
    _require(
        pin_hashes == expected,
        f"{name}: pin_hashes {pin_hashes} != the declared pins {expected}",
    )


def _check_common(name, record, kind):
    _require(record.get("record_id") == name, f"{name}: record_id {record.get('record_id')!r}")
    _require(record.get("kind") == kind, f"{name}: kind {record.get('kind')!r} != {kind!r}")
    _require(
        record.get("status") == STATUS,
        f"{name}: status {record.get('status')!r} != {STATUS!r}",
    )


def verify_probe(raw, record):
    """The magic-DEPENDENT artifact: the magic must be there, where it says.

    The offset is the record's CLAIM. The oracle decodes the emitted bytes and
    reads that window itself; it never asks the generator where it put things.
    The magic must appear exactly once, so a probe that happened to contain the
    bytes somewhere else, or twice, cannot pass on a coincidence.
    """
    _check_common(PROBE_ID, record, "scaffolding-probe")
    serialized = _stage(PROBE_ID, record, "tx_set")
    raw_bytes = _decode_bytes(PROBE_ID, serialized)

    declarations = record.get("declarations")
    _require(isinstance(declarations, dict), f"{PROBE_ID}: no declarations object")
    offset = declarations.get("magic_offset")
    _require(
        isinstance(offset, int) and not isinstance(offset, bool) and offset >= 0,
        f"{PROBE_ID}: declared magic_offset {offset!r} is not a non-negative integer",
    )
    window = raw_bytes[offset:offset + _MAGIC_LEN]
    _require(
        window == _MAGIC,
        f"{PROBE_ID}: bytes at declared offset {offset} are {window.hex()!r}, "
        f"not the magic {_MAGIC.hex()!r}",
    )
    _require(
        raw_bytes.count(_MAGIC) == 1,
        f"{PROBE_ID}: magic occurs {raw_bytes.count(_MAGIC)} times in the emitted "
        "bytes; the declared offset must be the one embedding",
    )

    # The FILE must carry the magic too, as hex text: that is the property the
    # 0.6 regeneration test rests on. A probe whose file text did not contain
    # the magic would not change hash when the magic constant is flipped, and
    # the test would pass vacuously.
    _require(
        _MAGIC.hex().encode("ascii") in raw.lower(),
        f"{PROBE_ID}: emitted file text does not carry the magic; a magic flip "
        "would not move this artifact's hash",
    )

    _check_manifest_stub(
        PROBE_ID, record,
        ["marker-grammar-DRAFT.md", "composition-handoff-SPEC.md"],
    )
    return {
        "record_id": PROBE_ID,
        "declared_magic_offset": offset,
        "byte_length": len(raw_bytes),
        "pin_hashes": sorted(record["manifest_stub"]["pin_hashes"]),
    }


def verify_control(raw, record):
    """The INVARIANT control: no grammar dependency, at the bytes and at the stub.

    Checked against the FILE bytes, not just the parsed record: the magic must
    not appear anywhere in it, in binary or as hex text, and neither pinned
    hash may appear in it as text. That is what makes it a control — flip the
    magic constant, rebuild, and this file is byte-identical or the 0.6 test is
    vacuous.
    """
    _check_common(CONTROL_ID, record, "scaffolding-control")
    serialized = _stage(CONTROL_ID, record, "header_template")
    raw_bytes = _decode_bytes(CONTROL_ID, serialized)

    _require(
        _MAGIC not in raw_bytes,
        f"{CONTROL_ID}: the control's bytes contain the magic",
    )
    _require(
        _MAGIC.hex().encode("ascii") not in raw.lower(),
        f"{CONTROL_ID}: the control's file text contains the magic as hex",
    )
    _require(
        _MAGIC not in raw,
        f"{CONTROL_ID}: the control's file text contains the magic as ASCII",
    )
    for pin in (EXPECTED_GRAMMAR_SHA256, EXPECTED_SPEC_SHA256):
        _require(
            pin.encode("ascii") not in raw,
            f"{CONTROL_ID}: the control carries a pinned doc hash; it must depend on none",
        )

    # Stage 1 sanity: every declared slot is a real window into the template.
    slots = serialized.get("slots")
    _require(isinstance(slots, list), f"{CONTROL_ID}: header_template carries no slots list")
    for slot in slots:
        _require(isinstance(slot, dict), f"{CONTROL_ID}: malformed slot {slot!r}")
        offset, length = slot.get("offset"), slot.get("length")
        _require(
            isinstance(offset, int) and isinstance(length, int)
            and offset >= 0 and length >= 1 and offset + length <= len(raw_bytes),
            f"{CONTROL_ID}: slot {slot.get('name')!r} is not a window into the template",
        )
        _require(
            raw_bytes[offset:offset + length].hex() == slot.get("bytes_hex"),
            f"{CONTROL_ID}: slot {slot.get('name')!r} bytes disagree with the template",
        )

    _require(
        record.get("declarations") == {},
        f"{CONTROL_ID}: the control declares {record.get('declarations')!r}; it "
        "claims nothing about any pinned constant, which is what makes it a control",
    )
    _check_manifest_stub(CONTROL_ID, record, [])
    return {
        "record_id": CONTROL_ID,
        "byte_length": len(raw_bytes),
        "pin_hashes": sorted(record["manifest_stub"]["pin_hashes"]),
    }


def verify_artifacts(vectors_dir=VECTORS_DIR):
    """Verify the full 0.3 scaffolding inventory. Raises OracleError on any failure."""
    vectors_dir = Path(vectors_dir)
    results = []

    raw, record = load_artifact(vectors_dir / ARTIFACTS[PROBE_ID])
    results.append(verify_probe(raw, record))

    raw, record = load_artifact(vectors_dir / ARTIFACTS[CONTROL_ID])
    results.append(verify_control(raw, record))

    # LF-only over the whole emitted directory, not only the two files the
    # oracle knows by name: a stray CR in anything under vectors/ is a defect.
    for path in sorted(vectors_dir.glob("*")):
        if path.is_file():
            _require(
                b"\r" not in path.read_bytes(),
                f"{path.name}: contains a CR byte; output is LF-only",
            )

    return results


def self_test() -> None:
    # Structure of the transcribed magic, NOT its value. Its value is checked
    # across the files, by generate.cross_check_transcriptions(): the
    # construction side spells the magic in ASCII and this side spells it in hex
    # escapes, so comparing the two catches a transposed byte in either spelling.
    # Restating the value here as a third literal would add a third place a magic
    # flip has to be edited (task 0.6) and would catch nothing the cross-check
    # does not already catch.
    assert len(_MAGIC) == _MAGIC_LEN == 4, _MAGIC
    assert all(0x21 <= b <= 0x7E for b in _MAGIC), _MAGIC  # printable ASCII

    # Integer satoshis: the bound is an int, and the guard rejects a float that
    # compares equal to it as well as a bool that would sneak through as 0/1.
    assert isinstance(_SUPPLY_BOUND_SATS, int) and not isinstance(_SUPPLY_BOUND_SATS, bool)
    assert _SUPPLY_BOUND_SATS == 2100000000000000, _SUPPLY_BOUND_SATS
    assert check_supply_bound(_SUPPLY_BOUND_SATS) == _SUPPLY_BOUND_SATS
    assert check_supply_bound(0) == 0
    for bad in (float(_SUPPLY_BOUND_SATS), True, -1, _SUPPLY_BOUND_SATS + 1):
        try:
            check_supply_bound(bad)
        except OracleError:
            pass
        else:
            raise AssertionError(f"check_supply_bound accepted {bad!r}")

    # The probe check reads the bytes, not the claim: a record whose declared
    # offset does not hold the magic must fail even though the magic is present.
    good = {
        "record_id": PROBE_ID,
        "kind": "scaffolding-probe",
        "status": STATUS,
        "declarations": {"magic_offset": 1},
        "stages": [{
            "stage": "tx_set",
            "serialized": {"bytes_hex": "00" + _MAGIC.hex(), "length": 5},
        }],
        "manifest_stub": {
            "depends_on": sorted(["marker-grammar-DRAFT.md", "composition-handoff-SPEC.md"]),
            "pin_hashes": {
                "grammar_doc_sha256": EXPECTED_GRAMMAR_SHA256,
                "spec_sha256": EXPECTED_SPEC_SHA256,
            },
        },
        "notes": "",
    }
    good_raw = json.dumps(good).encode("utf-8")
    verify_probe(good_raw, good)

    lying = json.loads(json.dumps(good))
    lying["declarations"]["magic_offset"] = 0
    try:
        verify_probe(good_raw, lying)
    except OracleError:
        pass
    else:
        raise AssertionError("verify_probe trusted a wrong declared offset")

    dropped = json.loads(json.dumps(good))
    dropped["manifest_stub"]["pin_hashes"].pop("grammar_doc_sha256")
    try:
        verify_probe(json.dumps(dropped).encode("utf-8"), dropped)
    except OracleError:
        pass
    else:
        raise AssertionError("verify_probe accepted a probe missing its grammar pin")

    print("verify.self_test: OK")


def main():
    self_test()
    try:
        results = verify_artifacts()
    except OracleError as exc:
        print(f"ORACLE FAIL: {exc}", file=sys.stderr)
        return 1
    print(f"Seam oracle (task 0.3 scaffolding) — status {STATUS}")
    for r in results:
        pins = ", ".join(r["pin_hashes"]) or "none"
        print(f"  {r['record_id']:<14} {r['byte_length']:>3} bytes   pins: {pins}")
    print("ORACLE GREEN: both scaffolding artifacts verified against own literals.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
