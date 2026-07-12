# plan.md — Marker Fixture Generator (btc-composition)

Timestamp: 2026-07-11 (v2)
Status: PRE-FREEZE build. Grammar: marker-grammar-DRAFT.md revision v3 (2026-07-11).
Pipeline position: PLAN. Revision history: v1 after 4-model adversarial review
round (Groq, ChatGPT, Gemini, Claude Fable); v2 after ChatGPT review of plan +
build prompt (12 findings, all adopted).
Machine: programingPC, ~/Projects/btc-composition/
Consumer: Shannon's Scala test harness (sigmastate-native, per PR #1182 lane).

---

## 1. What we are building

A python3 generator that emits the complete P1-P6 / N1-N15 fixture set defined
in Section 4 of marker-grammar-DRAFT.md, as full serialized legacy Bitcoin
transactions, each independently re-verified against the grammar before
emission. Fixtures are cheap regenerable output. Construction facts are
centralized in grammar.py; the independent verifier deliberately RETRANSCRIBES
the normative grammar from the document to avoid common-mode errors. All
vectors carry PRE-FREEZE status until the grammar freezes.

## 2. Language and dependencies

Python standard library only; no third-party dependencies. Core modules:
hashlib, struct, json, os, sys (dataclasses/typing/pathlib permitted).

## 3. Architecture (layered)

```
fixtures/marker/
  gen/
    donor.py       DONOR_HEX (block 342,854 raw tx) + DONOR_TXID_DISPLAY.
    txkit.py       protocol-agnostic layer. Knows NOTHING about markers:
                   imports nothing from grammar.py. CompactSize encode,
                   TxOut framing, donor output-section rebuild, raw_splice
                   (zero-recalculation script injection), dSHA256,
                   txid_internal(raw)=dsha256(raw) and
                   txid_display(raw)=dsha256(raw)[::-1].hex().
                   LEGACY-ONLY parser: aborts if the byte after version is
                   0x00 with a nonzero witness flag (SegWit marker/flag),
                   rather than misreading it as zero inputs.
                   Generalization seam: post-freeze extraction candidate
                   (TODO ideas-dd2f).
    grammar.py     protocol facts, CONSTRUCTION side. PRIMITIVE facts only;
                   dependent constants DERIVED, never hand-copied:
                     FIELDS = [(magic,4),(version,1),(ergo_net,1),
                               (btc_net,1),(vout,4),(vault_id,32)]
                     PAYLOAD_LEN = sum(sizes)            # 43
                     PUSH_OPCODE = PAYLOAD_LEN           # 0x2b
                     assert PAYLOAD_LEN <= 0x4b          # direct-push ceiling
                     SCRIPT_LEN  = PAYLOAD_LEN + 2       # 45
                   Offsets derived by cumulative sum of FIELDS. Also:
                   STATUS="PRE-FREEZE", GRAMMAR_REVISION="v3",
                   EXPECTED_GRAMMAR_SHA256 (pinned), ASSUMED_SCAN_CAPACITY=300,
                   fixture deployment constants (ergo_net=0x01, btc_net=0x01),
                   EXPECTED_VAULT_ID (the Section 1 test-vector id), and
                   near-miss magics COMPUTED from MAGIC (last byte +1, last
                   byte -1, lowercase) so a magic change at freeze cannot
                   silently degrade family N6.
    families.py    one function per fixture family, registry of stable case
                   IDs. Builds vectors from fresh immutable bytes.
                   CONSTRUCTION DISCIPLINE (post-review refinement):
                   malformed PUSH FRAMING is assembled manually from raw
                   bytes, but payload CONTENT normally comes from
                   grammar.build_canonical_payload() or derivations of it
                   (payload[:-1] for length 42, payload + 0x00 for 44), so a
                   grammar change propagates into the malformed families
                   instead of leaving them silently testing the old protocol.
                   txkit.txout() preserves every resulting script verbatim
                   (raw splice: no normalization, no repair, no allocation of
                   declared lengths).
    verify.py      the independent oracle. Does NOT import txkit.py or
                   donor.py, and does NOT import layout constants from
                   grammar.py (bookkeeping fields only: STATUS, revision,
                   pinned doc hash, scan capacity). Grammar-logical values
                   are its OWN hardcoded literals transcribed from the doc,
                   each commented with its section. Own minimal LEGACY-ONLY
                   tx parser (independent SegWit abort check), strict
                   framing: rejects trailing bytes, truncated fields,
                   incomplete outer CompactSize before marker logic;
                   script-slice boundary respected exactly. Duplicated
                   parsing logic is intentional redundancy.
    generate.py    entry point; see Section 4 pipeline.
  vectors/
    manifest.json  authoritative index (regenerable, never hand-edited)
    hex/{case_id}.hex   one raw tx per file (lowercase hex, exactly one final
                   newline), referenced from manifest
    SUMMARY.md     generated review table: case_id, verdict, txid_display
```

Both self-testing modules expose `def self_test() -> None` plus an
`if __name__ == "__main__"` runner, so generate.py calls them in-process. All
paths resolve from `__file__`, never from the current working directory.

## 4. Build gates and self-tests (the oracle-independence core)

generate.py pipeline, abort loudly at each step: (1) doc-hash GATE, (2) txkit
+ verify self_test() in-process, (3) build all cases, (4) verify every vector,
(5) required-set coverage assertion, (6) determinism check (build twice in
memory, byte-identical), (7) atomic emit.

- **Doc-hash gate:** EXPECTED_GRAMMAR_SHA256 pinned in grammar.py; generate.py
  hashes marker-grammar-DRAFT.md (path from __file__) and ABORTS on mismatch
  ("doc changed: re-review grammar.py and verify.py before regenerating").
  Prerequisite: fix the doc's title line ("DRAFT v2" vs revision v3) in a tiny
  commit BEFORE pinning.
- **Doc-literal membership self-tests** (hardcoded hex transcribed from the
  doc, never composed from grammar.py): `6a4c0045524756` must NOT claim;
  `6a4e0400008045524756` MUST claim (unsigned decode) and be noncanonical;
  the Section 1 vault_id byte-order vector.
- **Canonical-marker golden (construction↔doc bridge):** grammar.py's builder
  output for (mainnet/mainnet, vout=1, the test vault id) must equal a
  HARDCODED hex literal not computed from grammar.py:
  `6a2b455247560101010100000000112233445566778899aabbccddeeff00112233445566778899aabbccddeeff`
  (computed independently 2026-07-11 and verified). Catches wrong field order,
  wrong fixture network, wrong vault id, wrong offsets at correct total
  length — the shared-fixture-context class the verifier alone cannot expose.
- **Donor anchors:** `txid_display(donor) == b33c1252...` (display is the
  REVERSAL of dsha256; internal order is dsha256 directly — both orders
  verified by computation 2026-07-11); verify.py's own walk re-derives the
  scratch doc's independently computed offset map (outputCount at byte 153 ==
  2, out0 value 20,000 sats, out0 spk 25 bytes at 163..188, out1 spk 38
  bytes, push 0x24, locktime at 235..239).
- **txkit goldens:** CompactSize 252/253/257/65535/65536 (257 == fd0101, the
  P6 boundary); one complete TxOut golden; donor parse-and-reassemble
  byte-identical; SegWit-pattern abort test.
- **Determinism:** sorted case IDs, json indent=2 sort_keys, NO timestamps in
  outputs, atomic write, two consecutive builds byte-identical.

## 5. Verdict schema

Per-output labels (sparse; unlisted outputs default IGNORED):
`membership: IGNORED | CLAIMS` and `encoding: CANONICAL | NONCANONICAL |
NOT_APPLICABLE`. Labels are produced for every output even when the
transaction fails an early rule. Documented header example: an N7
wrong-version output is CLAIMS + CANONICAL while the TRANSACTION is MALFORMED.
Claimant indices are DERIVED from the labels (no singular
expected_marker_index field — it cannot represent two-claimant cases like
N2, N4d-f, N15a); each record carries `expected_claimant_indices: [...]`
computed from the labels for harness convenience.

Transaction-level: `grammar_verdict: VALID | MALFORMED | NOT-A-SETTLEMENT`
(pure protocol truth, capacity never mixed in), plus a nullable
`capacity_expectation` object:
```
"capacity_expectation": {
  "minimum_capacity": 301,
  "below_minimum": "REJECT_SCAN_CAPACITY",
  "at_or_above_minimum": "USE_GRAMMAR_VERDICT"
}
```
N15 decomposition: N15a two claimants within capacity → grammar_verdict
MALFORMED, capacity_expectation null; N15b single claimant at outputCount ==
300 → VALID, null; N15c outputCount == 301, otherwise valid → grammar_verdict
VALID, capacity_expectation with minimum_capacity 301.

Reason codes: fixed enum, FIRST failing Section 3 rule only (rules are
evaluated in order, so the intended failure is never obscured by secondary
ones): ZERO_CLAIMANTS, MULTIPLE_CLAIMANTS, NONCANONICAL_MARKER,
NONZERO_MARKER_VALUE, VERSION_MISMATCH, ERGO_NETWORK_MISMATCH,
BITCOIN_NETWORK_MISMATCH, VAULT_ID_MISMATCH, VOUT_OUT_OF_RANGE,
VOUT_IS_MARKER, PAYMENT_SCRIPT_MISMATCH, PAYMENT_AMOUNT_TOO_LOW. Both
families.py (expectation) and verify.py (result) use this one enum, defined
in a tiny shared codes module or duplicated verbatim with a cross-check test.

## 6. Manifest provenance (per vector)

case_id, family, label, hex_path, txid_display, txid_internal (hex string of
dsha256(raw), unreversed; never a bare "txid" field), synthetic: true,
per-output labels, expected_claimant_indices, grammar_verdict,
capacity_expectation (nullable), expected_reason_code, deal context (committed
scriptPubKey hex + its sha256, committedSats, expected vault_id), notes.
Manifest header: schema_version, STATUS=PRE-FREEZE, grammar revision, grammar
doc sha256, donor txid_display + donor raw sha256, deployment constants,
assumed_scan_capacity, the canonical-vs-claims semantics note, and this
synthetic-vector warning (soft wording, no sighash assumption): "These are
synthetic transaction serializations built from the donor's input bytes. They
are not asserted to be valid spends of the donor UTXO and must not be
broadcast or used as Bitcoin inclusion/Merkle fixtures. Grammar verification
only."

## 7. Fixture construction context

Donor: the real block-342,854 legacy tx (raw hex in
fixture-inventory-SCRATCH.md). Input side and locktime kept; output section
rebuilt per family. The donor's real OP_RETURN ("First OPReturn Message...")
is the unrelated-prefix output for P2/N6. Committed deal context: committed
script = donor out0 P2PKH (hash160 3f53b874...), committedSats = 20,000
(equality passes at-least; N14a lowers the named output to 19,999). Expected
vault_id = the Section 1 test-vector id. Filler outputs: minimal OP_RETURN
TxOuts. Marker payload canonical form: ERGV | 0x01 | 0x01 | 0x01 | vout
uint32 LE | vault_id 32 raw bytes.

## 8. Required case set (coverage-asserted in generate.py)

P1a marker-first/payment-after, P1b marker-middle/payment-before, P1c
marker-middle/payment-after, P1d marker-last/payment-before; P2a unrelated
OP_RETURN before marker, P2b after; P3 two qualifying payments, named vout is
one; P4 vout == outputCount-1; P5 vout=1 as 01000000; P6 vout=256 as 00010000,
257 outputs.
N1 zero claimants; N2a two canonical same vault_id, N2b different; N3a len 42,
N3b len 44, N3c declared 43 truncated, N3d trailing byte, N3e trailing second
push; N4a/b/c PUSHDATA1/2/4 correct payload alone, N4d/e/f each alongside a
canonical marker; N5a-d PD1 declared len 0/1/2/3 with magic following
(IGNORED), N5e declared >= 4, magic present, push extends past slice (CLAIMS,
malformed), N5f slice ends before 4 magic bytes (IGNORED), N5g/h/i incomplete
PD1/PD2/PD4 length prefixes (IGNORED), N5j PD4 0x80000004 (CLAIMS, malformed);
N6a empty first push + magic second push, N6b unrelated first push + magic
second push, N6c magic in P2WSH, N6d magic in P2TR, N6e script not starting
0x6a, N6f/g/h computed near-miss magics; N7 version 0x02; N8a btc_net wrong,
N8b ergo_net wrong, N8c/d unlisted enum values; N9a different vault (the M2
counterexample anchor), N9b one-byte mismatch, N9c full byte reversal; N10
big-endian vout; N11a vout == outputCount, N11b vout == markerOutputIndex,
N11c 0xffffffff; N12 nonzero marker value; N13 named output fails while
another qualifies; N14a right script insufficient amount, N14b sufficient
amount wrong script; N15a/b/c per Section 5.

## 9. Decisions log

- Emission: manifest index + per-vector hex files + SUMMARY.md (owner decision,
  2026-07-11).
- SegWit second donor: DEFERRED (owner decision, 2026-07-11); v2 adds explicit
  legacy-only guards in both parsers instead (abort on witness marker/flag).
- Generalization: NOT now; clean txkit seam; post-freeze extraction = TODO
  ideas-dd2f.
- Outer-framing negative families: NOT generated (grammar does not define
  them); verify.py strict regardless; listed as a question for Shannon's
  grammar review.
- v2 amendments (ChatGPT review, all 12 adopted): txid byte-order definitions
  fixed; malformed families derive payload content from grammar.py (framing
  raw); expected_marker_index replaced by label-derived
  expected_claimant_indices; grammar_verdict separated from nullable
  capacity_expectation; reason-code enum fixed, first-failing-rule; legacy-only
  parser guards; canonical-marker hardcoded golden added; consensus-invalid
  wording softened; self_test() callables; __file__ path resolution; .hex
  single-final-newline; stdlib wording clarified.

## 10. Impact analysis and security

Public repo; no secrets anywhere in inputs or outputs (public blockchain data
+ synthetic bytes). Scrub gate before any commit: two-stage address pattern
(match 9[1-9A-HJ-NP-Za-km-z]{50} then exclude pure-hex lines), IPs, hostnames,
usernames; the owner additionally runs a private name-grep before push. No running
services touched. New directory only; nothing existing modified except the
one-line grammar-doc title fix. Rollback: git. Build on a feature branch; CC
does NOT push — the owner reviews the diff, runs the scrub gate, pushes.

## 11. Freeze impact

At freeze: edit grammar.py primitive facts (magic, possibly nets), update
verify.py's independent literals AND the canonical-marker golden (intentional
redundancy — three conscious edits), re-pin EXPECTED_GRAMMAR_SHA256, flip
STATUS, rerun. Minutes, not days. If Shannon's grammar review lands mid-build:
the doc-hash gate hard-stops regeneration until constants, oracle, and golden
are consciously re-reviewed.
