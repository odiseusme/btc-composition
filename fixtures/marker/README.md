# Settlement marker fixtures

Synthetic Bitcoin-transaction test vectors for the settlement **marker grammar**
(`marker-grammar-DRAFT.md`, revision v3). Each vector is a legacy transaction
serialization paired with the expected verdict of an independent grammar oracle,
so a marker-verifier implementation can be checked byte-for-byte against the
document.

## ⚠️ PRE-FREEZE

The grammar is **DRAFT — NOT FROZEN**; freeze is gated on the lifecycle
checkpoint. `status` is `PRE-FREEZE` throughout (manifest header, SUMMARY
banner, module constants). Do not treat these vectors, the magic value, or the
byte layout as final. Regenerate after any grammar change (see the gate below).

## Not real spends

Every vector is a **synthetic** serialization built from a real donor
transaction's input bytes. The vectors are NOT valid spends of the donor UTXO
and MUST NOT be broadcast or used as Bitcoin inclusion / Merkle fixtures. They
exist for grammar verification only. This warning is repeated verbatim in the
manifest (`synthetic_vector_warning`).

## Layout

```
fixtures/marker/
  README.md              this file
  gen/                   the generator (Python stdlib only, no dependencies)
    donor.py             donor tx constants (real, block 342854), verified by txid
    txkit.py             protocol-agnostic tx toolkit (CompactSize, raw TxOut
                         splice, dSHA256 txids, legacy parser, output rebuilder)
    grammar.py           marker CONSTRUCTION constants + canonical builders
    verify.py            the INDEPENDENT oracle (own literals + own parser)
    families.py          the 61-case registry (CASES: case_id -> CaseSpec)
    generate.py          the pipeline (gate, self-tests, verify, emit)
  vectors/
    hex/{case_id}.hex    one raw tx per file, lowercase hex, single trailing \n
    manifest.json        machine-readable index (schema below)
    SUMMARY.md           human-readable table
```

## Three-layer design (deliberate decoupling)

The construction side and the verification side are kept independent so a bug in
one cannot mask itself in the other:

- **txkit.py — protocol-agnostic.** Knows nothing about the marker. Pure
  Bitcoin serialization mechanics. Its `txout()` is a RAW SPLICE: scripts are
  used verbatim, never validated, normalized, or padded to a declared push
  length — malformed framing passes through untouched, which is what the
  negative fixtures need.
- **grammar.py — construction constants.** The field layout, magic/version/
  network bytes, and the two canonical builders. No dimensional literal is
  hardcoded: `PAYLOAD_LEN`, `PUSH_OPCODE`, `SCRIPT_LEN`, and `OFFSETS` all
  derive from `FIELDS`.
- **verify.py — the independent oracle.** Imports ONLY bookkeeping fields from
  grammar.py (`STATUS`, `GRAMMAR_REVISION`, `EXPECTED_GRAMMAR_SHA256`,
  `ASSUMED_SCAN_CAPACITY`, `REASON_CODES`) and NOTHING from txkit.py/donor.py.
  Every grammar-logical constant (magic bytes, offsets, lengths, net enums) is
  **retranscribed as its own literal from the document**, each commented with
  its doc section. It carries its own from-scratch legacy parser. The
  retranscription is intentional redundancy: if grammar.py and verify.py ever
  disagree, a self-test fails.

families.py bridges the two (builds with grammar.py + txkit.py, expects
verify.py's outcome); generate.py replays the oracle over every case and refuses
to emit on any mismatch.

## Legacy-only serialization

This version handles **legacy (non-SegWit) transactions only**. Both parsers
(txkit.py and verify.py, independently) abort with a clear error if, after the
4-byte version, they see `0x00` followed by a nonzero flag byte — the SegWit
marker/flag — rather than misinterpreting it as zero inputs.

## The doc-hash gate

`generate.py` step 1 computes the SHA-256 of `marker-grammar-DRAFT.md` (path
resolved from `__file__` to the repo root) and compares it to
`grammar.EXPECTED_GRAMMAR_SHA256`. On mismatch it aborts with:

```
grammar doc changed: re-review grammar.py and verify.py before regenerating
```

This forces a human to re-review both the construction constants and the
independently-transcribed oracle literals whenever the normative document
changes, instead of silently regenerating vectors against a moved target.

## Regenerating

```
python3 fixtures/marker/gen/generate.py
```

The pipeline, in order: (1) doc-hash gate; (2) run txkit/grammar/verify
self-tests in-process; (3) build all cases; (4) replay the oracle over each case
— computed grammar_verdict, reason_code, and every declared per-output label
must equal the expectation, and claimant indices are derived from the labels;
(5) coverage assertion (emitted set == the required 61); (6) determinism (build
twice in memory, byte-identical); (7) atomic emit (temp file + `os.replace`);
(8) run report. Any failure aborts loudly; nothing is emitted partially.

Each module also runs standalone (`python3 .../txkit.py`, etc.) via its own
`self_test()`.

## Manifest schema (`manifest.json`)

`schema_version` is `"1"`. `json.dump(indent=2, sort_keys=True)`. No timestamps
anywhere.

### Header fields

| field | meaning |
|-------|---------|
| `schema_version` | `"1"` |
| `status` | `PRE-FREEZE` |
| `grammar_revision` | `v3` |
| `grammar_doc_sha256` | SHA-256 of the normative doc the vectors were built against (matches the gate constant) |
| `donor.txid_display` | donor transaction id, Bitcoin display order |
| `donor.raw_sha256` | SHA-256 of the donor raw bytes |
| `deployment.ergo_net` / `deployment.btc_net` | the deployment network constants the oracle compared against (both `1` = mainnet here) |
| `assumed_scan_capacity` | the reference verifier's assumed output-scan bound (`300`); used only by the capacity layer, never by the grammar verdict |
| `semantics_note` | orthogonality of membership vs encoding; unlisted-are-IGNORED; reason_code is the FIRST failing rule |
| `synthetic_vector_warning` | the not-real-spends warning, verbatim |
| `vectors` | the per-case records, sorted by `case_id` |

### Per-vector record fields

| field | meaning |
|-------|---------|
| `case_id` | e.g. `P1a`, `N15c` |
| `family` | the taxonomy family (`P1`…`N15`) |
| `label` | one-line human description |
| `grammar_verdict` | `VALID` \| `MALFORMED` \| `NOT-A-SETTLEMENT` (see split below) |
| `reason_code` | the FIRST failing Section 3 rule's code, or `null` when VALID |
| `capacity_expectation` | `null` except N15c (see split below) |
| `expected_labels` | sparse map, `"index" -> [membership, encoding]`, listing only non-IGNORED outputs |
| `expected_claimant_indices` | output indices that CLAIM the magic (derived from the labels) |
| `deal_context` | the deal facts the oracle used: `expected_ergo_net`, `expected_btc_net`, `expected_vault_id` (hex), `committed_script` (hex), `committed_sats` |
| `notes` | construction / intent note |
| `txid_display` | vector txid, display order |
| `txid_internal` | `dSHA256(raw)` hex, UNREVERSED (internal order) |
| `hex_path` | `hex/{case_id}.hex`, relative to `vectors/` |
| `synthetic` | always `true` |

### grammar_verdict vs capacity_expectation (the split)

`grammar_verdict` is pure grammar truth from Section 3 and is computed **without
any scan-capacity bound** — a fully-scanned transaction's verdict:

- `NOT-A-SETTLEMENT` — zero outputs claim the magic (not in our namespace).
- `MALFORMED` — claims but fails a validity rule (multiple claimants,
  non-canonical marker, nonzero marker value, or a field/vout/payment failure).
- `VALID` — exactly one canonical claimant and all Section 3 rules pass.

`capacity_expectation` is a **separate layer** carried only where output count
exceeds the assumed scan capacity (N15c). It is `null` everywhere else,
including N15a/N15b. When present it is:

```json
{
  "minimum_capacity": 301,
  "below_minimum": "REJECT_SCAN_CAPACITY",
  "at_or_above_minimum": "USE_GRAMMAR_VERDICT"
}
```

meaning: a bounded verifier whose scan capacity is below `minimum_capacity` MUST
reject the transaction outright (it cannot prove exactly-one-claimant); at or
above it, defer to `grammar_verdict`. Section 3 rule 1 requires scanning every
output OR rejecting when outputCount exceeds capacity — a partial scan that
accepts is a defect (a second claimant could hide beyond the bound). The grammar
verdict itself never applies the bound; the capacity layer is where it lives.

### reason_code enum (Section 3)

Exactly these twelve strings:

```
ZERO_CLAIMANTS  MULTIPLE_CLAIMANTS  NONCANONICAL_MARKER  NONZERO_MARKER_VALUE
VERSION_MISMATCH  ERGO_NETWORK_MISMATCH  BITCOIN_NETWORK_MISMATCH
VAULT_ID_MISMATCH  VOUT_OUT_OF_RANGE  VOUT_IS_MARKER
PAYMENT_SCRIPT_MISMATCH  PAYMENT_AMOUNT_TOO_LOW
```

`reason_code` is the FIRST failing rule in Section 3 order (1→7); later failures
present in the same transaction are not reported.

### membership / encoding axes

`expected_labels` values are `[membership, encoding]`, two orthogonal axes:

- membership: `CLAIMS` | `IGNORED` — does the output claim the magic (Section 2)?
- encoding: `CANONICAL` | `NONCANONICAL` | `NOT_APPLICABLE` — `CANONICAL` is the
  byte-exact `0x6a 0x2b` + 43-byte payload; `NOT_APPLICABLE` accompanies
  `IGNORED`.

They are independent: an output can be `CLAIMS`+`CANONICAL` inside a MALFORMED
transaction (e.g. one of two canonical claimants). Outputs not listed in
`expected_labels` are `IGNORED` by convention.
