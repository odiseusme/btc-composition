"""generate.py — the fixture pipeline.

Order of operations (aborts loudly on any failure):
  1. GATE on the grammar doc: reject any CR byte, then hash the exact LF-only
     bytes and compare to the pin.
  2. Run txkit / grammar / verify self-tests in-process.
  3. Build all cases from families.CASES.
  4. Replay the oracle over every case; computed verdict/reason/labels must
     equal the declared expectation. Derive claimant indices from labels.
     Compute the Section 7 profile layer for every case, and assert it where
     the case declares an expectation (N15d/N15e).
  5. Coverage: emitted case-id set == the required list, exactly.
  6. Determinism: build the full artifact set twice; byte-identical.
  7. Emit atomically (hex vectors, manifest.json, SUMMARY.md). Atomicity is
     PER FILE (temp + os.replace), not set-wide.
  8. Stale-file hygiene: delete any .hex not in the case set, reporting each.
  9. Print a run report.

TWO VERDICT LAYERS (Section 7). Every vector carries the ABSTRACT GRAMMAR
VERDICT (Sections 2-3, no implementation bound) and, separately, a PROFILE
VERDICT per named profile: equal to the grammar verdict when the transaction is
in profile, else REJECT-OUT-OF-PROFILE. The manifest keys both by profile name
so future profiles are additive.

ALL text writes use newline="\\n" explicitly: the fixtures are LF-only.
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

PROFILE_NAME = verify._PROFILE_NAME          # "sigmastate-v1" (Section 7)
REJECT_OUT_OF_PROFILE = "REJECT-OUT-OF-PROFILE"

SEMANTICS_NOTE = (
    "membership and encoding are orthogonal axes; an output can be "
    "CLAIMS+CANONICAL inside a MALFORMED transaction; unlisted outputs are "
    "IGNORED; reason_code is the FIRST failing Section 3 rule."
)

PROFILE_NOTE = (
    "TWO VERDICT LAYERS (grammar Section 7). grammar_verdict is protocol truth "
    "from Sections 2-3, computed with NO implementation bound. "
    "profile_verdicts[P] is a SEPARATE layer for a named verifier profile P: it "
    "equals grammar_verdict when the transaction is IN PROFILE, else "
    "REJECT-OUT-OF-PROFILE, and profile_violations[P] lists every violated "
    "profile constraint as Section 7 item numbers in document order 1-4 (empty "
    "when in profile). Rejecting out of profile is fail-closed and is never a "
    "grammar result: P6 and the at-capacity N15 members are grammar-VALID but "
    "out of profile for sigmastate-v1, whose scan capacity is 4 outputs. The "
    "concrete 4-vs-5 boundary is N15d (in profile) vs N15e (N15d plus exactly "
    "one appended output). PAYMENT ABI (Section 3 rule 7): the deal commits "
    "committedScriptHash = SHA256(buyer scriptPubKey) -- a single SHA-256 over "
    "the raw scriptPubKey bytes exactly as they appear inside the output, with "
    "NO CompactSize length prefix, NO byte reversal, and NO second hash -- "
    "never the raw script itself. Carried as text it is exactly 64 lowercase "
    "hex characters representing the 32 raw bytes, decoded to bytes before "
    "comparison. deal_context.committed_script is retained as construction "
    "provenance only; the oracle reads committed_script_hash."
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
    """Hash the normative doc's EXACT bytes, read in BINARY.

    A CRLF checkout would change every line's bytes and so change the digest;
    the gate names that cause explicitly instead of reporting a bogus "doc
    changed". The pinned hash is over LF-only bytes; .gitattributes keeps the
    working tree that way.
    """
    raw = GRAMMAR_DOC.read_bytes()
    if b"\r" in raw:
        _fail("CRLF checkout detected — fix line endings, see .gitattributes")
    digest = hashlib.sha256(raw).hexdigest()
    if digest != grammar.EXPECTED_GRAMMAR_SHA256:
        _fail(
            "grammar doc changed: re-review grammar.py and verify.py before "
            "regenerating"
        )
    return digest


def _claimants_from_labels(labels):
    return sorted(i for i, lab in labels.items() if tuple(lab)[0] == "CLAIMS")


def profile_layer(cid, spec):
    """Section 7: compute (profile_verdict, violations) for this case.

    Separate layer from the grammar verdict. Where the case DECLARES an expected
    violations list (the N15d/N15e boundary), the computed list must match it.
    """
    in_profile, violations = verify.classify_profile(spec.raw_tx)

    declared = spec.expected_profile_violations
    if declared is not None and violations != declared:
        _fail(
            f"{cid}: profile_violations {violations} != declared {declared}"
        )

    verdict = spec.grammar_verdict if in_profile else REJECT_OUT_OF_PROFILE
    return verdict, violations


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
        tx = verify.parse_stripped_tx(spec.raw_tx)
        if not tx["output_count"] > grammar.ASSUMED_SCAN_CAPACITY:
            _fail(f"N15c: outputCount {tx['output_count']} not > capacity")

    return expected_claimants


def build_record(cid, spec, claimants, profile_verdict, profile_violations):
    raw = spec.raw_tx
    dc = spec.deal_context
    return {
        "case_id": cid,
        "family": spec.family,
        "label": spec.label,
        "grammar_verdict": spec.grammar_verdict,
        "reason_code": spec.reason_code,
        # Section 7: keyed by profile name so future profiles are additive.
        "profile_verdicts": {PROFILE_NAME: profile_verdict},
        "profile_violations": {PROFILE_NAME: profile_violations},
        "capacity_expectation": spec.capacity_expectation,
        "expected_labels": {
            str(i): list(lab) for i, lab in sorted(spec.labels.items())
        },
        "expected_claimant_indices": claimants,
        "deal_context": {
            "expected_ergo_net": dc["expected_ergo_net"],
            "expected_btc_net": dc["expected_btc_net"],
            "expected_vault_id": dc["expected_vault_id"].hex(),
            # committed_script is construction provenance; the oracle's rule-7
            # predicate reads committed_script_hash (the composed-vault ABI).
            "committed_script": dc["committed_script"].hex(),
            "committed_script_hash": dc["committed_script_hash"],
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
        pv, pviol = profile_layer(cid, spec)
        hex_map[cid] = spec.raw_tx.hex() + "\n"
        records.append(build_record(cid, spec, claimants, pv, pviol))

    records.sort(key=lambda r: r["case_id"])

    manifest = {
        "schema_version": "2",
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
        "profiles": {
            PROFILE_NAME: {
                "min_inputs": verify._PROFILE_MIN_INPUTS,
                "max_inputs": verify._PROFILE_MAX_INPUTS,
                "min_outputs": verify._PROFILE_MIN_OUTPUTS,
                "max_outputs": verify._PROFILE_MAX_OUTPUTS,
                "compactsize_single_byte": True,
                "stripped_only": True,
                "constraint_items": {
                    "1": "stripped (non-witness) serialization only",
                    "2": "inputCount in {1, 2}",
                    "3": "outputCount in {1, 2, 3, 4} (scan capacity 4)",
                    "4": "every CompactSize field single-byte (< 0xfd)",
                },
            },
        },
        "semantics_note": SEMANTICS_NOTE,
        "profile_note": PROFILE_NOTE,
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
        f"Two verdict layers (grammar Section 7): `grammar_verdict` is protocol "
        f"truth with no implementation bound; `{PROFILE_NAME}` is the profile "
        "layer — the grammar verdict when in profile, else "
        "`REJECT-OUT-OF-PROFILE` annotated with the FIRST violated Section 7 "
        "item (the manifest carries the full ordered list).",
        "",
        f"| case_id | family | grammar_verdict | reason_code | {PROFILE_NAME} | "
        "txid_display | label |",
        "|---------|--------|-----------------|-------------|"
        "---------------|--------------|-------|",
    ]
    for r in records:
        rc = r["reason_code"] if r["reason_code"] is not None else ""
        viol = r["profile_violations"][PROFILE_NAME]
        pv = r["profile_verdicts"][PROFILE_NAME]
        # Profile column: the profile verdict, plus the FIRST violated item when
        # out of profile (the manifest holds every violated item, in order).
        prof = pv if not viol else f"{pv} (item {viol[0]})"
        lines.append(
            f"| {r['case_id']} | {r['family']} | {r['grammar_verdict']} | "
            f"{rc} | {prof} | {r['txid_display']} | {r['label']} |"
        )
    summary_text = "\n".join(lines) + "\n"

    return hex_map, manifest_text, summary_text


def _atomic_write(path: Path, text: str):
    """Atomic PER FILE (temp + os.replace); the SET is not atomic as a whole.

    newline="\\n" is explicit: no platform translation, LF-only output, matching
    the .gitattributes policy and the CR-rejecting doc gate.
    """
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    os.replace(tmp, path)


def prune_stale_vectors(case_ids):
    """Delete any .hex whose case id is not in the (already validated) set.

    NORMATIVE ORDERING: this runs only AFTER the complete expected case set has
    been generated and validated, so a failed run never deletes anything. Every
    deleted path is reported.
    """
    deleted = []
    for path in sorted(HEX_DIR.glob("*.hex")):
        if path.stem not in case_ids:
            path.unlink()
            deleted.append(path)
    return deleted


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

    # 7. Emit atomically (per file).
    HEX_DIR.mkdir(parents=True, exist_ok=True)
    for cid, text in hex_map.items():
        _atomic_write(HEX_DIR / f"{cid}.hex", text)
    _atomic_write(VECTORS_DIR / "manifest.json", manifest_text)
    _atomic_write(VECTORS_DIR / "SUMMARY.md", summary_text)

    # 8. Stale-file hygiene, AFTER a fully successful generate+validate.
    deleted = prune_stale_vectors(set(hex_map))

    # 9. Run report.
    per_family = {}
    for cid in families.REQUIRED_CASES:
        fam = families.CASES[cid].family
        per_family[fam] = per_family.get(fam, 0) + 1
    print("Marker fixture generation report (PRE-FREEZE)")
    print("  grammar_revision: ", grammar.GRAMMAR_REVISION)
    print("  grammar_doc_sha256:", doc_sha)
    print("  manifest schema:  ", "2")
    print("  cases per family:")
    for fam in sorted(per_family, key=lambda f: (f[0], int(f[1:]))):
        print(f"    {fam:<4} {per_family[fam]}")
    print("  total vectors:", len(hex_map))

    in_prof = sum(
        1 for cid in families.REQUIRED_CASES
        if not verify.classify_profile(families.CASES[cid].raw_tx)[1]
    )
    print(f"  profile {PROFILE_NAME}: {in_prof} in profile, "
          f"{len(hex_map) - in_prof} REJECT-OUT-OF-PROFILE")

    if deleted:
        print("  stale vectors deleted:")
        for path in deleted:
            print("    -", path.relative_to(REPO_ROOT))
    else:
        print("  stale vectors deleted: none")

    print("ALL GREEN: self-tests, oracle agreement, profile layer, coverage, "
          "determinism, emit.")


if __name__ == "__main__":
    main()
