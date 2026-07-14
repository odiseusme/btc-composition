"""self_test_defect.py — the oracle seeded-defect self-test (task 0.4).

    python3 fixtures/seam/gen/self_test_defect.py

Exit 0 only if the oracle CATCHES a defect deliberately seeded into a
temporary run's generator output. The one thing this script must never be
is a test that can only pass: if the oracle stays green on the corrupted
set, this script exits 1, loudly, because an oracle that misses a seeded
defect is an oracle whose green means nothing.

Structure (each phase aborts loudly on failure):

  1. BYTECODE HYGIENE: purge __pycache__ before the first lane import.
     A stale .pyc survives edits that change neither size nor mtime, and a
     self-test that imports a cached compile of the oracle tests yesterday's
     oracle.
  2. TREE SNAPSHOT: hash every committed file under fixtures/seam/ (the
     selftest evidence directory excluded — it is this run's one permitted
     delta). Compared again at the end: the committed vectors are never
     touched, the defect lives only in temporary directories.
  3. BASELINE: run the full 0.3 pipeline into temp dir A and require the
     oracle green on it. Seeding a defect into an already-broken baseline
     proves nothing about detection.
  4. SEEDED RUN: B is a full copy of A, proven identical, then EXACTLY two
     characters of the probe's file text are edited — the hex pair of the
     first byte in the declared magic window, XOR 0x01 — and the
     single-decoded-byte property is proven against A before detection.
  5. DETECTION: the oracle over B MUST raise, and the rejection must name
     the probe, the declared offset, and the mutated window (derived from
     this script's own mutation, not the oracle's internals). A green
     oracle here, or an unrelated rejection, is THIS script's failure.
  6. EVIDENCE: the previous report is invalidated at run start; a new one
     is written only on the all-green path, atomically, through a
     symlink-guarded path, bound to the sha256 of this script, the oracle,
     the generator, and the initial tree snapshot.
  7. TREE CHECK: the recorded state of every file under fixtures/seam/
     (content hash, exec bit, symlink target; the one mutable report
     excluded) must be identical at the start and end of the phases, and
     again after evidence emission. This is honest damage detection at the
     endpoints, not a proof of non-access during the interval; the phases
     work in temporary directories by construction.

Semantics-free by construction (Shannon's sequencing rule): no new vector
content, no threat keys, no D5 keys, no SPEC section numbers. The only
SPEC dependence is the doc gate already inside run_pipeline(), inherited,
not added — this file survives the coming SPEC re-pin untouched.
"""

import hashlib
import json
import os
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

GEN_DIR = Path(__file__).resolve().parent
SEAM_DIR = GEN_DIR.parent
SELFTEST_DIR = GEN_DIR / "selftest"

# 1. BYTECODE HYGIENE, part one: settings that must precede ANY lane import.
# dont_write_bytecode stops WRITING caches; pycache_prefix = None stops
# READING bytecode from an external cache tree (PYTHONPYCACHEPREFIX /
# -X pycache_prefix), where a stale compile of the oracle could survive a
# purge that only looks under GEN_DIR. (Review finding 3.)
sys.dont_write_bytecode = True
sys.pycache_prefix = None

_LANE_MODULES = ("constants", "adapters", "generate", "verify")

# Bound by _import_lane_modules(), called from main() AFTER the initial tree
# snapshot: a top-level lane import that wrote to the committed tree would
# otherwise be baselined into the snapshot and pass unseen. (Finding 5.)
generate = None
verify = None


def _fail(msg):
    print(f"SELF-TEST FAIL: {msg}", file=sys.stderr)
    sys.exit(1)


def _purge_bytecode_caches():
    """Delete local caches STRICTLY: a purge that cannot prove it purged is
    an assurance. No ignore_errors — a permission failure is a failure —
    and the directory is re-scanned afterwards to prove nothing remains.
    """
    for cache in sorted(GEN_DIR.rglob("__pycache__")):
        shutil.rmtree(cache)
    leftover = sorted(GEN_DIR.rglob("__pycache__")) + sorted(GEN_DIR.rglob("*.pyc"))
    if leftover:
        _fail(f"bytecode caches survived the purge: {[str(p) for p in leftover]}")


def _import_lane_modules():
    """Import the lane fresh, provably from source.

    A module already sitting in sys.modules would be handed back by the
    import system as-is — no file read at all — so a pre-seeded oracle
    would bypass every hygiene measure above. Rejected before importing.
    """
    seeded = [m for m in _LANE_MODULES if m in sys.modules]
    if seeded:
        _fail(f"lane modules already imported before the self-test: {seeded}")
    global generate, verify
    import generate as _generate  # noqa: E402
    import verify as _verify      # noqa: E402
    generate, verify = _generate, _verify
    for mod in (generate, verify):
        origin = Path(mod.__file__).resolve()
        if origin.parent != GEN_DIR:
            _fail(f"{mod.__name__} imported from {origin}, not {GEN_DIR}")


def _call_phase(name, fn, *args):
    """Run an imported lane entry point; convert any SystemExit into a
    self-test failure. Today no lane function calls sys.exit(0), but a
    CLI-style refactor could, and SystemExit(0) propagating out of main()
    would end this process GREEN with no detection, no tree check, and no
    evidence. (Finding 1.) An exit attempt of ANY code, 0 included, is a
    contract violation here: phases return or raise, never exit.
    """
    try:
        return fn(*args)
    except SystemExit as exc:
        _fail(f"{name} attempted process exit with code {exc.code!r} "
              "instead of returning or raising")


def _utc_now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


_REPORT_REL = ("gen", "selftest", "selftest-report.json")


def snapshot_tree():
    """Record every file under fixtures/seam/: content hash, exec bit, and
    symlink target where applicable.

    What two snapshots PROVE is that the recorded state is identical at the
    two moments they were taken — honest damage detection, not a proof of
    non-access during the interval (review finding 4; the only actor in the
    interval is this process, and its phases work in temp dirs by
    construction).

    Excluded: EXACTLY the mutable evidence report (finding 6 — excluding
    the whole selftest directory would let any other file appear, change,
    or vanish there unseen), and bytecode caches (purged and verified gone
    before lane imports; excluded so a cache written by a different
    interpreter mid-run cannot masquerade as tree damage). Symlinks are
    recorded as their TARGET, not followed for content, so a tracked file
    silently replaced by a link to identical bytes still shows as a change;
    the exec bit is recorded because content hashing alone is blind to it.
    """
    entries = {}
    for path in sorted(SEAM_DIR.rglob("*")):
        if not (path.is_file() or path.is_symlink()):
            continue
        rel = path.relative_to(SEAM_DIR)
        if rel.parts == _REPORT_REL:
            continue
        if "__pycache__" in rel.parts:
            continue
        if path.is_symlink():
            entries[str(rel)] = f"symlink->{os.readlink(path)}"
        else:
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            exec_bit = bool(path.stat().st_mode & 0o111)
            entries[str(rel)] = f"file:{digest}:exec={exec_bit}"
    return entries


def baseline_run(out_dir):
    """Phase 3: full pipeline into out_dir; oracle green on it, or abort.

    run_pipeline() already replays the oracle in memory before emitting; the
    explicit verify_artifacts() call afterwards is not redundancy for its own
    sake — it establishes the baseline through the SAME entry point the
    seeded run will use, so the later red verdict and this green one are
    verdicts of one code path, not two.
    """
    _call_phase("generate.run_pipeline", generate.run_pipeline, out_dir)
    try:
        results = _call_phase("verify.verify_artifacts (baseline)",
                              verify.verify_artifacts, out_dir)
    except verify.OracleError as exc:
        _fail(f"baseline is not green ({exc}); nothing to seed a defect into")
    return {
        r["record_id"]: hashlib.sha256(
            (Path(out_dir) / verify.ARTIFACTS[r["record_id"]]).read_bytes()
        ).hexdigest()
        for r in results
    }


def _load_json_strict(path):
    """Parse an artifact as STANDARDS-valid JSON: Python's default parser
    accepts NaN/Infinity, which no JSON standard does, so an artifact
    carrying one would be Python-readable yet invalid JSON — quietly
    violating the valid-JSON half of the semantic-corruption guarantee.
    (Review finding 11.)
    """
    def _reject(const):
        raise ValueError(f"nonstandard JSON constant {const!r} in {path.name}")
    return json.loads(path.read_text(encoding="utf-8"), parse_constant=_reject)


def _inventory(root):
    """{relative path: sha256} for every file under root."""
    root = Path(root)
    return {
        str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(root.rglob("*")) if p.is_file()
    }


def seed_defect(run_dir):
    """Phase 4: corrupt ONE generator output, SURGICALLY.

    The mutation edits exactly TWO CHARACTERS of the emitted file: the hex
    pair encoding the first byte of the probe's declared magic window, XORed
    with 0x01. Nothing is reparsed-and-reserialized (review finding 10: a
    rewrite in this script's own formatting could differ from the
    generator's representation in many bytes, so 'one seeded byte' would be
    a lie and an unrelated formatting rejection could masquerade as
    detection). The file's every other byte is preserved, so it remains
    exactly as valid as the generator made it — the only thing wrong with
    it is the thing the oracle's semantic window check exists to catch.

    Deterministic on purpose: same window, same XOR, every run — evidence
    that names an exact mutation beats evidence that names a random one.
    Returns the mutation record for the detection check and the evidence.
    """
    probe_path = Path(run_dir) / verify.ARTIFACTS[verify.PROBE_ID]
    original_text = probe_path.read_text(encoding="utf-8")
    record = _load_json_strict(probe_path)

    hex_text = record["stages"][0]["serialized"]["bytes_hex"]
    offset = record["declarations"]["magic_offset"]

    # The pair arithmetic below assumes contiguous, unspaced hex. fromhex()
    # would tolerate whitespace; this surgery must not GUESS through it.
    if not (isinstance(hex_text, str) and len(hex_text) % 2 == 0
            and all(c in "0123456789abcdefABCDEF" for c in hex_text)):
        _fail("probe bytes_hex is not contiguous hex; surgical mutation "
              "cannot map a byte offset to a character pair — re-scope the "
              "mutation before trusting this self-test")
    if original_text.count(hex_text) != 1:
        _fail(f"probe bytes_hex value occurs "
              f"{original_text.count(hex_text)} times in the file text; "
              "surgical replacement requires exactly one")

    pair_start = offset * 2
    old_pair = hex_text[pair_start:pair_start + 2]
    new_byte = int(old_pair, 16) ^ 0x01
    new_pair = f"{new_byte:02X}" if old_pair.isupper() else f"{new_byte:02x}"
    mutated_hex = hex_text[:pair_start] + new_pair + hex_text[pair_start + 2:]

    probe_path.write_text(
        original_text.replace(hex_text, mutated_hex, 1),
        encoding="utf-8", newline="\n",
    )
    return {
        "file": probe_path.name,
        "stage_byte_offset": offset,
        "old_byte_hex": old_pair.lower(),
        "new_byte_hex": new_pair.lower(),
        "mutation": "XOR 0x01 on the first byte of the declared magic "
                    "window, via a two-character edit of the file text",
    }


def verify_mutation(dir_a, dir_b, mutation):
    """The mutation's own claims, proven before detection is attempted.

    (Review finding 10's assertion battery.) Everything the evidence will
    say about the seeded defect is checked here against the actual bytes:
    identical inventories, exactly one differing file, both probes parse as
    standards-valid JSON, equal declared lengths, equal decoded lengths,
    exactly ONE decoded byte differing, at the declared offset.
    """
    inv_a, inv_b = _inventory(dir_a), _inventory(dir_b)
    if set(inv_a) != set(inv_b):
        _fail(f"A and B inventories differ: {sorted(set(inv_a) ^ set(inv_b))}")
    differing = sorted(p for p in inv_a if inv_a[p] != inv_b[p])
    if differing != [mutation["file"]]:
        _fail(f"expected only {mutation['file']!r} to differ between A and "
              f"B; differing files: {differing}")

    rec_a = _load_json_strict(Path(dir_a) / mutation["file"])
    rec_b = _load_json_strict(Path(dir_b) / mutation["file"])
    ser_a = rec_a["stages"][0]["serialized"]
    ser_b = rec_b["stages"][0]["serialized"]
    if ser_a["length"] != ser_b["length"]:
        _fail("declared lengths diverged under a byte-preserving mutation")
    bytes_a = bytes.fromhex(ser_a["bytes_hex"])
    bytes_b = bytes.fromhex(ser_b["bytes_hex"])
    if len(bytes_a) != len(bytes_b):
        _fail("decoded lengths diverged under a byte-preserving mutation")
    diff_positions = [i for i, (x, y) in enumerate(zip(bytes_a, bytes_b)) if x != y]
    if diff_positions != [mutation["stage_byte_offset"]]:
        _fail(f"expected exactly one decoded byte to differ at offset "
              f"{mutation['stage_byte_offset']}; differing: {diff_positions}")
    return bytes_b


def require_detection(run_dir, mutation, mutated_bytes):
    """Phase 5: the oracle over the seeded set MUST raise — AND the
    rejection must be THE rejection.

    THE INVERTED-FAILURE PROPERTY LIVES HERE. An oracle that stays green on
    a corrupted probe makes THIS script exit 1. And an OracleError alone is
    not enough (review finding 2): an oracle whose semantic window check
    was removed could still reject B for some unrelated reason, and a
    self-test that accepts ANY rejection would launder that into 'the
    seeded defect was caught'. So the message must name what WE mutated —
    the probe, the declared offset, and the mutated window's actual hex,
    every expectation derived from this script's own mutation record and
    the post-mutation bytes, none from the oracle's internals.
    Returns the oracle's verbatim rejection for the evidence report.
    """
    offset = mutation["stage_byte_offset"]
    window_hex = mutated_bytes[offset:offset + verify._MAGIC_LEN].hex()
    expected_fragments = (
        verify.PROBE_ID,
        f"declared offset {offset}",
        window_hex,
    )
    try:
        _call_phase("verify.verify_artifacts (detection)",
                    verify.verify_artifacts, run_dir)
    except verify.OracleError as exc:
        rejection = str(exc)
        missing = [f for f in expected_fragments if f not in rejection]
        if missing:
            _fail(
                "the oracle rejected the seeded set, but NOT at the semantic "
                f"window check — the rejection does not name {missing}.\n"
                f"  rejection verbatim: {rejection}\n"
                "An unrelated rejection is not detection; the window check "
                "may be weakened or gone."
            )
        return rejection
    _fail(
        "the oracle stayed GREEN on the seeded defect — detection failed; "
        "the oracle's green cannot be trusted until this is resolved"
    )


def _guard_evidence_path():
    """Reject a symlink at ANY component of the evidence path (finding 8):
    a linked directory or report file would make write_text() land the
    evidence bytes somewhere else — possibly on a tracked file — after the
    tree check believed itself done. lstat semantics via is_symlink(), so
    the link itself is what is judged, not its target.
    """
    report = SELFTEST_DIR / "selftest-report.json"
    for component in (GEN_DIR, SELFTEST_DIR, report):
        if component.is_symlink():
            _fail(f"evidence path component {component} is a symlink; "
                  "refusing to write evidence through it")
    if report.exists() and not report.is_file():
        _fail(f"{report} exists and is not a regular file")


def _invalidate_prior_evidence():
    """Run-start invalidation (finding 7): a report from a PREVIOUS run
    says nothing about THIS tree or THIS source, and if this run dies
    partway, that stale green must not be what a reader finds. Deleted up
    front: a red run leaves NO evidence, visibly, and version control shows
    the deletion.
    """
    _guard_evidence_path()
    report = SELFTEST_DIR / "selftest-report.json"
    if report.exists():
        report.unlink()
        print("  evidence: prior report invalidated at run start "
              "(a red run leaves none)")


def main():
    started = _utc_now()
    print(f"Seam oracle seeded-defect self-test (task 0.4) — {started}")

    # 2. TREE SNAPSHOT — taken with stdlib only, BEFORE any lane module is
    # imported, so an import-time write to the committed tree cannot be
    # baselined into the reference it is later compared against.
    before = snapshot_tree()
    print(f"  tree snapshot: {len(before)} committed files hashed")

    # 1. BYTECODE HYGIENE, part two, then the guarded lane import.
    _purge_bytecode_caches()
    _import_lane_modules()
    print("  hygiene: caches purged and verified gone; lane imported fresh "
          "from source")
    _invalidate_prior_evidence()

    # 3. BASELINE.
    with tempfile.TemporaryDirectory(prefix="seam-selftest-a-") as tmp_a:
        baseline_hashes = baseline_run(tmp_a)
        print("  baseline: pipeline emitted into temp dir A; oracle GREEN")
        for rid, digest in sorted(baseline_hashes.items()):
            print(f"    {rid:<14} sha256 {digest[:16]}…")

        # 4. SEEDED RUN: B is a FULL copy of A (review finding 9: copying
        # only the files the oracle currently names would let a future
        # pipeline output vanish from B unnoticed, and its absence could
        # masquerade as detection). Copied, proven identical, THEN mutated,
        # then the mutation's own claims proven byte-by-byte.
        with tempfile.TemporaryDirectory(prefix="seam-selftest-b-") as tmp_b:
            shutil.copytree(tmp_a, tmp_b, dirs_exist_ok=True)
            if _inventory(tmp_a) != _inventory(tmp_b):
                _fail("B is not a byte-identical copy of A after copytree")
            mutation = seed_defect(tmp_b)
            mutated_bytes = verify_mutation(tmp_a, tmp_b, mutation)
            print(f"  seeded run: {mutation['mutation']} "
                  f"in {mutation['file']} at stage byte {mutation['stage_byte_offset']} "
                  f"({mutation['old_byte_hex']} -> {mutation['new_byte_hex']}); "
                  "single-byte property verified against A")

            # 5. DETECTION: green here is THIS script's failure, and only
            # the semantic window rejection counts.
            rejection = require_detection(tmp_b, mutation, mutated_bytes)
            print(f"  detection: oracle REJECTED the seeded set at the "
                  "expected check:")
            print(f"    {rejection}")

    # 7a. TREE CHECK, pre-evidence: phase damage must fail BEFORE any
    # green-looking evidence exists.
    after = snapshot_tree()
    if before != after:
        changed = sorted(
            set(before) ^ set(after)
            | {p for p in before.keys() & after.keys() if before[p] != after[p]}
        )
        _fail(f"committed tree changed during the run: {changed}")
    print(f"  tree check: {len(after)} recorded entries identical to the "
          "initial snapshot")

    # 6. EVIDENCE. Emitted only on the all-green path; the prior report was
    # already invalidated at run start, so a run that died before this line
    # left NO evidence rather than someone else's green (finding 7).
    # Symlink-guarded and atomic (finding 8), bound to the exact sources
    # and tree it attests so it cannot be mistaken for evidence about some
    # later state of either.
    _guard_evidence_path()
    SELFTEST_DIR.mkdir(parents=True, exist_ok=True)
    report_path = SELFTEST_DIR / "selftest-report.json"
    report = {
        "task": "0.4 oracle seeded-defect self-test",
        "started_utc": started,
        "completed_utc": _utc_now(),
        "command": "python3 fixtures/seam/gen/self_test_defect.py",
        "python_version": sys.version.split()[0],
        "bound_to_sha256": {
            "self_test_defect.py": hashlib.sha256(
                Path(__file__).read_bytes()).hexdigest(),
            "verify.py": hashlib.sha256(
                Path(verify.__file__).read_bytes()).hexdigest(),
            "generate.py": hashlib.sha256(
                Path(generate.__file__).read_bytes()).hexdigest(),
            "initial_tree_snapshot": hashlib.sha256(
                json.dumps(before, sort_keys=True).encode("utf-8")).hexdigest(),
        },
        "baseline": {
            "run": "full 0.3 pipeline into a temporary directory",
            "oracle_verdict": "GREEN",
            "artifact_sha256": baseline_hashes,
        },
        "seeded_defect": mutation,
        "detection": {
            "oracle_verdict": "REJECTED",
            "rejection_verbatim": rejection,
        },
        "tree_check": {
            "recorded_entries": len(after),
            "verdict": "recorded state identical at start and end of phases",
        },
        "phases_all_green": True,
    }
    tmp_path = report_path.with_name(report_path.name + ".tmp")
    with open(tmp_path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(report, indent=2, sort_keys=True,
                            allow_nan=False) + "\n")
    os.replace(tmp_path, report_path)
    print(f"  evidence: {report_path.relative_to(SEAM_DIR.parents[1])}")

    # 7b. TREE CHECK, post-evidence: the write itself must have touched
    # nothing but the one excluded report path. If it did, the report is
    # removed before failing — damaged-tree evidence is no evidence.
    final = snapshot_tree()
    if final != after:
        report_path.unlink(missing_ok=True)
        changed = sorted(
            set(after) ^ set(final)
            | {p for p in after.keys() & final.keys() if after[p] != final[p]}
        )
        _fail(f"evidence emission touched the committed tree: {changed}")

    print("SELF-TEST GREEN: baseline green, seeded defect CAUGHT by the "
          "oracle at the expected check, recorded tree state identical, "
          "evidence emitted and bound.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
