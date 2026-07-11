"""generate.py — the fixture pipeline.

Order of operations (aborts loudly on any failure):
  1. GATE on the grammar doc hash.
  2. Run txkit / grammar / verify self-tests in-process.
  3. Build all cases from families.CASES.
  4. Replay the oracle over every case; computed verdict/reason/labels must
     equal the declared expectation. Derive claimant indices from labels.
  5. Coverage: emitted case-id set == the required list, exactly.
  6. Determinism: build the full artifact set twice; byte-identical.
  7. Emit atomically (hex vectors, manifest.json, SUMMARY.md).
  8. Print a run report.
"""

import hashlib
import json
import os
import sys
from pathlib import Path

import donor
import families
import grammar
import txkit
import verify

REPO_ROOT = Path(__file__).resolve().parents[3]
GRAMMAR_DOC = REPO_ROOT / "marker-grammar-DRAFT.md"
VECTORS_DIR = REPO_ROOT / "fixtures" / "marker" / "vectors"
HEX_DIR = VECTORS_DIR / "hex"

SEMANTICS_NOTE = (
    "membership and encoding are orthogonal axes; an output can be "
    "CLAIMS+CANONICAL inside a MALFORMED transaction; unlisted outputs are "
    "IGNORED; reason_code is the FIRST failing Section 3 rule."
)

SYNTHETIC_WARNING = (
    "These are synthetic transaction serializations built from the donor's "
    "input bytes. They are not asserted to be valid spends of the donor UTXO "
    "and must not be broadcast or used as Bitcoin inclusion/Merkle fixtures. "
    "Grammar verification only."
)


def _fail(msg):
    print(msg, file=sys.stderr)
    sys.exit(1)


def gate_grammar_doc():
    digest = hashlib.sha256(GRAMMAR_DOC.read_bytes()).hexdigest()
    if digest != grammar.EXPECTED_GRAMMAR_SHA256:
        _fail(
            "grammar doc changed: re-review grammar.py and verify.py before "
            "regenerating"
        )
    return digest


def _claimants_from_labels(labels):
    return sorted(i for i, lab in labels.items() if tuple(lab)[0] == "CLAIMS")


def verify_case(cid, spec):
    """Replay the oracle; return the validated derived facts for the manifest."""
    gv, rc, per = verify.verdict_tx(spec.raw_tx, spec.deal_context)
    if gv != spec.grammar_verdict:
        _fail(f"{cid}: grammar_verdict {gv!r} != expected {spec.grammar_verdict!r}")
    if rc != spec.reason_code:
        _fail(f"{cid}: reason_code {rc!r} != expected {spec.reason_code!r}")

    computed = {i: lab for i, lab in enumerate(per)}
    for i, lab in spec.labels.items():
        if computed.get(i) != tuple(lab):
            _fail(f"{cid}: label[{i}] {computed.get(i)!r} != expected {tuple(lab)!r}")
    for i, lab in computed.items():
        if i not in spec.labels and lab != ("IGNORED", "NOT_APPLICABLE"):
            _fail(f"{cid}: unlisted output {i} is not IGNORED: {lab!r}")

    expected_claimants = _claimants_from_labels(spec.labels)
    computed_claimants = sorted(
        i for i, lab in computed.items() if lab[0] == "CLAIMS"
    )
    if expected_claimants != computed_claimants:
        _fail(f"{cid}: claimant indices {computed_claimants} != {expected_claimants}")

    if cid == "N15c":
        tx = verify.parse_legacy_tx(spec.raw_tx)
        if not tx["output_count"] > grammar.ASSUMED_SCAN_CAPACITY:
            _fail(f"N15c: outputCount {tx['output_count']} not > capacity")

    return expected_claimants


def build_record(cid, spec, claimants):
    raw = spec.raw_tx
    dc = spec.deal_context
    return {
        "case_id": cid,
        "family": spec.family,
        "label": spec.label,
        "grammar_verdict": spec.grammar_verdict,
        "reason_code": spec.reason_code,
        "capacity_expectation": spec.capacity_expectation,
        "expected_labels": {
            str(i): list(lab) for i, lab in sorted(spec.labels.items())
        },
        "expected_claimant_indices": claimants,
        "deal_context": {
            "expected_ergo_net": dc["expected_ergo_net"],
            "expected_btc_net": dc["expected_btc_net"],
            "expected_vault_id": dc["expected_vault_id"].hex(),
            "committed_script": dc["committed_script"].hex(),
            "committed_sats": dc["committed_sats"],
        },
        "notes": spec.notes,
        "txid_display": txkit.txid_display(raw),
        "txid_internal": txkit.txid_internal(raw).hex(),
        "hex_path": f"hex/{cid}.hex",
        "synthetic": True,
    }


def build_artifacts(doc_sha):
    """Compute (hex_map, manifest_text, summary_text) from families.CASES."""
    hex_map = {}
    records = []
    for cid in families.REQUIRED_CASES:
        spec = families.CASES[cid]
        claimants = verify_case(cid, spec)
        hex_map[cid] = spec.raw_tx.hex() + "\n"
        records.append(build_record(cid, spec, claimants))

    records.sort(key=lambda r: r["case_id"])

    manifest = {
        "schema_version": "1",
        "status": grammar.STATUS,
        "grammar_revision": grammar.GRAMMAR_REVISION,
        "grammar_doc_sha256": doc_sha,
        "donor": {
            "txid_display": donor.DONOR_TXID_DISPLAY,
            "raw_sha256": hashlib.sha256(
                bytes.fromhex(donor.DONOR_HEX)
            ).hexdigest(),
        },
        "deployment": {
            "ergo_net": grammar.DEPLOY_ERGO_NET,
            "btc_net": grammar.DEPLOY_BTC_NET,
        },
        "assumed_scan_capacity": grammar.ASSUMED_SCAN_CAPACITY,
        "semantics_note": SEMANTICS_NOTE,
        "synthetic_vector_warning": SYNTHETIC_WARNING,
        "vectors": records,
    }
    manifest_text = json.dumps(manifest, indent=2, sort_keys=True) + "\n"

    lines = [
        "# Marker fixture vectors — SUMMARY",
        "",
        "**STATUS: PRE-FREEZE — DRAFT grammar, freeze gated on the lifecycle "
        "checkpoint. Do not treat as final.**",
        "",
        "| case_id | family | grammar_verdict | reason_code | txid_display | label |",
        "|---------|--------|-----------------|-------------|--------------|-------|",
    ]
    for r in records:
        rc = r["reason_code"] if r["reason_code"] is not None else ""
        lines.append(
            f"| {r['case_id']} | {r['family']} | {r['grammar_verdict']} | "
            f"{rc} | {r['txid_display']} | {r['label']} |"
        )
    summary_text = "\n".join(lines) + "\n"

    return hex_map, manifest_text, summary_text


def _atomic_write(path: Path, text: str):
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def main():
    # 1. GATE.
    doc_sha = gate_grammar_doc()

    # 2. Self-tests in-process.
    txkit.self_test()
    grammar.self_test()
    verify.self_test()

    # 3-5. Build + verify + coverage (verify_case runs inside build_artifacts).
    if set(families.CASES) != set(families.REQUIRED_CASES):
        _fail("coverage: emitted case set != required list")
    hex_map, manifest_text, summary_text = build_artifacts(doc_sha)
    assert set(hex_map) == set(families.REQUIRED_CASES)

    # 6. Determinism: second independent build must be byte-identical.
    hex_map2, manifest_text2, summary_text2 = build_artifacts(doc_sha)
    if (hex_map, manifest_text, summary_text) != (
        hex_map2, manifest_text2, summary_text2
    ):
        _fail("determinism: second build differs from the first")

    # 7. Emit atomically.
    HEX_DIR.mkdir(parents=True, exist_ok=True)
    for cid, text in hex_map.items():
        _atomic_write(HEX_DIR / f"{cid}.hex", text)
    _atomic_write(VECTORS_DIR / "manifest.json", manifest_text)
    _atomic_write(VECTORS_DIR / "SUMMARY.md", summary_text)

    # 8. Run report.
    per_family = {}
    for cid in families.REQUIRED_CASES:
        fam = families.CASES[cid].family
        per_family[fam] = per_family.get(fam, 0) + 1
    print("Marker fixture generation report (PRE-FREEZE)")
    print("  grammar_doc_sha256:", doc_sha)
    print("  cases per family:")
    for fam in sorted(per_family, key=lambda f: (f[0], int(f[1:]))):
        print(f"    {fam:<4} {per_family[fam]}")
    print("  total vectors:", len(hex_map))
    print("ALL GREEN: self-tests, oracle agreement, coverage, determinism, emit.")


if __name__ == "__main__":
    main()
