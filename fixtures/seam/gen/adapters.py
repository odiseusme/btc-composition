"""adapters.py — the ownership-neutrality layer (risk R2, all stages).

WHY THIS FILE EXISTS. Decision 14.5 (which side of the seam owns which
construction machinery) has not landed. Any code that hard-wires an
ownership assumption now is code that has to be rewritten when it does, and
worse, code whose fixtures silently encode the assumption. So this lane
builds every stage behind a REPLACEABLE ADAPTER BOUNDARY, and the boundary
is defined by SERIALIZATION, not by an object graph.

THE CONTRACT, identical for all four stages:

    adapter(serialized_input: dict) -> {"stage": <name>, "serialized": dict}

  * The input is JSON-safe data: dicts, lists, str, int, bool, None. Byte
    material crosses the boundary as hex text. Nothing else is accepted —
    not an object, not a callable, not a module-level constant reached
    behind the caller's back.
  * The output is JSON-safe data, wrapped in a stage envelope.
  * Therefore ANY stage's input can be supplied from outside this package:
    written by hand, read from a file, or produced by the other side of the
    seam once 14.5 says who that is. check_scaffolding.py check (g) proves
    exactly this by constructing each stage's input purely from literals in
    the test and getting the same output back.

NO STAGE CALLS ANOTHER STAGE'S INTERNALS. Cross-stage flow happens only by
passing one adapter's serialized output into another adapter's serialized
input, and the caller — never an adapter — decides that flow. There is no
orchestrator in this package and there will not be one before task 5a.2:
identity-bearing construction ordering (the box id / payload / txid / proof
chain) is exactly what 14.5 gates, so composing those steps in a fixed
sequence anywhere in Phase 0 or Phase 1 code is banned.

NAMING IS PART OF THE CONTRACT. No adapter, function, or emitted field may
assign machinery ownership. The stage names are the four neutral layers of
the seam — tx_set, proof, header_template, packaging — and they name WHAT is
serialized, never WHO serialized it. A whole class of identifiers is banned
outright anywhere in fixtures/seam/gen/ because each one presumes the pending
split: box-id derivation calls, txid-from-payload helpers, payload-assembly
functions, and any function that composes payload, txid, and proof in a fixed
sequence.

The banned names are enumerated ONCE, in check_scaffolding.BANNED_IDENTIFIERS,
and are deliberately not spelled out here: the property under test is that a
plain grep for any of them over this directory finds nothing, and a file that
wrote them down in order to describe the ban would be the one hit. Checks (e)
and (f) enforce both halves of the rule mechanically.

SCOPE AT TASK 0.3. These adapters carry structural serialization only:
lengths, offsets, slices, counts. They assert no protocol layout, no
byte-order convention, and no failure category. Those are Phase 1 facts,
declared per family against the SPEC, and they will arrive as adapter INPUT.
"""

import json

STAGES = ("tx_set", "proof", "header_template", "packaging")

# The adapter's own input-validation rule for byte material: even-length,
# lowercase hex. This is a boundary contract, not a manifest schema rule —
# manifest hex-case policy belongs to decision 14.3 and task 5b.9, and is
# deliberately not decided here.
_HEX_DIGITS = "0123456789abcdef"


class AdapterContractError(ValueError):
    """Raised when an adapter is handed something that is not serialized data.

    This is the boundary doing its job: an adapter that accepted a live
    object would be an adapter through which ownership could leak.
    """


def _require_json_safe(where, value):
    """Reject anything that could not have arrived as a JSON document."""
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, (str, int)):
        return value
    if isinstance(value, float):
        raise AdapterContractError(
            f"{where}: float crossed the boundary; satoshi and byte counts "
            "are integers in this lane"
        )
    if isinstance(value, dict):
        for key, sub in value.items():
            if not isinstance(key, str):
                raise AdapterContractError(f"{where}: non-string key {key!r}")
            _require_json_safe(f"{where}.{key}", sub)
        return value
    if isinstance(value, list):
        for i, sub in enumerate(value):
            _require_json_safe(f"{where}[{i}]", sub)
        return value
    raise AdapterContractError(
        f"{where}: {type(value).__name__} is not serialized data; adapters "
        "consume and produce JSON-safe values only (bytes travel as hex text)"
    )


def _require_dict(where, value):
    if not isinstance(value, dict):
        raise AdapterContractError(f"{where}: expected a dict, got {type(value).__name__}")
    _require_json_safe(where, value)
    return value


def _require_keys(where, mapping, required):
    missing = [k for k in required if k not in mapping]
    if missing:
        raise AdapterContractError(f"{where}: missing key(s) {sorted(missing)}")
    unknown = [k for k in mapping if k not in required]
    if unknown:
        raise AdapterContractError(f"{where}: unknown key(s) {sorted(unknown)}")


def _require_hex(where, value):
    """Even-length lowercase hex text; returns the decoded bytes."""
    if not isinstance(value, str):
        raise AdapterContractError(f"{where}: expected hex text, got {type(value).__name__}")
    if len(value) % 2:
        raise AdapterContractError(f"{where}: odd-length hex ({len(value)} chars)")
    bad = sorted({c for c in value if c not in _HEX_DIGITS})
    if bad:
        raise AdapterContractError(
            f"{where}: non-lowercase-hex character(s) {bad} — byte material "
            "crosses the boundary as even-length lowercase hex"
        )
    return bytes.fromhex(value)


def _require_int(where, value, minimum=0):
    if isinstance(value, bool) or not isinstance(value, int):
        raise AdapterContractError(f"{where}: expected an int, got {value!r}")
    if value < minimum:
        raise AdapterContractError(f"{where}: {value} < {minimum}")
    return value


def _envelope(stage, serialized):
    return {"stage": stage, "serialized": _require_dict(f"{stage}.serialized", serialized)}


def _deep_copy(value):
    """A copy that shares nothing with the caller's data.

    A JSON round trip is the right copy here rather than an approximation of
    one: the boundary contract already says the value is JSON-safe, so a value
    that cannot survive this is a value that had no business crossing.
    """
    return json.loads(json.dumps(value))


def tx_set_adapter(serialized_input):
    """Stage tx_set: an ordered list of byte segments becomes one byte string.

    Input:  {"segments": [<hex>, ...]}
    Output: {"bytes_hex", "length", "segment_lengths", "segment_offsets"}

    The adapter concatenates in the order given and reports where each
    segment landed. It does not know what any segment MEANS: the caller
    supplies the bytes, so a magic-bearing segment, a script, or a whole
    stripped transaction all route through unchanged. Offsets are reported,
    never asserted — the caller declares which offset it cares about, and
    the oracle re-derives that offset from the emitted bytes independently.
    """
    _require_dict("tx_set input", serialized_input)
    _require_keys("tx_set input", serialized_input, {"segments"})

    segments = serialized_input["segments"]
    if not isinstance(segments, list) or not segments:
        raise AdapterContractError("tx_set input.segments: expected a non-empty list")

    blobs = [_require_hex(f"tx_set input.segments[{i}]", h) for i, h in enumerate(segments)]

    offsets, acc = [], 0
    for blob in blobs:
        offsets.append(acc)
        acc += len(blob)
    raw = b"".join(blobs)

    return _envelope("tx_set", {
        "bytes_hex": raw.hex(),
        "length": len(raw),
        "segment_lengths": [len(b) for b in blobs],
        "segment_offsets": offsets,
    })


def proof_adapter(serialized_input):
    """Stage proof: an ordered element list plus its flag bytes.

    Input:  {"elements": [<hex>, ...], "flags_hex": <hex>}
    Output: {"elements", "element_lengths", "element_count", "flags_hex",
             "flag_byte_count"}

    Structural only. Element widths, flag semantics, and the empty-proof
    boundary are SPEC facts declared per vector in Phase 1 (family V11) and
    arrive here as input; this adapter neither validates them nor hashes
    anything. It computes no root and consumes no transaction: a proof's
    relationship to a tx set is the caller's to state, not this boundary's
    to assume.
    """
    _require_dict("proof input", serialized_input)
    _require_keys("proof input", serialized_input, {"elements", "flags_hex"})

    elements = serialized_input["elements"]
    if not isinstance(elements, list):
        raise AdapterContractError("proof input.elements: expected a list")

    blobs = [_require_hex(f"proof input.elements[{i}]", h) for i, h in enumerate(elements)]
    flags = _require_hex("proof input.flags_hex", serialized_input["flags_hex"])

    return _envelope("proof", {
        "elements": [b.hex() for b in blobs],
        "element_lengths": [len(b) for b in blobs],
        "element_count": len(blobs),
        "flags_hex": flags.hex(),
        "flag_byte_count": len(flags),
    })


def header_template_adapter(serialized_input):
    """Stage header_template: a byte template plus named slots into it.

    Input:  {"template_hex": <hex>,
             "slots": [{"name", "offset", "length"}, ...]}
    Output: {"bytes_hex", "length", "slots": [... plus "bytes_hex" per slot]}

    A slot is a named window into the template. The adapter checks only that
    each window lies inside the template and returns the bytes it selects. It
    fixes no field order, no header layout, and no chain: what the template
    IS arrives as input.
    """
    _require_dict("header_template input", serialized_input)
    _require_keys("header_template input", serialized_input, {"template_hex", "slots"})

    template = _require_hex("header_template input.template_hex", serialized_input["template_hex"])
    slots = serialized_input["slots"]
    if not isinstance(slots, list):
        raise AdapterContractError("header_template input.slots: expected a list")

    out_slots, seen = [], set()
    for i, slot in enumerate(slots):
        where = f"header_template input.slots[{i}]"
        _require_dict(where, slot)
        _require_keys(where, slot, {"name", "offset", "length"})
        name = slot["name"]
        if not isinstance(name, str) or not name:
            raise AdapterContractError(f"{where}.name: expected a non-empty string")
        if name in seen:
            raise AdapterContractError(f"{where}.name: duplicate slot name {name!r}")
        seen.add(name)
        offset = _require_int(f"{where}.offset", slot["offset"])
        length = _require_int(f"{where}.length", slot["length"], minimum=1)
        if offset + length > len(template):
            raise AdapterContractError(
                f"{where}: slot [{offset}, {offset + length}) runs past the "
                f"{len(template)}-byte template"
            )
        out_slots.append({
            "name": name,
            "offset": offset,
            "length": length,
            "bytes_hex": template[offset:offset + length].hex(),
        })

    return _envelope("header_template", {
        "bytes_hex": template.hex(),
        "length": len(template),
        "slots": out_slots,
    })


def packaging_adapter(serialized_input):
    """Stage packaging: already-serialized stage envelopes become one record.

    Input:  {"record_id", "kind", "status", "stages": [<envelope>, ...],
             "declarations": {...}, "manifest_stub": {...}, "notes"}
    Output: the artifact record, JSON-safe.

    declarations is the record's own CLAIMS about its stages — the probe's
    magic offset, later a family's expected failure category. They pass through
    the boundary as serialized data like everything else, so nothing is bolted
    onto a record after it leaves the adapter, and the oracle can re-derive
    each claim from the emitted bytes and disagree with it.

    THIS IS NOT AN ORCHESTRATOR, and the distinction is the whole point of
    risk R2. Packaging does not call another adapter, does not know what a
    tx_set or a proof means, and imposes no order on the stages it is
    handed: it takes the list the CALLER built, in the CALLER's order, and
    wraps it. There is deliberately no code path anywhere in this package
    that chains payload, txid, and proof in a fixed sequence — that chain is
    exactly what decision 14.5 gates and task 5a.2 owns.

    manifest_stub carries the hash of each pinned document the record's bytes
    depend on, and nothing more. It is a STUB: the manifest schema (field
    names, layout, hex case, unknown-field policy) is owned by decision 14.3
    and task 5b.9, and is not being defined here. The pin-hash field is the
    one thing the 0.2 procedure needs from day one, because the invalidation
    set of a moved pin is derived mechanically by scanning these fields for
    the pin's old value.

    THE RECORD IS A DEEP COPY of the accepted input, and this is not a detail:
    the stage envelopes and the manifest stub arrive as the caller's own live
    dicts, so a record that merely referenced them would keep changing after it
    was packaged. Anything the caller touched afterwards would silently reach the
    emitted bytes, the oracle replay, and the determinism comparison — all of
    which run on the record this function returned. A packaged record is a fact
    about the moment it was packaged, so nothing outside it may still hold a
    handle on its parts.
    """
    _require_dict("packaging input", serialized_input)
    _require_keys("packaging input", serialized_input, {
        "record_id", "kind", "status", "stages", "declarations",
        "manifest_stub", "notes",
    })

    stages = serialized_input["stages"]
    if not isinstance(stages, list) or not stages:
        raise AdapterContractError("packaging input.stages: expected a non-empty list")

    packed = []
    for i, env in enumerate(stages):
        where = f"packaging input.stages[{i}]"
        _require_dict(where, env)
        _require_keys(where, env, {"stage", "serialized"})
        stage = env["stage"]
        if stage not in STAGES or stage == "packaging":
            raise AdapterContractError(
                f"{where}.stage: {stage!r} is not one of the serialized stages "
                f"{[s for s in STAGES if s != 'packaging']}"
            )
        _require_dict(f"{where}.serialized", env["serialized"])
        packed.append({"stage": stage, "serialized": env["serialized"]})

    manifest_stub = _require_dict("packaging input.manifest_stub", serialized_input["manifest_stub"])
    _require_keys("packaging input.manifest_stub", manifest_stub, {"depends_on", "pin_hashes"})
    declarations = _require_dict("packaging input.declarations", serialized_input["declarations"])

    for key in ("record_id", "kind", "status", "notes"):
        if not isinstance(serialized_input[key], str):
            raise AdapterContractError(f"packaging input.{key}: expected a string")

    return _envelope("packaging", _deep_copy({
        "record_id": serialized_input["record_id"],
        "kind": serialized_input["kind"],
        "status": serialized_input["status"],
        "stages": packed,
        "declarations": declarations,
        "manifest_stub": manifest_stub,
        "notes": serialized_input["notes"],
    }))


# The registry is the boundary made enumerable: check_scaffolding.py's
# externality test walks it and supplies every stage's input from serialized
# literals of its own.
ADAPTERS = {
    "tx_set": tx_set_adapter,
    "proof": proof_adapter,
    "header_template": header_template_adapter,
    "packaging": packaging_adapter,
}


def self_test() -> None:
    assert tuple(ADAPTERS) == STAGES, tuple(ADAPTERS)

    # tx_set concatenates in order and reports where each segment landed.
    env = tx_set_adapter({"segments": ["0001", "ff", ""]})
    assert env["stage"] == "tx_set"
    assert env["serialized"]["bytes_hex"] == "0001ff"
    assert env["serialized"]["length"] == 3
    assert env["serialized"]["segment_offsets"] == [0, 2, 3]
    assert env["serialized"]["segment_lengths"] == [2, 1, 0]

    # proof is structural: counts and lengths, no hashing, no root.
    env = proof_adapter({"elements": ["aa" * 32, "bb" * 34], "flags_hex": "02"})
    assert env["serialized"]["element_count"] == 2
    assert env["serialized"]["element_lengths"] == [32, 34]
    assert env["serialized"]["flag_byte_count"] == 1

    # header_template slots are windows, and they must lie inside the template.
    env = header_template_adapter({
        "template_hex": "00112233",
        "slots": [{"name": "first_half", "offset": 0, "length": 2}],
    })
    assert env["serialized"]["slots"][0]["bytes_hex"] == "0011"
    try:
        header_template_adapter({
            "template_hex": "0011",
            "slots": [{"name": "over", "offset": 1, "length": 2}],
        })
    except AdapterContractError:
        pass
    else:
        raise AssertionError("header_template accepted a slot past the template")

    # packaging preserves the caller's stage order and imposes none of its own.
    a = tx_set_adapter({"segments": ["00"]})
    b = header_template_adapter({"template_hex": "11", "slots": []})
    rec = packaging_adapter({
        "record_id": "selftest",
        "kind": "selftest",
        "status": "PRE-FREEZE",
        "stages": [b, a],
        "declarations": {"example_offset": 0},
        "manifest_stub": {"depends_on": [], "pin_hashes": {}},
        "notes": "",
    })["serialized"]
    assert [s["stage"] for s in rec["stages"]] == ["header_template", "tx_set"]
    assert rec["declarations"] == {"example_offset": 0}

    # The packaged record shares nothing with the input it was built from: a
    # caller that keeps mutating its own envelopes and stub after packaging
    # cannot reach back into the record the oracle and the emitter will read.
    stub = {"depends_on": [], "pin_hashes": {}}
    sealed = packaging_adapter({
        "record_id": "selftest-copy",
        "kind": "selftest",
        "status": "PRE-FREEZE",
        "stages": [a],
        "declarations": {},
        "manifest_stub": stub,
        "notes": "",
    })["serialized"]
    a["serialized"]["bytes_hex"] = "ff"
    stub["pin_hashes"]["late_addition"] = "reached the record"
    assert sealed["stages"][0]["serialized"]["bytes_hex"] == "00", sealed
    assert sealed["manifest_stub"]["pin_hashes"] == {}, sealed

    # The boundary rejects anything that is not serialized data.
    for bad in (b"\x00", object(), 1.5):
        try:
            tx_set_adapter({"segments": [bad]})
        except AdapterContractError:
            pass
        else:
            raise AssertionError(f"tx_set accepted unserialized input {bad!r}")

    print("adapters.self_test: OK")


if __name__ == "__main__":
    self_test()
