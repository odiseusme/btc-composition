"""generate.py — the seam scaffolding pipeline (task 0.3).

Order of operations (aborts loudly on any failure):
  1. GATE on BOTH pinned documents: reject any CR byte, hash the exact
     LF-only bytes, compare to the pins in constants.py. The grammar doc and
     the pre-freeze SPEC are gated the same way and with equal force — the
     seam's byte-identity claim is stated by the SPEC and the payload layer
     by the grammar, and a fixture built against a moved copy of either is a
     fixture that proves nothing.
  2. Run the constants / adapters / oracle self-tests in-process.
  3. TRANSCRIPTION CROSS-CHECK: the construction side and the oracle
     transcribe the shared normative constants independently; compare the two
     copies, and first prove they are still two copies.
  4. Build the two scaffolding artifacts through the adapter boundaries.
  5. Replay the ORACLE over what was built, in memory, before writing.
  6. Determinism: build the full set twice; byte-identical.
  7. Emit LF-only into a CALLER-SUPPLIED directory: stage every temp file
     first, then replace them all.

Steps 1 to 7 are run_pipeline(out_dir). The output directory is a parameter so
that a caller can drive the whole pipeline into a scratch directory and compare
what it produces against the committed vectors WITHOUT overwriting them first;
main() passes the committed vectors/ and is what production regeneration (0.6)
calls, and check_scaffolding.py passes a temporary directory so that acceptance
attests the committed bytes rather than bytes it just wrote itself.

THE MAGIC LIVES HERE, IN ONE PLACE (_MAGIC below): this is the only
construction-side copy in the lane, and constants.py deliberately does not
hold it. Task 0.6's regeneration test flips it and requires the probe's hash
to change and the control's not to; a second construction-side copy would
make the flip incomplete and the test a lie.

NOTE FOR THE 0.6 BUILDER. The oracle keeps its OWN transcription of the magic
(verify._MAGIC) — it has to, or it would be checking the generator's bytes
against the generator's own constant. So the lane holds exactly two copies, by
design, and a flip is a two-line edit: the ASCII literal here and the hex-escape
literal there. That is not a loophole in the "single location" rule, it is the
oracle boundary: a ONE-SIDED flip does not silently produce a wrong artifact,
it aborts at cross_check_transcriptions() naming both values. The two spellings
are also the point — comparing an ASCII literal against a hex-escape literal is
what catches a transposed byte in either.

Second note for 0.6, learned the hard way while proving the probe/control pair
behaves: "clean state" must include the bytecode cache. Flipping the magic
changes neither file's SIZE, and an edit made in the same second as the last
run leaves the mtime unchanged too, so CPython happily reuses a stale .pyc for
the imported oracle and the "rebuild" silently rebuilds nothing. A flip test
that skips this passes VACUOUSLY, byte-identical for the wrong reason. Clear
__pycache__/ or run with PYTHONDONTWRITEBYTECODE=1.

WHAT IS NOT HERE, AND WILL NOT BE BEFORE 5a.2: any function that chains
payload, txid, and proof in a fixed sequence. Stages are built independently
and handed to the packaging boundary as serialized envelopes, in an order
this file chooses per artifact and no adapter knows about. That is risk R2
discipline, and it is checked mechanically by check_scaffolding.py.
"""

import hashlib
import json
import os
import sys
from pathlib import Path

import adapters
import constants
import verify

REPO_ROOT = Path(__file__).resolve().parents[3]
GRAMMAR_DOC = REPO_ROOT / "marker-grammar-DRAFT.md"
SPEC_DOC = REPO_ROOT / "composition-handoff-SPEC.md"
SEAM_DIR = REPO_ROOT / "fixtures" / "seam"
VECTORS_DIR = SEAM_DIR / "vectors"
PINS_LEDGER = SEAM_DIR / "PINS.md"

# --- The single construction-side copy of the payload magic ----------------
# marker-grammar-DRAFT.md Section 1: ASCII "ERGV". Flipping THIS constant is
# the 0.6 regeneration test. The oracle keeps its own transcription and the
# two are compared at every run.
_MAGIC = b"ERGV"

# Scaffolding filler around the magic. These bytes carry NO protocol meaning:
# the probe asserts no layout, only that the magic is embedded at a declared
# offset in bytes routed through the tx_set boundary. Real layouts arrive in
# Phase 1, per family, declared against the SPEC.
_PROBE_PREFIX = bytes([0x00, 0x01, 0x02, 0x03])
_PROBE_SUFFIX = bytes([0xFF])

# The control's template: eight zero bytes, two named windows. No magic, no
# grammar constant, nothing derived from either pinned document.
_CONTROL_TEMPLATE = bytes(8)

# Names that must NEVER be bound in the oracle's namespace. It imports a
# bookkeeping-only whitelist from constants.py and transcribes the rest; if
# one of these shows up there, that import line has grown a value the oracle
# was supposed to be transcribing, and the comparisons below quietly become
# comparisons of a value with itself.
FORBIDDEN_VERIFY_IMPORTS = ("SUPPLY_BOUND_SATS", "PRODUCER_PR_HEAD", "CONSUMER_PR_HEAD")

# The ledger's EXPECTED-pin section, and the label each gate constant must be
# declared under. The section is parsed; the file is never searched as a whole.
# The check log below that section records the ACTUAL values seen at each check,
# including every value that has since MOVED, so a substring search over the
# whole document is satisfied by a stale digest sitting in the history — which is
# precisely the one-sided edit (gate moved, expected pins not) that this check
# exists to catch.
_LEDGER_PIN_HEADING = "## Expected pins"
_LEDGER_PIN_LABELS = (
    ("EXPECTED_GRAMMAR_SHA256", "grammar doc sha256"),
    ("EXPECTED_SPEC_SHA256", "spec pre-freeze sha256"),
    ("PRODUCER_PR_HEAD", "producer pr head"),
    ("CONSUMER_PR_HEAD", "consumer pr head"),
)

_PROBE_NOTE = (
    "Scaffolding probe (task 0.3). Magic-DEPENDENT target for the 0.6 "
    "regeneration test: its bytes embed the 4-byte payload magic at "
    "magic_offset, routed through the tx_set adapter boundary. The surrounding "
    "bytes are filler and assert no layout. manifest_stub carries the hash of "
    "each pinned document these bytes depend on, which is what the 0.2 "
    "procedure scans to derive an invalidation set."
)

_CONTROL_NOTE = (
    "Scaffolding control (task 0.3). INVARIANT control for the 0.6 "
    "regeneration test: a header_template record with no grammar dependency — "
    "no magic in its bytes, no pin hash in its manifest stub. Flipping the "
    "magic constant must leave this file byte-identical; without that, the "
    "regeneration test cannot tell a working rebuild from one that rewrites "
    "everything. This record is the invariant for MAGIC flips specifically: "
    "the 0.2 pin-scan derives invalidation sets for document pin movements, "
    "and the 7.1 freeze re-pins the gate constants themselves, which are "
    "inputs to every artifact, so the freeze regenerates the full inventory by "
    "its own procedure, outside pin-scan selection."
)


def _fail(msg):
    print(msg, file=sys.stderr)
    sys.exit(1)


def _gate_one_doc(path, expected_sha256, label):
    """Hash a normative doc's EXACT bytes, read in BINARY.

    A CRLF checkout would change every line's bytes and so change the digest;
    the gate names that cause explicitly instead of reporting a bogus "doc
    changed". The pinned hashes are over LF-only bytes.
    """
    if not path.exists():
        _fail(f"GATE: {label} not found at {path}")
    raw = path.read_bytes()
    if b"\r" in raw:
        _fail(f"GATE: CRLF checkout detected in {label} — fix line endings")
    digest = hashlib.sha256(raw).hexdigest()
    if digest != expected_sha256:
        _fail(
            f"GATE: {label} changed.\n"
            f"  expected {expected_sha256}\n"
            f"  actual   {digest}\n"
            "Generation is HALTED. This is a pin movement: run the task 0.2 "
            "procedure (fixtures/seam/README.md) — seam-surface re-verification, "
            "invalidation set derived from the manifest pin-hash fields, ledger "
            "and gate updated in one commit — before regenerating anything."
        )
    return digest


def gate_docs():
    """GATE on both pinned documents. Returns (grammar_sha256, spec_sha256)."""
    grammar_sha = _gate_one_doc(
        GRAMMAR_DOC, constants.EXPECTED_GRAMMAR_SHA256, "marker-grammar-DRAFT.md"
    )
    spec_sha = _gate_one_doc(
        SPEC_DOC, constants.EXPECTED_SPEC_SHA256,
        f"composition-handoff-SPEC.md ({constants.STATUS})",
    )
    return grammar_sha, spec_sha


def _ledger_expected_pins():
    """Parse PINS.md's expected-pin section into [(label, value), ...].

    The section is a bullet list, and a bullet's value may continue on the
    indented lines under it — the 64-hex digests are wrapped that way. Each
    bullet yields its label (lowercased, everything before the first colon) and
    its value (the first whitespace-delimited token after that colon), so a
    trailing parenthetical like the SPEC's PRE-FREEZE marker is not mistaken for
    part of the digest.
    """
    if not PINS_LEDGER.exists():
        _fail(f"PIN LEDGER: {PINS_LEDGER} is missing")

    lines = PINS_LEDGER.read_text(encoding="utf-8").splitlines()
    start = next(
        (i for i, line in enumerate(lines) if line.startswith(_LEDGER_PIN_HEADING)), None
    )
    if start is None:
        _fail(
            f"PIN LEDGER: {PINS_LEDGER.name} has no '{_LEDGER_PIN_HEADING}' section; "
            "the expected pins are the only part of the ledger the gate is checked "
            "against (the check log records actuals, including moved ones)"
        )

    bullets = []
    for line in lines[start + 1:]:
        if line.startswith("## "):
            break
        stripped = line.strip()
        if stripped.startswith("- "):
            bullets.append([stripped[2:]])
        elif stripped and bullets:
            bullets[-1].append(stripped)

    pins = []
    for bullet in bullets:
        label, sep, value = " ".join(bullet).partition(":")
        if not sep:
            continue
        tokens = value.split()
        pins.append((label.strip().lower(), tokens[0] if tokens else ""))
    return pins


def cross_check_transcriptions():
    """The construction side vs. the oracle, at every run.

    Both sides transcribe the same normative constants from the pinned
    documents and must not import each other's values. That redundancy buys
    nothing unless something actually COMPARES the two copies: without a
    comparison, a divergence just yields two internally self-consistent halves
    and the build stays green.

    A disagreement here is a BUILD FAILURE, not a warning.
    """
    # The comparison is only meaningful while the copies are independent. If
    # the oracle ever IMPORTS one of these instead of transcribing it, every
    # assertion below degrades into a tautology. Catch that first.
    leaked = [n for n in FORBIDDEN_VERIFY_IMPORTS if hasattr(verify, n)]
    if leaked:
        _fail(
            "TRANSCRIPTION CROSS-CHECK: verify.py binds "
            + ", ".join(leaked)
            + " from constants.py; these must be retranscribed, not imported"
        )
    for module_name in ("adapters", "generate"):
        if module_name in vars(verify):
            _fail(f"TRANSCRIPTION CROSS-CHECK: verify.py imports {module_name}")

    # marker-grammar-DRAFT.md Section 1: the payload magic.
    if _MAGIC != verify._MAGIC:
        _fail(
            "TRANSCRIPTION CROSS-CHECK: the payload magic disagrees — "
            f"generate {_MAGIC!r} != verify {verify._MAGIC!r}"
        )

    # Section 3 rule 7: the supply bound, and its integer discipline.
    if constants.SUPPLY_BOUND_SATS != verify._SUPPLY_BOUND_SATS:
        _fail(
            "TRANSCRIPTION CROSS-CHECK: SUPPLY_BOUND_SATS disagrees — "
            f"constants {constants.SUPPLY_BOUND_SATS} != "
            f"verify {verify._SUPPLY_BOUND_SATS}"
        )
    for label, value in (
        ("constants.SUPPLY_BOUND_SATS", constants.SUPPLY_BOUND_SATS),
        ("verify._SUPPLY_BOUND_SATS", verify._SUPPLY_BOUND_SATS),
    ):
        if not isinstance(value, int) or isinstance(value, bool):
            _fail(f"TRANSCRIPTION CROSS-CHECK: {label} is not an integer ({value!r})")

    # The gate pins the oracle checks manifests against are the ones this side
    # gates the documents with. They are shared bookkeeping, so this is an
    # identity check by construction — and it is here so that a future edit
    # giving the oracle its own copy of a pin cannot pass silently.
    if verify.EXPECTED_GRAMMAR_SHA256 != constants.EXPECTED_GRAMMAR_SHA256:
        _fail("TRANSCRIPTION CROSS-CHECK: EXPECTED_GRAMMAR_SHA256 disagrees")
    if verify.EXPECTED_SPEC_SHA256 != constants.EXPECTED_SPEC_SHA256:
        _fail("TRANSCRIPTION CROSS-CHECK: EXPECTED_SPEC_SHA256 disagrees")
    if verify.STATUS != constants.STATUS:
        _fail("TRANSCRIPTION CROSS-CHECK: STATUS disagrees")

    # THE LEDGER AND THE GATE CANNOT DISAGREE (0.2 step 4). Every pin the gate
    # enforces must be DECLARED, under its own label and exactly once, in the
    # ledger's expected-pin section. The comparison is against that section
    # alone: a pin is agreed only where the ledger says what it EXPECTS, never
    # where it records what some past check happened to see.
    declared = _ledger_expected_pins()
    for const_name, label in _LEDGER_PIN_LABELS:
        expected = getattr(constants, const_name)
        matches = [value for lab, value in declared if lab.startswith(label)]
        if not matches:
            _fail(
                f"PIN LEDGER: no expected-pin entry labelled '{label}' in the "
                f"'{_LEDGER_PIN_HEADING}' section of PINS.md; the gate holds "
                f"{const_name} = {expected}"
            )
        if len(matches) > 1:
            _fail(
                f"PIN LEDGER: {len(matches)} expected-pin entries labelled "
                f"'{label}' ({', '.join(matches)}); each pin is declared exactly "
                "once, or 'the ledger agrees' means whichever copy was read first"
            )
        if matches[0] != expected:
            _fail(
                f"PIN LEDGER: {const_name} disagrees with the ledger.\n"
                f"  gate   {expected}\n"
                f"  ledger {matches[0]}  (expected-pin entry '{label}')\n"
                "The gate and the ledger move in the same commit (0.2 step 4) — "
                "they may never disagree."
            )


def build_probe(grammar_sha, spec_sha):
    """The magic-embedding probe, routed through the tx_set boundary.

    The magic is passed to the adapter as one serialized segment among
    several: the adapter is handed hex text and hands back hex text, and it
    neither knows nor asks what the segment means. The offset is then READ
    BACK from the adapter's own segment_offsets rather than being asserted
    here, so the number the record declares is the number the serialization
    actually produced.
    """
    segments = [_PROBE_PREFIX.hex(), _MAGIC.hex(), _PROBE_SUFFIX.hex()]
    tx_set = adapters.tx_set_adapter({"segments": segments})
    magic_offset = tx_set["serialized"]["segment_offsets"][1]

    return adapters.packaging_adapter({
        "record_id": verify.PROBE_ID,
        "kind": "scaffolding-probe",
        "status": constants.STATUS,
        "stages": [tx_set],
        "declarations": {"magic_offset": magic_offset},
        "manifest_stub": {
            "depends_on": sorted(["marker-grammar-DRAFT.md", "composition-handoff-SPEC.md"]),
            "pin_hashes": {
                "grammar_doc_sha256": grammar_sha,
                "spec_sha256": spec_sha,
            },
        },
        "notes": _PROBE_NOTE,
    })["serialized"]


def build_control():
    """The invariant control: header_template boundary, no grammar dependency.

    It takes no document hash as an argument, which is the point — there is no
    parameter through which a pin could reach these bytes.
    """
    header_template = adapters.header_template_adapter({
        "template_hex": _CONTROL_TEMPLATE.hex(),
        "slots": [
            {"name": "slot_a", "offset": 0, "length": 4},
            {"name": "slot_b", "offset": 4, "length": 4},
        ],
    })

    return adapters.packaging_adapter({
        "record_id": verify.CONTROL_ID,
        "kind": "scaffolding-control",
        "status": constants.STATUS,
        "stages": [header_template],
        "declarations": {},
        "manifest_stub": {"depends_on": [], "pin_hashes": {}},
        "notes": _CONTROL_NOTE,
    })["serialized"]


def build_artifacts(grammar_sha, spec_sha):
    """Compute {filename: text} for the whole 0.3 scaffolding inventory."""
    records = {
        verify.PROBE_ID: build_probe(grammar_sha, spec_sha),
        verify.CONTROL_ID: build_control(),
    }
    return {
        verify.ARTIFACTS[rid]: json.dumps(rec, indent=2, sort_keys=True) + "\n"
        for rid, rec in records.items()
    }, records


def emit(out_dir, texts):
    """Stage EVERY temp file, then replace them all. Emits into out_dir.

    The atomicity unit is still the PER-FILE os.replace; the set as a whole is
    not atomic, and no arrangement of ordinary POSIX calls makes it so. What
    staging every write before the first replace buys is a narrower window: the
    directory can hold a mix of old and new artifacts only for the duration of
    the replace loop, not for as long as it takes to serialize the inventory. A
    build that aborts partway through serialization now leaves the committed set
    untouched rather than half-rewritten.

    newline="\\n" is explicit: no platform translation, LF-only output, matching
    the CR-rejecting document gate and the oracle's byte-level LF check.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    staged = []
    for filename, text in sorted(texts.items()):
        target = out_dir / filename
        tmp = target.with_name(target.name + ".tmp")
        with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        staged.append((tmp, target))

    for tmp, target in staged:
        os.replace(tmp, target)


def run_pipeline(out_dir):
    """The whole pipeline, steps 1 to 7, emitting into out_dir.

    Returns (grammar_sha, spec_sha, texts, records). out_dir is a PARAMETER and
    not the module's VECTORS_DIR constant so that acceptance can rebuild into a
    scratch directory and byte-compare against the committed vectors instead of
    overwriting them and then attesting its own output.
    """
    # 1. GATE on both pinned documents.
    grammar_sha, spec_sha = gate_docs()

    # 2. Self-tests, in-process.
    constants.self_test()
    adapters.self_test()
    verify.self_test()

    # 3. TRANSCRIPTION CROSS-CHECK.
    cross_check_transcriptions()

    # 4. Build through the adapter boundaries.
    texts, records = build_artifacts(grammar_sha, spec_sha)

    # 5. ORACLE REPLAY, before anything is written. The oracle works on the
    #    emitted file bytes, so hand it the exact text that is about to be
    #    written, not the in-memory record.
    for rid, filename in verify.ARTIFACTS.items():
        raw = texts[filename].encode("utf-8")
        checker = verify.verify_probe if rid == verify.PROBE_ID else verify.verify_control
        try:
            checker(raw, json.loads(raw.decode("utf-8")))
        except verify.OracleError as exc:
            _fail(f"ORACLE REPLAY: {exc}")

    # 6. Determinism: a second independent build must be byte-identical.
    texts2, _ = build_artifacts(grammar_sha, spec_sha)
    if texts != texts2:
        _fail("determinism: second build differs from the first")

    # 7. Emit.
    emit(out_dir, texts)
    return grammar_sha, spec_sha, texts, records


def main():
    """Production regeneration: run the pipeline over the committed vectors."""
    grammar_sha, spec_sha, texts, records = run_pipeline(VECTORS_DIR)

    print(f"Seam scaffolding generation report ({constants.STATUS})")
    print("  grammar_doc_sha256:", grammar_sha)
    print("  spec_sha256:       ", spec_sha)
    for filename, text in sorted(texts.items()):
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        rid = [r for r, f in verify.ARTIFACTS.items() if f == filename][0]
        pins = sorted(records[rid]["manifest_stub"]["pin_hashes"]) or ["none"]
        print(f"  {filename:<20} sha256 {digest[:16]}…  pins: {', '.join(pins)}")
    print("ALL GREEN: doc gate (both pins), self-tests, transcription "
          "cross-check, oracle replay, determinism, emit.")


if __name__ == "__main__":
    main()
