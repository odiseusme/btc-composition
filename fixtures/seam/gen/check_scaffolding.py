"""check_scaffolding.py — the task 0.3 verify line, in one command.

    python3 fixtures/seam/gen/check_scaffolding.py

Exit 0 only if EVERY check passes. One PASS/FAIL line per check:

  (a) every module imports cleanly
  (b) generate then verify round-trips both scaffolding artifacts
  (c) byte level: no emitted file contains a CR byte
  (d) the transcription cross-check is green
  (e) forbidden-import check, by AST: the oracle imports nothing from the
      adapters or the generator; the adapters import nothing from the oracle;
      and no adapter calls another stage's adapter
  (f) grep: every banned identifier is absent from fixtures/seam/gen/
  (g) adapter externality: each stage's input is constructed from serialized
      data in this test and yields the same output

Checks (e), (f), and (g) are the ownership-neutrality checks (risk R2). They
are the reason this file exists as a command rather than a habit: "the oracle
is independent" and "no stage reaches into another" are claims, and claims
that nothing tests are claims that quietly stop being true. They are checked
mechanically, on the source, at every run.
"""

import ast
import contextlib
import io
import json
import sys
import traceback
from pathlib import Path

GEN_DIR = Path(__file__).resolve().parent
SEAM_DIR = GEN_DIR.parent
VECTORS_DIR = SEAM_DIR / "vectors"
REPO_ROOT = SEAM_DIR.parents[1]

MODULES = ("constants", "adapters", "generate", "verify")

# BANNED IDENTIFIERS (task 0.3). Each presumes the pending 14.5 split — that
# some named side of the seam derives box ids, turns payloads into txids,
# assembles deals — and none of that has been decided. This tuple is the
# canonical list; no other file in the lane spells these names out.
#
# They are assembled from fragments ON PURPOSE. The property under test is that
# a plain recursive grep for any banned name over fixtures/seam/gen/ finds
# nothing — so the file that searches for them must not contain them either, or
# it becomes its own only hit. Matching is by substring, lowercased, which is
# what makes the second entry cover the whole prefixed family. "".join() is a
# runtime call, so the compiler's literal folding never materializes a whole
# banned name, in the source or in any byte-compiled form of it.
BANNED_IDENTIFIERS = (
    "".join(("derive_", "box", "_id")),
    "".join(("box", "_id_", "from_")),      # covers the whole prefixed family
    "".join(("txid_", "from_", "payload")),
    "".join(("payload_", "from_", "box")),
    "".join(("assemble_", "deal")),
    "".join(("build_", "deal_", "payload")),
    "".join(("deal_", "pipeline")),
)

# The four neutral stages. Sourced here as literals, not imported from
# adapters.py: this file is checking that module, not agreeing with it.
STAGE_NAMES = ("tx_set", "proof", "header_template", "packaging")
ADAPTER_FUNCS = {f"{stage}_adapter": stage for stage in STAGE_NAMES}

_results = []


def _record(ok, label, detail=""):
    _results.append(ok)
    status = "PASS" if ok else "FAIL"
    line = f"{status}  {label}"
    if detail:
        line += f"\n        {detail}"
    print(line)
    return ok


def _source_files():
    """Every source file under fixtures/seam/gen/ (never byte-compiled output)."""
    return sorted(
        p for p in GEN_DIR.rglob("*")
        if p.is_file() and "__pycache__" not in p.parts
    )


# --- (a) imports ------------------------------------------------------------

def check_imports():
    try:
        for name in MODULES:
            __import__(name)
    except Exception:
        return _record(False, "(a) modules import cleanly",
                       traceback.format_exc(limit=2).strip().splitlines()[-1])
    return _record(True, f"(a) modules import cleanly: {', '.join(MODULES)}")


# --- (b) generate -> verify round-trip --------------------------------------

def check_round_trip():
    import generate
    import verify

    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            generate.main()
    except SystemExit as exc:
        return _record(False, "(b) generate then verify round-trips both artifacts",
                       f"generate aborted (exit {exc.code}); see stderr")
    except Exception:
        return _record(False, "(b) generate then verify round-trips both artifacts",
                       traceback.format_exc(limit=2).strip().splitlines()[-1])

    try:
        results = verify.verify_artifacts(VECTORS_DIR)
    except verify.OracleError as exc:
        return _record(False, "(b) generate then verify round-trips both artifacts", str(exc))

    ids = sorted(r["record_id"] for r in results)
    if ids != sorted(verify.ARTIFACTS):
        return _record(False, "(b) generate then verify round-trips both artifacts",
                       f"verified {ids}, expected {sorted(verify.ARTIFACTS)}")
    return _record(True, f"(b) generate then verify round-trips both artifacts: {', '.join(ids)}")


# --- (c) LF-only, at the byte level -----------------------------------------

def check_lf_only():
    files = sorted(p for p in VECTORS_DIR.glob("*") if p.is_file()) if VECTORS_DIR.exists() else []
    if not files:
        return _record(False, "(c) no emitted file contains a CR byte", "no artifacts found")
    offenders = [p.name for p in files if b"\r" in p.read_bytes()]
    if offenders:
        return _record(False, "(c) no emitted file contains a CR byte",
                       f"CR bytes in {', '.join(offenders)}")
    total = sum(p.stat().st_size for p in files)
    return _record(True, f"(c) no emitted file contains a CR byte: {len(files)} files, {total} bytes")


# --- (d) transcription cross-check ------------------------------------------

def check_cross_transcription():
    import generate
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            generate.cross_check_transcriptions()
    except SystemExit as exc:
        return _record(False, "(d) transcription cross-check green",
                       f"cross-check aborted (exit {exc.code}); see stderr")
    return _record(True, "(d) transcription cross-check green: magic, supply bound, "
                         "gate pins, ledger agreement")


# --- (e) forbidden imports and cross-stage calls, by AST --------------------

def _imported_modules(tree):
    """Every module name a file imports, top-level package first component."""
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                names.add(node.module.split(".")[0])
    return names


def _cross_stage_calls(tree):
    """Adapter functions that call another stage's adapter. Must be empty."""
    offenders = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef) or node.name not in ADAPTER_FUNCS:
            continue
        for inner in ast.walk(node):
            if not isinstance(inner, ast.Call):
                continue
            func = inner.func
            called = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
            if called in ADAPTER_FUNCS and called != node.name:
                offenders.append(f"{node.name} calls {called}")
    return offenders


def check_forbidden_imports():
    verify_tree = ast.parse((GEN_DIR / "verify.py").read_text(encoding="utf-8"))
    adapters_src = (GEN_DIR / "adapters.py").read_text(encoding="utf-8")
    adapters_tree = ast.parse(adapters_src)

    problems = []

    leaked = _imported_modules(verify_tree) & {"adapters", "generate"}
    if leaked:
        problems.append(
            f"verify.py imports {sorted(leaked)}: the oracle would be re-running "
            "the generator, not checking it"
        )

    # The oracle's whitelist from constants.py: bookkeeping only. Anything else
    # is a value it is supposed to be transcribing itself.
    allowed = {"STATUS", "EXPECTED_GRAMMAR_SHA256", "EXPECTED_SPEC_SHA256"}
    for node in ast.walk(verify_tree):
        if isinstance(node, ast.ImportFrom) and node.module == "constants":
            pulled = {alias.name for alias in node.names}
            extra = pulled - allowed
            if extra:
                problems.append(
                    f"verify.py imports {sorted(extra)} from constants.py; the "
                    f"bookkeeping whitelist is {sorted(allowed)}"
                )

    leaked = _imported_modules(adapters_tree) & {"verify", "generate", "constants"}
    if leaked:
        problems.append(
            f"adapters.py imports {sorted(leaked)}: an adapter that reached the "
            "oracle or the generator would not be a replaceable boundary"
        )

    crossed = _cross_stage_calls(adapters_tree)
    if crossed:
        problems.append(
            "cross-stage calls in adapters.py (" + "; ".join(crossed) + "): stages "
            "communicate only through serialized data the caller passes"
        )

    if problems:
        return _record(False, "(e) forbidden-import / cross-stage-call check (AST)",
                       "\n        ".join(problems))
    return _record(True, "(e) forbidden-import / cross-stage-call check (AST): oracle "
                         "independent, adapters isolated")


# --- (f) banned identifiers --------------------------------------------------

def check_banned_identifiers():
    hits = []
    for path in _source_files():
        try:
            text = path.read_text(encoding="utf-8").lower()
        except UnicodeDecodeError:
            continue
        for banned in BANNED_IDENTIFIERS:
            if banned in text:
                for lineno, line in enumerate(text.splitlines(), 1):
                    if banned in line:
                        hits.append(f"{path.relative_to(REPO_ROOT)}:{lineno}: {banned}")
    if hits:
        return _record(False, "(f) banned identifiers absent from fixtures/seam/gen/",
                       "\n        ".join(hits))
    return _record(True, f"(f) banned identifiers absent from fixtures/seam/gen/: "
                         f"{len(BANNED_IDENTIFIERS)} names, {len(_source_files())} files")


# --- (g) adapter externality -------------------------------------------------

def _json_round_trip(value):
    """The proof that a value really is serialized data: it survives JSON."""
    return json.loads(json.dumps(value))


def check_adapter_externality():
    """Each stage's input is built from serialized data HERE, in this test.

    Nothing below is imported from the generator: no constant, no helper, no
    intermediate object. Every input is a literal or is read back out of an
    emitted artifact. If a stage could only be driven by the generator's own
    in-memory objects, this test could not exist — which is exactly what makes
    it the boundary's proof.
    """
    import adapters

    problems = []

    # 1. Literal inputs, one per stage. If these drive the adapters, then so
    #    can a file, a fixture, or the other side of the seam post-14.5.
    external_inputs = {
        "tx_set": {"segments": ["dead", "beef", ""]},
        "proof": {"elements": ["11" * 32, "22" * 32], "flags_hex": "03"},
        "header_template": {
            "template_hex": "0102030405060708",
            "slots": [{"name": "window", "offset": 2, "length": 3}],
        },
        "packaging": {
            "record_id": "externality",
            "kind": "externality-probe",
            "status": "PRE-FREEZE",
            "stages": [{"stage": "proof", "serialized": {"element_count": 0}}],
            "declarations": {},
            "manifest_stub": {"depends_on": [], "pin_hashes": {}},
            "notes": "input built entirely from serialized data in the test",
        },
    }
    if sorted(external_inputs) != sorted(STAGE_NAMES):
        problems.append("the externality test does not cover every stage")

    outputs = {}
    for stage in STAGE_NAMES:
        adapter = getattr(adapters, f"{stage}_adapter")
        supplied = external_inputs[stage]
        try:
            direct = adapter(supplied)
            # The same input, after a round trip through JSON: byte-for-byte the
            # form it would arrive in from outside this process.
            from_serialized = adapter(_json_round_trip(supplied))
        except Exception as exc:
            problems.append(f"{stage}: externally supplied input rejected ({exc})")
            continue
        if direct != from_serialized:
            problems.append(f"{stage}: output differs when the input arrives as JSON")
        if _json_round_trip(direct) != direct:
            problems.append(f"{stage}: output is not serialized data")
        if direct.get("stage") != stage:
            problems.append(f"{stage}: envelope is tagged {direct.get('stage')!r}")
        outputs[stage] = direct

    # 2. The strong form: rebuild the EMITTED artifacts' stages from nothing but
    #    the serialized data in the artifacts themselves. This is the externality
    #    claim applied to real output — a stage's input can be supplied from a
    #    file, with no generator in the room.
    try:
        probe = json.loads((VECTORS_DIR / "probe-magic.json").read_text(encoding="utf-8"))
        control = json.loads((VECTORS_DIR / "control-plain.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        problems.append(f"could not read the emitted artifacts ({exc})")
        probe = control = None

    if probe is not None:
        try:
            emitted = [s for s in probe["stages"] if s["stage"] == "tx_set"][0]
            blob = emitted["serialized"]["bytes_hex"]
            offset = probe["declarations"]["magic_offset"] * 2   # hex chars per byte
            magic_len = 4 * 2
            segments = [blob[:offset], blob[offset:offset + magic_len], blob[offset + magic_len:]]
            rebuilt = adapters.tx_set_adapter({"segments": segments})
            if rebuilt != emitted:
                problems.append("probe: tx_set stage not reproducible from the artifact's own bytes")
        except Exception as exc:
            problems.append(f"probe: tx_set stage could not be rebuilt from the artifact ({exc})")

    if control is not None:
        try:
            emitted = [s for s in control["stages"] if s["stage"] == "header_template"][0]
            rebuilt = adapters.header_template_adapter({
                "template_hex": emitted["serialized"]["bytes_hex"],
                "slots": [
                    {"name": s["name"], "offset": s["offset"], "length": s["length"]}
                    for s in emitted["serialized"]["slots"]
                ],
            })
            if rebuilt != emitted:
                problems.append("control: header_template stage not reproducible from the artifact")
        except Exception as exc:
            problems.append(f"control: header_template stage could not be rebuilt ({exc})")

    if problems:
        return _record(False, "(g) adapter externality: every stage driven from serialized data",
                       "\n        ".join(problems))
    return _record(True, "(g) adapter externality: every stage driven from serialized data "
                         f"({', '.join(STAGE_NAMES)}); emitted stages rebuilt from their own bytes")


CHECKS = (
    ("a", check_imports),
    ("b", check_round_trip),
    ("c", check_lf_only),
    ("d", check_cross_transcription),
    ("e", check_forbidden_imports),
    ("f", check_banned_identifiers),
    ("g", check_adapter_externality),
)


def main():
    print(f"Task 0.3 scaffolding check — {GEN_DIR.relative_to(REPO_ROOT)}")
    print()

    # Every check is run, and a check that RAISES is a check that FAILED: a
    # defect in the code under test must produce its own FAIL line, never a
    # traceback that swallows the checks after it.
    for cid, check in CHECKS:
        try:
            check()
        except Exception:
            last = traceback.format_exc().strip().splitlines()[-1]
            _record(False, f"({cid}) check raised before reporting", last)

    print()
    passed = sum(1 for ok in _results if ok)
    total = len(_results)
    if passed == total:
        print(f"ALL GREEN: {passed}/{total} checks passed.")
        return 0
    print(f"FAILED: {passed}/{total} checks passed.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
