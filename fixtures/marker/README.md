# Settlement marker fixtures

Synthetic Bitcoin-transaction test vectors for the settlement **marker grammar**
(`marker-grammar-DRAFT.md`, revision v4). Each vector is a **stripped
(non-witness)** transaction serialization paired with the expected verdict of an
independent grammar oracle, so a marker-verifier implementation can be checked
byte-for-byte against the document.

63 vectors: the 61 grammar-layer cases, plus `N15d`/`N15e`, which pin the
**verifier-profile** boundary (Section 7). The 61 grammar-layer transactions are
byte-identical to their v3 serializations — v4 changed the payment ABI and added
a profile layer, but no payload byte moved.

## ⚠️ PRE-FREEZE

The grammar is **DRAFT — NOT FROZEN**; freeze is gated on the lifecycle
checkpoint. `status` is `PRE-FREEZE` throughout (manifest header, SUMMARY
banner, module constants). Do not treat these vectors or the byte layout as
final. Regenerate after any grammar change (see the gate below).

v4 **adopts the magic value `ERGV`** (Section 1) — it becomes final at freeze
together with the rest of the document; a later change is a protocol revision.

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
                         splice, dSHA256 txids, stripped-form parser, output
                         rebuilder)
    grammar.py           marker CONSTRUCTION constants + canonical builders
    verify.py            the INDEPENDENT oracle (own literals + own parser +
                         own Section 7 profile classifier)
    families.py          the 63-case registry (CASES: case_id -> CaseSpec)
    generate.py          the pipeline (gate, self-tests, verify, emit, prune)
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
  Every grammar-logical constant (magic bytes, offsets, lengths, net enums, the
  supply bound, **and the Section 7 profile bounds**) is **retranscribed as its
  own literal from the document**, each commented with its doc section — the
  profile bounds are *not* imported from `grammar.PROFILE_SIGMASTATE_V1`. It
  carries its own from-scratch stripped-form parser, plus a separate tolerant
  shape scanner for the profile layer. The retranscription is intentional
  redundancy: if grammar.py and verify.py ever disagree, a self-test fails.
  That claim is **enforced**, not merely asserted: generate.py cross-checks the
  two transcriptions on every run, so a disagreement in `SUPPLY_BOUND_SATS` or
  in any `PROFILE_SIGMASTATE_V1` bound is a build failure — the same check
  verify.py's self-test already applies to `REASON_CODES`.

families.py bridges the two (builds with grammar.py + txkit.py, expects
verify.py's outcome); generate.py replays the oracle over every case and refuses
to emit on any mismatch.

## Two verdict layers (grammar Section 7)

A fixture carries **two independent verdicts**, and conflating them is the whole
mistake Section 7 exists to prevent:

- **`grammar_verdict`** — protocol truth from Sections 2–3: `VALID` /
  `MALFORMED` / `NOT-A-SETTLEMENT`, computed with **no implementation bound**.
- **`profile_verdicts[P]`** — a *separate* layer for a named verifier profile
  `P`. It **equals** the grammar verdict when the transaction is IN PROFILE,
  and is otherwise `REJECT-OUT-OF-PROFILE`. Rejecting out of profile is
  fail-closed and always safe; **it is never a grammar result**.

The profile verdict **replaces**, it does not merge: `N15a` is grammar-MALFORMED
*and* `REJECT-OUT-OF-PROFILE`, and its profile column says only the latter. The
grammar verdict still carries `MALFORMED` in its own field. The layers stay
orthogonal.

The one profile defined today is **`sigmastate-v1`** (the composed-vault /
pre-committed-txid parser lane). A transaction is in profile iff **all** of:

| item | constraint |
|-----:|------------|
| 1 | stripped (non-witness) serialization only |
| 2 | `inputCount` in {1, 2} |
| 3 | `outputCount` in {1, 2, 3, 4} — scan capacity 4 |
| 4 | every CompactSize field is single-byte (`< 0xfd`) |

`profile_violations[P]` lists **every** violated item, as Section 7 item numbers
in the fixed document order 1–4 (empty when in profile) — so a transaction that
breaks several constraints records all of them, deterministically across
implementations. `P6`, `N15a`, `N15b` and `N15c` carry `[3, 4]`: their
257/300/301 output counts also force a multibyte CompactSize.

`vout` is **not** a profile constraint. Inside an in-profile transaction, rule 6
already requires `vout < outputCount`, so any `vout >= 4` there is necessarily
MALFORMED under rule 6 — not independently out of profile.

**The profile boundary is `N15d` vs `N15e`.** `N15e` is `N15d` plus exactly one
appended non-claiming output: same inputs, same marker index, same `vout`, same
named payment output, same scripts and values. `outputCount` 4→5 is the **only**
changed property, so a parser that accepts `N15d` and rejects `N15e` is
demonstrating its scan bound and nothing else. Both are grammar-VALID.

`P6` and the at-capacity `N15` member are **ABSTRACT-ONLY**: grammar positives
that this profile rejects. That is expected, not a contradiction.

## The payment ABI (Section 3 rule 7)

The deal commits **`committedScriptHash = SHA256(buyer scriptPubKey)`**, never
the raw script (register R4 in the vault contract, R5 in the pre-committed-txid
parser). The hash convention, exactly:

> a single SHA-256 over the raw scriptPubKey bytes exactly as they appear inside
> the output, with **NO** CompactSize length prefix, **NO** byte reversal, and
> **NO** second hash. Where the hash is carried as text (fixtures, manifests), it
> is exactly 64 lowercase hexadecimal characters representing the 32 raw bytes,
> decoded to bytes before comparison.

The predicate applied to `outputs[vout]` — **that output specifically**, never a
search over any output — is:

```
SHA256(outputs[vout].scriptPubKey) == committedScriptHash
AND outputs[vout].value >= committedSats
```

with hardened guards, all in **integer** arithmetic (never floating point):
non-empty `scriptPubKey`; `0 < committedSats <= 2_100_000_000_000_000` (the 21M
BTC supply bound in satoshi); `outputs[vout].value <= 2_100_000_000_000_000`.

Reason codes are unchanged — no new codes were invented. The mapping is by
domain: **`PAYMENT_SCRIPT_MISMATCH`** for script-domain failures only (empty
scriptPubKey, malformed committed-hash text, hash mismatch);
**`PAYMENT_AMOUNT_TOO_LOW`** for *all* amount-domain failures (committedSats
outside `(0, bound]`, output value above the bound, output value below
committedSats). Guards evaluate in that fixed order, so a transaction failing in
both domains at once reports the amount code first — deterministic, and no
fixture exercises it.

`deal_context.committed_script` is retained in the manifest as **construction
provenance only**; the oracle reads `committed_script_hash`.

## Stripped (non-witness) serialization only

The operative form is the **stripped (non-witness) serialization — the txid
preimage**. The correct term is "stripped/non-witness serialization only", *not*
"legacy-only".

**SegWit payments remain fully supported.** A transaction paying a SegWit output
is verifiable in this form like any other: the marker and the payment both live
in the stripped serialization. What is unsupported is the full **BIP144 witness
serialization** (marker `0x00` + nonzero flag after the version), which a parser
MUST **reject as unsupported rather than misparse** — misreading it as zero
inputs is the failure this rule prevents. Both parsers (txkit.py and verify.py,
independently) abort with a clear error on that form.

The Section 7 profile layer is the one place that does *not* abort on it:
`verify.classify_profile` **classifies** rather than rejecting, so a witness-form
transaction comes back as violation item `[1]` instead of raising. It uses its
own tolerant shape scanner, kept separate from the strict semantic parse path so
the strict path's rejection behavior is unchanged.

## The doc-hash gate

`generate.py` step 1 reads `marker-grammar-DRAFT.md` in **binary** (path resolved
from `__file__` to the repo root).

**CR check first.** If the file contains any `0x0D` byte it aborts with:

```
CRLF checkout detected — fix line endings, see .gitattributes
```

A CRLF checkout changes every line's bytes and so changes the digest; the gate
names that cause explicitly instead of reporting a bogus "doc changed". The
pinned hash is over **LF-only** bytes.

**Then the hash.** It compares the SHA-256 of those exact bytes to
`grammar.EXPECTED_GRAMMAR_SHA256`. On mismatch it aborts with:

```
grammar doc changed: re-review grammar.py and verify.py before regenerating
```

This forces a human to re-review both the construction constants and the
independently-transcribed oracle literals whenever the normative document
changes, instead of silently regenerating vectors against a moved target.

## LF policy

`.gitattributes` pins `*.md`, `*.hex`, `*.py` and `*.json` to `text eol=lf`.
Every generator write is explicit `newline="\n"` — no platform translation. Each
`.hex` file is lowercase hex, LF-only, with exactly one final newline.

## Regenerating

```
python3 fixtures/marker/gen/generate.py
```

The pipeline, in order: (1) doc gate (CR reject, then hash); (2) run
txkit/grammar/verify self-tests in-process; (3) build all cases; (4) replay the
oracle over each case — computed grammar_verdict, reason_code, and every declared
per-output label must equal the expectation, and claimant indices are derived
from the labels — and compute the Section 7 profile layer for every case,
asserting it where the case declares an expectation (`N15d`/`N15e`);
(5) coverage assertion (emitted set == the required 63); (6) determinism (build
twice in memory, byte-identical); (7) atomic emit; (8) stale-file prune;
(9) run report. Any failure aborts loudly.

**Atomicity is per file, not set-wide.** Each file is written to a temp path and
`os.replace`d, so no individual file is ever seen half-written — but the *set* is
not transactional. A crash midway through step 7 can leave the directory holding
a mix of old and new vectors. Re-run the generator; it is deterministic.

**Stale-file hygiene.** After the complete expected case set has generated **and
validated**, any `.hex` in `vectors/hex/` whose name is not in the case set is
**deleted**, and each deleted path is reported in the run output. Ordering is
normative: a failed run never deletes anything. This is what keeps a renamed or
dropped case from leaving an orphan vector behind.

Each module also runs standalone (`python3 .../txkit.py`, etc.) via its own
`self_test()`. verify.py's self-tests include the rule-7 hash predicate anchored
to independently-precomputed known-answer digests (never derived through the code
path under test) and the full Section 7 profile matrix.

## Manifest schema (`manifest.json`)

`schema_version` is **`"2"`** (v2 adds the profile layer and the payment-hash
ABI; every v1 field is retained). `json.dump(indent=2, sort_keys=True)`. No
timestamps anywhere.

### Header fields

| field | meaning |
|-------|---------|
| `schema_version` | `"2"` |
| `status` | `PRE-FREEZE` |
| `grammar_revision` | `v4` |
| `grammar_doc_sha256` | SHA-256 of the normative doc the vectors were built against (matches the gate constant; over LF-only bytes) |
| `donor.txid_display` | donor transaction id, Bitcoin display order |
| `donor.raw_sha256` | SHA-256 of the donor raw bytes |
| `deployment.ergo_net` / `deployment.btc_net` | the deployment network constants the oracle compared against (both `1` = mainnet here) |
| `assumed_scan_capacity` | the ABSTRACT layer's assumed output-scan bound (`300`); used only by `capacity_expectation`, never by the grammar verdict, and unrelated to any profile |
| `profiles` | **v2.** Map of profile name → its bounds (`min_inputs`, `max_inputs`, `min_outputs`, `max_outputs`, `compactsize_single_byte`, `stripped_only`) and `constraint_items`, the Section 7 items 1–4 keyed by item number |
| `semantics_note` | orthogonality of membership vs encoding; unlisted-are-IGNORED; reason_code is the FIRST failing rule |
| `profile_note` | **v2.** The two-verdict-layer model and the hash-committed-script ABI, stated in full |
| `synthetic_vector_warning` | the not-real-spends warning, verbatim |
| `vectors` | the per-case records, sorted by `case_id` |

### Per-vector record fields

| field | meaning |
|-------|---------|
| `case_id` | e.g. `P1a`, `N15e` |
| `family` | the taxonomy family (`P1`…`N15`) |
| `label` | one-line human description |
| `grammar_verdict` | `VALID` \| `MALFORMED` \| `NOT-A-SETTLEMENT` — the ABSTRACT layer (see split below) |
| `reason_code` | the FIRST failing Section 3 rule's code, or `null` when VALID |
| `profile_verdicts` | **v2.** Map profile name → the grammar verdict when in profile, else `REJECT-OUT-OF-PROFILE`. Keyed by name so future profiles are additive |
| `profile_violations` | **v2.** Map profile name → the ordered list of violated Section 7 item numbers (1–4), empty when in profile |
| `capacity_expectation` | `null` except N15c — the ABSTRACT capacity layer, unchanged from v1 and unrelated to `profile_*` |
| `expected_labels` | sparse map, `"index" -> [membership, encoding]`, listing only non-IGNORED outputs |
| `expected_claimant_indices` | output indices that CLAIM the magic (derived from the labels) |
| `deal_context` | the deal facts the oracle used: `expected_ergo_net`, `expected_btc_net`, `expected_vault_id` (hex), `committed_script_hash` (**v2**, 64 lowercase hex — what the oracle actually compares), `committed_script` (hex — construction provenance only), `committed_sats` |
| `notes` | construction / intent note |
| `txid_display` | vector txid, display order |
| `txid_internal` | `dSHA256(raw)` hex, UNREVERSED (internal order) |
| `hex_path` | `hex/{case_id}.hex`, relative to `vectors/` |
| `synthetic` | always `true` |

Note that `capacity_expectation` (abstract, capacity 300) and `profile_*`
(concrete, capacity 4) are **different layers** that happen to both concern
output counts. The first asks "what must a verifier of unknown capacity do?"; the
second asks "is this transaction eligible for *this named parser* at all?"

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
