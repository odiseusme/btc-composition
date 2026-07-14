"""check_scaffolding.py — the task 0.3 verify line, in one command.

    python3 fixtures/seam/gen/check_scaffolding.py

Exit 0 only if EVERY check passes. One PASS/FAIL line per check:

  (a) every module imports cleanly
  (b) the COMMITTED vectors are what this generator produces, and the oracle
      accepts them: hash the committed files, rebuild the whole pipeline into a
      temporary directory, byte-compare, then verify the committed bytes
  (c) byte level: no COMMITTED file contains a CR byte
  (d) the transcription cross-check is green
  (e) forbidden-import check, by AST: the oracle imports nothing from the
      adapters or the generator and reaches the constants module through one
      whitelisted import and no other path; the adapters import nothing from
      the oracle; and no function anywhere under gen/ composes stages unless it
      is on the composition allowlist
  (f) banned identifiers: the raw text, and every identifier in every file,
      normalized
  (g) adapter externality: each stage's input is constructed from serialized
      data in this test and yields the same output
  (h) the working tree is bit-identical to how this run found it

WHAT THIS SCRIPT MUST NEVER DO IS WRITE TO vectors/. Acceptance that regenerates
in place attests the bytes it has just written: a committed vector that no
longer matches its generator would pass forever, and the one claim the seam
package rests on — these committed bytes are these sources' output — would be
the one claim nothing checks. So the committed files are read and hashed FIRST,
the pipeline is rebuilt into a temporary directory, and the two are compared.
Check (h) proves the tree came out as it went in.

Checks (e), (f), and (g) are the ownership-neutrality checks (risk R2). They
are the reason this file exists as a command rather than a habit: "the oracle
is independent" and "no stage reaches into another" are claims, and claims
that nothing tests are claims that quietly stop being true. They are checked
mechanically, on the source, at every run.
"""

import ast
import contextlib
import hashlib
import io
import json
import shutil
import sys
import tempfile
import traceback
from pathlib import Path

GEN_DIR = Path(__file__).resolve().parent
SEAM_DIR = GEN_DIR.parent
VECTORS_DIR = SEAM_DIR / "vectors"
REPO_ROOT = SEAM_DIR.parents[1]

# BYTECODE HYGIENE, BEFORE THE FIRST LANE IMPORT. A stale .pyc survives an edit
# that changes neither a file's size nor its mtime — flipping the payload magic
# (task 0.6) is exactly such an edit — and CPython would then check the sources
# of record against a cached compile of their previous selves. PYTHONDONTWRITEBYTECODE
# (and -B) only stop CPython WRITING a .pyc; a cache that is already on disk is
# still LOADED. So the caches are deleted, not merely left unwritten.
sys.dont_write_bytecode = True
for _cache in sorted(GEN_DIR.rglob("__pycache__")):
    shutil.rmtree(_cache, ignore_errors=True)

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

# BANNED STEMS (the AST layer of check (f)). The list above is matched against
# the raw text, exactly as a reviewer's grep would be — and a grep is defeated by
# spelling. These stems are matched against every IDENTIFIER instead, normalized
# to lowercase with underscores stripped, and a stem CONTAINED in a longer name
# still hits. So the family is closed under spelling: the camelCase form, the
# SHOUTING form, and a stem buried inside a longer name all land on the same
# stem, and no future contributor has to have read the list to be stopped by it.
#
# Fragment-assembled for the same reason as the list above. Prose is exempt by
# construction: nothing but identifiers is ever tested against these, which is
# what lets the comments in this lane say plainly what is banned without any of
# them becoming the violation.
BANNED_STEMS = (
    "".join(("box", "id")),
    "".join(("deal", "payload")),
    "".join(("assemble", "deal")),
    "".join(("deal", "pipeline")),
    "".join(("txid", "from", "payload")),
    "".join(("payload", "from", "box")),
    "".join(("payload", "to", "txid")),
    "".join(("make", "deal")),
)

# The four neutral stages. Sourced here as literals, not imported from
# adapters.py: this file is checking that module, not agreeing with it.
STAGE_NAMES = ("tx_set", "proof", "header_template", "packaging")
ADAPTER_FUNCS = {f"{stage}_adapter": stage for stage in STAGE_NAMES}

# The oracle's bookkeeping whitelist: the ONLY names verify.py may take from
# constants.py, and it must take them in one import and reach that module by no
# other path. Everything else it checks, it transcribes itself — and a value the
# oracle imported instead of transcribing turns the cross-check into a
# comparison of a value with itself.
ORACLE_CONSTANTS_WHITELIST = frozenset({
    "STATUS", "EXPECTED_GRAMMAR_SHA256", "EXPECTED_SPEC_SHA256",
})

# THE COMPOSITION ALLOWLIST (risk R2). A function that calls two or more DISTINCT
# stage adapters is composing stages — that is orchestration, and construction
# ORDER for identity-bearing vectors (the box id / payload / txid / proof chain)
# is exactly what decision 14.5 gates. The entries below are the only places in
# the lane allowed to compose; each builds one artifact or drives the boundary
# from literals, and none of them chains identity-bearing steps.
#
# TASK 5a.2 OWNS ADDITIONS TO THIS LIST. Until the 14.5 split is recorded, a new
# file or a new function that composes stages FAILS this check, wherever under
# gen/ it is written. That failure is the control working, not an obstacle to be
# routed around by adding a name here.
COMPOSITION_ALLOWLIST = frozenset({
    "generate.build_probe",             # the probe: tx_set into packaging
    "generate.build_control",           # the control: header_template into packaging
    "generate.build_artifacts",         # the inventory, built from the two above
    "check_scaffolding.check_adapter_externality",   # check (g), the boundary's own proof
    # adapters.self_test drives each boundary from literals in the module — the
    # same job check (g) does one file over — and no adapter can reach it. See
    # ADAPTERS_COMPOSITION_EXEMPT.
    "adapters.self_test",
})

# Inside adapters.py the rule is stricter than the allowlist: an ADAPTER that
# called another stage's adapter would make the boundary itself an orchestrator,
# and no entry in the list above may excuse that. The module's own self-test is
# the single exemption — it is a test, not a boundary, nothing in the module
# calls it, and it still has to be named in COMPOSITION_ALLOWLIST like any other
# composer.
ADAPTERS_COMPOSITION_EXEMPT = frozenset({"self_test"})


def _vector_hashes():
    """sha256 of every file under vectors/, by name."""
    if not VECTORS_DIR.exists():
        return {}
    return {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(VECTORS_DIR.glob("*")) if path.is_file()
    }


# Captured before any check runs: the COMMITTED bytes, as this run found them.
# Every artifact check below reads these files, and check (h) proves they are
# still exactly these files afterwards.
COMMITTED_HASHES = _vector_hashes()

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


def _python_files():
    return [p for p in _source_files() if p.suffix == ".py"]


# --- (a) imports ------------------------------------------------------------

def check_imports():
    try:
        for name in MODULES:
            __import__(name)
    except Exception:
        return _record(False, "(a) modules import cleanly",
                       traceback.format_exc(limit=2).strip().splitlines()[-1])
    return _record(True, f"(a) modules import cleanly: {', '.join(MODULES)}")


# --- (b) the committed vectors, rebuilt and verified ------------------------

def check_round_trip():
    """The committed bytes are the thing under test, and are never written to.

    Read and hash them first; rebuild the entire pipeline into a temporary
    directory; byte-compare. A difference means the committed vectors are not
    this generator's output any more, and that is a FAILURE, not something to
    fix by overwriting them — which is precisely what regenerating in place
    would do, silently, before any check could look.
    """
    label = "(b) committed vectors rebuild byte-for-byte, and the oracle accepts them"
    import generate
    import verify

    committed = {}
    for filename in sorted(verify.ARTIFACTS.values()):
        path = VECTORS_DIR / filename
        if not path.is_file():
            return _record(False, label, f"committed artifact missing: {filename}")
        committed[filename] = path.read_bytes()

    buf = io.StringIO()
    with tempfile.TemporaryDirectory() as scratch:
        out_dir = Path(scratch)
        try:
            with contextlib.redirect_stdout(buf):
                generate.run_pipeline(out_dir)
        except SystemExit as exc:
            return _record(False, label, f"generate aborted (exit {exc.code}); see stderr")
        except Exception:
            return _record(False, label,
                           traceback.format_exc(limit=2).strip().splitlines()[-1])
        rebuilt = {p.name: p.read_bytes() for p in sorted(out_dir.glob("*")) if p.is_file()}

    if sorted(rebuilt) != sorted(committed):
        return _record(False, label,
                       f"the pipeline emits {sorted(rebuilt)}; the tree holds {sorted(committed)}")

    differing = [name for name in sorted(committed) if rebuilt[name] != committed[name]]
    if differing:
        detail = "; ".join(
            f"{name}: committed {hashlib.sha256(committed[name]).hexdigest()[:16]}… != "
            f"rebuilt {hashlib.sha256(rebuilt[name]).hexdigest()[:16]}…"
            for name in differing
        )
        return _record(False, label,
                       "the committed vectors are NOT what this generator produces — "
                       + detail)

    try:
        results = verify.verify_artifacts(VECTORS_DIR)
    except verify.OracleError as exc:
        return _record(False, label, f"the oracle rejected the COMMITTED bytes: {exc}")

    ids = sorted(r["record_id"] for r in results)
    if ids != sorted(verify.ARTIFACTS):
        return _record(False, label, f"verified {ids}, expected {sorted(verify.ARTIFACTS)}")
    return _record(True, f"{label}: {', '.join(sorted(committed))}")


# --- (c) LF-only, at the byte level -----------------------------------------

def check_lf_only():
    files = sorted(p for p in VECTORS_DIR.glob("*") if p.is_file()) if VECTORS_DIR.exists() else []
    if not files:
        return _record(False, "(c) no committed file contains a CR byte", "no artifacts found")
    offenders = [p.name for p in files if b"\r" in p.read_bytes()]
    if offenders:
        return _record(False, "(c) no committed file contains a CR byte",
                       f"CR bytes in {', '.join(offenders)}")
    total = sum(p.stat().st_size for p in files)
    return _record(True, f"(c) no committed file contains a CR byte: {len(files)} files, {total} bytes")


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


# --- (e) forbidden imports, oracle independence, stage composition (AST) ----

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


def _oracle_constants_problems(tree):
    """verify.py reaches constants.py through ONE whitelisted import, or not at all.

    The oracle's independence is not "it mostly transcribes its own literals". It
    is: there is exactly one import, it binds exactly three bookkeeping names, and
    no other expression in the file can reach that module. A single
    `import constants` would hand it every value in there, and a value the oracle
    imported instead of transcribing makes generate.cross_check_transcriptions()
    compare a value with itself and call it agreement.
    """
    problems = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] == "constants":
                    problems.append(
                        f"verify.py does `import constants` (line {node.lineno}): the "
                        "whitelist binds three names, and the module object binds all of them"
                    )

    froms = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module == "constants"
    ]
    if len(froms) != 1:
        problems.append(
            f"verify.py has {len(froms)} `from constants import ...` statements; there is "
            "exactly one, so that one place states everything the oracle shares"
        )

    for node in froms:
        pulled = {alias.name for alias in node.names}
        if pulled != ORACLE_CONSTANTS_WHITELIST:
            detail = []
            extra = sorted(pulled - ORACLE_CONSTANTS_WHITELIST)
            missing = sorted(ORACLE_CONSTANTS_WHITELIST - pulled)
            if extra:
                detail.append(f"imports {extra}")
            if missing:
                detail.append(f"does not import {missing}")
            problems.append(
                "verify.py " + " and ".join(detail) + " from constants.py; the bookkeeping "
                f"whitelist is exactly {sorted(ORACLE_CONSTANTS_WHITELIST)} — anything else "
                "is a value the oracle is supposed to be transcribing itself"
            )
        aliased = sorted(alias.asname for alias in node.names if alias.asname)
        if aliased:
            problems.append(
                f"verify.py aliases its constants imports ({aliased}); the whitelisted names "
                "are imported under their own names, so the whitelist can be read off the line"
            )

    # Not one expression may name the module. This single rule covers attribute
    # access (constants.SUPPLY_BOUND_SATS), rebinding it (c = constants), and any
    # assignment whose right-hand side reads through either.
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id == "constants":
            problems.append(
                f"verify.py names the constants module in an expression (line {node.lineno}); "
                "it reaches that module through the whitelisted import and no other path"
            )

    return problems


def _stage_adapter_calls(node):
    """The distinct stage adapters called anywhere inside an AST node."""
    called = set()
    for inner in ast.walk(node):
        if not isinstance(inner, ast.Call):
            continue
        func = inner.func
        name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
        if name in ADAPTER_FUNCS:
            called.add(name)
    return called


def _composition_problems():
    """Who composes stages, across EVERY .py under gen/, and are they allowed to.

    Scanning only adapters.py's four adapters would have proved that the four
    functions we already trust do not compose. The rule is about the lane, not
    about four functions: a new file, a new helper, a self-test that quietly
    chains stages, all have to fail this, or the ban is a convention again.
    """
    problems = []

    for path in sorted(GEN_DIR.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        module = path.stem
        tree = ast.parse(path.read_text(encoding="utf-8"))

        scopes = [
            (f"{module}.{node.name}", node.name, node)
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        ]

        # Module-level code composes too, and a function-only scan would sail
        # straight past it. Everything outside a def is attributed to <module>,
        # which is on no allowlist and never will be.
        scopes.append((f"{module}.<module>", "<module>", ast.Module(
            body=[
                node for node in tree.body
                if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
            ],
            type_ignores=[],
        )))

        for qualified, local, node in scopes:
            called = _stage_adapter_calls(node)
            if not called:
                continue

            if module == "adapters" and local not in ADAPTERS_COMPOSITION_EXEMPT:
                others = sorted(called - {local})
                if others:
                    problems.append(
                        f"adapters.py: {local}() calls {', '.join(others)} — no function in "
                        "the boundary module may call a stage adapter; stages communicate "
                        "only through serialized data the CALLER passes"
                    )
                    continue

            if len(called) >= 2 and qualified not in COMPOSITION_ALLOWLIST:
                problems.append(
                    f"{qualified}() composes stages ({', '.join(sorted(called))}) and is not "
                    "on the composition allowlist; identity-bearing construction order is "
                    "gated by decision 14.5, and task 5a.2 owns additions to that list"
                )

    return problems


def check_forbidden_imports():
    verify_tree = ast.parse((GEN_DIR / "verify.py").read_text(encoding="utf-8"))
    adapters_tree = ast.parse((GEN_DIR / "adapters.py").read_text(encoding="utf-8"))

    problems = []

    leaked = _imported_modules(verify_tree) & {"adapters", "generate"}
    if leaked:
        problems.append(
            f"verify.py imports {sorted(leaked)}: the oracle would be re-running "
            "the generator, not checking it"
        )

    problems.extend(_oracle_constants_problems(verify_tree))

    leaked = _imported_modules(adapters_tree) & {"verify", "generate", "constants"}
    if leaked:
        problems.append(
            f"adapters.py imports {sorted(leaked)}: an adapter that reached the "
            "oracle or the generator would not be a replaceable boundary"
        )

    problems.extend(_composition_problems())

    if problems:
        return _record(False, "(e) forbidden-import / oracle-independence / composition (AST)",
                       "\n        ".join(problems))
    scanned = len([p for p in _python_files()])
    return _record(True, "(e) forbidden-import / oracle-independence / composition (AST): "
                         f"oracle independent, adapters isolated, {scanned} files scanned for "
                         f"stage composition, {len(COMPOSITION_ALLOWLIST)} composers allowlisted")


# --- (f) banned identifiers --------------------------------------------------

def _identifiers(tree):
    """Every identifier a file binds or reads: defs, names, attributes, arguments."""
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
        elif isinstance(node, ast.arg):
            names.add(node.arg)
        elif isinstance(node, ast.keyword) and node.arg:
            names.add(node.arg)
        elif isinstance(node, ast.alias):
            names.add(node.name.split(".")[0])
            if node.asname:
                names.add(node.asname)
        elif isinstance(node, ast.ExceptHandler) and node.name:
            names.add(node.name)
        elif isinstance(node, (ast.Global, ast.Nonlocal)):
            names.update(node.names)
    return names


def _normalized(identifier):
    """lowercase, underscores stripped: one spelling for a family of spellings."""
    return identifier.replace("_", "").lower()


def check_banned_identifiers():
    hits = []

    # Layer 1: the raw text, exactly as a reviewer's grep would read it.
    for path in _source_files():
        try:
            text = path.read_text(encoding="utf-8").lower()
        except UnicodeDecodeError:
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            for banned in BANNED_IDENTIFIERS:
                if banned in line:
                    hits.append(f"{path.relative_to(REPO_ROOT)}:{lineno}: text {banned!r}")

    # Layer 2: the AST. A grep for exact names is beaten by spelling — a
    # camelCase form, a stem buried inside a longer name — and the ban is on the
    # CONCEPT, not on seven strings. So every identifier is normalized and
    # tested for a banned stem as a substring. Prose is untouched by this loop
    # by construction: only identifiers reach it.
    for path in _python_files():
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError as exc:
            hits.append(f"{path.relative_to(REPO_ROOT)}: does not parse ({exc})")
            continue
        for identifier in sorted(_identifiers(tree)):
            flat = _normalized(identifier)
            for stem in BANNED_STEMS:
                if stem in flat:
                    hits.append(
                        f"{path.relative_to(REPO_ROOT)}: identifier {identifier!r} contains "
                        f"the banned stem {stem!r}"
                    )

    if hits:
        return _record(False, "(f) banned identifiers absent from fixtures/seam/gen/",
                       "\n        ".join(hits))
    return _record(True, "(f) banned identifiers absent from fixtures/seam/gen/: "
                         f"{len(BANNED_IDENTIFIERS)} names over {len(_source_files())} files, "
                         f"{len(BANNED_STEMS)} stems over every identifier in "
                         f"{len(_python_files())} modules")


# --- (g) adapter externality -------------------------------------------------

def _json_round_trip(value):
    """The proof that a value really is serialized data: it survives JSON."""
    return json.loads(json.dumps(value))


def check_adapter_externality():
    """Each stage's input is built from serialized data HERE, in this test.

    Nothing below is imported from the generator: no constant, no helper, no
    intermediate object. Every input is a literal or is read back out of a
    COMMITTED artifact. If a stage could only be driven by the generator's own
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

    # 2. The strong form: rebuild the COMMITTED artifacts' stages from nothing but
    #    the serialized data in the artifacts themselves. This is the externality
    #    claim applied to real output — a stage's input can be supplied from a
    #    file, with no generator in the room.
    try:
        probe = json.loads((VECTORS_DIR / "probe-magic.json").read_text(encoding="utf-8"))
        control = json.loads((VECTORS_DIR / "control-plain.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        problems.append(f"could not read the committed artifacts ({exc})")
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
                         f"({', '.join(STAGE_NAMES)}); committed stages rebuilt from their own bytes")


# --- (h) the working tree is as this run found it ---------------------------

def check_tree_untouched():
    """Acceptance observes; it does not write. This is the proof, not the promise.

    Every artifact check above ran against the committed bytes, and that is only
    worth anything if the committed bytes were never touched. Hashed before the
    first check, hashed again after the last: a rewritten file, a new file, a
    leftover .tmp from a half-finished emit all show up here.
    """
    label = "(h) working tree untouched: fixtures/seam/vectors byte-identical before and after"
    after = _vector_hashes()
    if after == COMMITTED_HASHES:
        return _record(True, f"{label} ({len(after)} files)")

    problems = []
    for name in sorted(set(COMMITTED_HASHES) | set(after)):
        before, now = COMMITTED_HASHES.get(name), after.get(name)
        if before == now:
            continue
        if before is None:
            problems.append(f"{name}: created by this check run")
        elif now is None:
            problems.append(f"{name}: removed by this check run")
        else:
            problems.append(f"{name}: rewritten ({before[:16]}… -> {now[:16]}…)")
    return _record(False, label, "\n        ".join(problems))


CHECKS = (
    ("a", check_imports),
    ("b", check_round_trip),
    ("c", check_lf_only),
    ("d", check_cross_transcription),
    ("e", check_forbidden_imports),
    ("f", check_banned_identifiers),
    ("g", check_adapter_externality),
    ("h", check_tree_untouched),
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
