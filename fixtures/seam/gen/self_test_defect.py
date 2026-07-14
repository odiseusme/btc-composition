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
  4. SEEDED RUN: copy A to temp dir B, corrupt ONE generator output in B.
     (Phase not yet implemented — arrives in the next step.)
  5. DETECTION: the oracle over B MUST raise; a green oracle here is THIS
     script's failure. (Arrives with phase 4.)
  6. EVIDENCE: a report under fixtures/seam/gen/selftest/ carrying the
     commands, the baseline hashes, the exact mutation, the oracle's
     verbatim rejection, and the tree verdict.
  7. TREE UNTOUCHED: re-hash the snapshot set; byte-identical or fail.

Semantics-free by construction (Shannon's sequencing rule): no new vector
content, no threat keys, no D5 keys, no SPEC section numbers. The only
SPEC dependence is the doc gate already inside run_pipeline(), inherited,
not added — this file survives the coming SPEC re-pin untouched.
"""

import hashlib
import json
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

GEN_DIR = Path(__file__).resolve().parent
SEAM_DIR = GEN_DIR.parent
SELFTEST_DIR = GEN_DIR / "selftest"

# 1. BYTECODE HYGIENE, BEFORE THE FIRST LANE IMPORT (same discipline as
# check_scaffolding.py, for the same reason).
sys.dont_write_bytecode = True
for _cache in sorted(GEN_DIR.rglob("__pycache__")):
    shutil.rmtree(_cache, ignore_errors=True)

import generate  # noqa: E402  (hygiene must precede lane imports)
import verify    # noqa: E402


def _fail(msg):
    print(f"SELF-TEST FAIL: {msg}", file=sys.stderr)
    sys.exit(1)


def _utc_now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def snapshot_tree():
    """Hash every committed file under fixtures/seam/, sorted, by relative path.

    Excluded: this run's evidence directory (the one permitted delta) and any
    bytecode cache (deleted above; excluded anyway so a cache written by a
    different interpreter between phases cannot masquerade as tree damage).
    """
    hashes = {}
    for path in sorted(SEAM_DIR.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(SEAM_DIR)
        if rel.parts[:2] == ("gen", "selftest"):
            continue
        if "__pycache__" in rel.parts:
            continue
        hashes[str(rel)] = hashlib.sha256(path.read_bytes()).hexdigest()
    return hashes


def baseline_run(out_dir):
    """Phase 3: full pipeline into out_dir; oracle green on it, or abort.

    run_pipeline() already replays the oracle in memory before emitting; the
    explicit verify_artifacts() call afterwards is not redundancy for its own
    sake — it establishes the baseline through the SAME entry point the
    seeded run will use, so the later red verdict and this green one are
    verdicts of one code path, not two.
    """
    generate.run_pipeline(out_dir)
    try:
        results = verify.verify_artifacts(out_dir)
    except verify.OracleError as exc:
        _fail(f"baseline is not green ({exc}); nothing to seed a defect into")
    return {
        r["record_id"]: hashlib.sha256(
            (Path(out_dir) / verify.ARTIFACTS[r["record_id"]]).read_bytes()
        ).hexdigest()
        for r in results
    }


def seed_defect(run_dir):
    """Phase 4: corrupt ONE generator output in the temporary run.

    The mutation: XOR the first byte inside the probe's declared magic window
    with 0x01, in the decoded stage bytes, then re-encode and re-emit the
    record in the generator's own serialization (indent=2, sort_keys, LF).
    The file stays valid UTF-8 JSON with a correct declared length, so the
    only thing wrong with it is the thing the ORACLE's semantic check exists
    to catch: the bytes at the declared offset are not the magic. A mutation
    that broke the JSON instead would be caught by any parser anywhere, and
    a self-test passing on that would say nothing about the oracle.

    Deterministic on purpose: same window, same XOR, every run — evidence
    that names an exact mutation beats evidence that names a random one.
    Returns the mutation record for the evidence report.
    """
    probe_path = Path(run_dir) / verify.ARTIFACTS[verify.PROBE_ID]
    record = json.loads(probe_path.read_text(encoding="utf-8"))

    serialized = record["stages"][0]["serialized"]
    raw_bytes = bytearray(bytes.fromhex(serialized["bytes_hex"]))
    offset = record["declarations"]["magic_offset"]

    old_byte = raw_bytes[offset]
    raw_bytes[offset] = old_byte ^ 0x01
    serialized["bytes_hex"] = raw_bytes.hex()
    # length is unchanged by construction: one byte flipped, none added.

    probe_path.write_text(
        json.dumps(record, indent=2, sort_keys=True) + "\n",
        encoding="utf-8", newline="\n",
    )
    return {
        "file": probe_path.name,
        "stage_byte_offset": offset,
        "old_byte_hex": f"{old_byte:02x}",
        "new_byte_hex": f"{raw_bytes[offset]:02x}",
        "mutation": "XOR 0x01 on the first byte of the declared magic window",
    }


def require_detection(run_dir):
    """Phase 5: the oracle over the seeded set MUST raise.

    THE INVERTED-FAILURE PROPERTY LIVES HERE. The success path of this
    function is the oracle's failure path; an oracle that stays green on a
    corrupted probe makes THIS script exit 1. A self-test that can only pass
    is worthless, so the pass is earned by a caught defect and nothing else.
    Returns the oracle's verbatim rejection for the evidence report.
    """
    try:
        verify.verify_artifacts(run_dir)
    except verify.OracleError as exc:
        return str(exc)
    _fail(
        "the oracle stayed GREEN on the seeded defect — detection failed; "
        "the oracle's green cannot be trusted until this is resolved"
    )


def main():
    started = _utc_now()
    print(f"Seam oracle seeded-defect self-test (task 0.4) — {started}")

    # 2. TREE SNAPSHOT.
    before = snapshot_tree()
    print(f"  tree snapshot: {len(before)} committed files hashed")

    # 3. BASELINE.
    with tempfile.TemporaryDirectory(prefix="seam-selftest-a-") as tmp_a:
        baseline_hashes = baseline_run(tmp_a)
        print("  baseline: pipeline emitted into temp dir A; oracle GREEN")
        for rid, digest in sorted(baseline_hashes.items()):
            print(f"    {rid:<14} sha256 {digest[:16]}…")

        # 4. SEEDED RUN: copy A to B, corrupt one generator output in B.
        with tempfile.TemporaryDirectory(prefix="seam-selftest-b-") as tmp_b:
            for filename in verify.ARTIFACTS.values():
                shutil.copy2(Path(tmp_a) / filename, Path(tmp_b) / filename)
            mutation = seed_defect(tmp_b)
            print(f"  seeded run: {mutation['mutation']} "
                  f"in {mutation['file']} at stage byte {mutation['stage_byte_offset']} "
                  f"({mutation['old_byte_hex']} -> {mutation['new_byte_hex']})")

            # 5. DETECTION: green here is THIS script's failure.
            rejection = require_detection(tmp_b)
            print(f"  detection: oracle REJECTED the seeded set:")
            print(f"    {rejection}")

    # 7. TREE UNTOUCHED (checked BEFORE evidence is written: the evidence
    # file must never be what explains away a damaged tree).
    after = snapshot_tree()
    if before != after:
        changed = sorted(
            set(before) ^ set(after)
            | {p for p in before.keys() & after.keys() if before[p] != after[p]}
        )
        _fail(f"committed tree changed during the run: {changed}")
    print(f"  tree untouched: {len(after)} files byte-identical to the snapshot")

    # 6. EVIDENCE, LAST: emitted only on the all-green path, so a red run
    # can never leave green-looking evidence behind. PINS.md standard:
    # command, actuals, verdicts — an entry that merely asserts success is
    # an assurance, which is the one thing this lane's evidence never is.
    SELFTEST_DIR.mkdir(parents=True, exist_ok=True)
    report_path = SELFTEST_DIR / "selftest-report.json"
    report = {
        "task": "0.4 oracle seeded-defect self-test",
        "started_utc": started,
        "command": "python3 fixtures/seam/gen/self_test_defect.py",
        "python_version": sys.version.split()[0],
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
        "tree_untouched": {
            "committed_files_hashed": len(after),
            "verdict": "byte-identical before and after",
        },
        "exit_code": 0,
    }
    report_path.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8", newline="\n",
    )
    print(f"  evidence: {report_path.relative_to(SEAM_DIR.parents[1])}")

    print("SELF-TEST GREEN: baseline green, seeded defect CAUGHT by the "
          "oracle, committed tree untouched, evidence emitted.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
