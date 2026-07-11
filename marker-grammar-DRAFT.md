# Settlement Marker Grammar — DRAFT v3 (pending lifecycle checkpoint)

Status: DRAFT — NOT FROZEN. Freeze is gated on kushti's lifecycle confirmation.
Revision: v3, 2026-07-11 — second external adversarial pass on v2 found two
defects in v2's own fixes: (1) a logical contradiction in the truncation rule
(claiming without physically present magic bytes is impossible); (2) PUSHDATA4
length not required to decode unsigned, allowing a high-bit declared length to
escape membership through a signed intermediate. Both corrected here, plus
test-vector and taxonomy refinements. v2 history: full revision after the
first external round on v1 (PUSHDATA2/4 escape; PUSHDATA1 empty-push false
claimant; scan obligation; field underspecification). The payload layout is
unchanged since v1.
Scope: byte-level wire format of the settlement marker, plus the verifier
obligations without which the byte rules are bypassable. The marker's role in
the design (exactly-one claimant, originating-vault binding, namespace
fail-closed rule) is already adopted and restated only as far as the bytes
require. Chronological freshness (payment-height floor) is explicitly OUT OF
SCOPE — a separate open item; nothing in this grammar addresses it.

## 1. Wire format

The settlement Bitcoin transaction MUST contain exactly one marker output. The
canonical marker output is an OP_RETURN output, value exactly 0 satoshi, with
a single direct data push:

```
scriptPubKey (45 bytes total):
  0x6a                      OP_RETURN
  0x2b                      direct push of 43 bytes
  <43-byte payload>
```

As framed inside the serialized transaction (the parser walks this form):

```
TxOut:
  00 00 00 00 00 00 00 00   value = 0 satoshi, uint64 LE
  2d                        CompactSize script length = 45
  6a 2b <43-byte payload>   scriptPubKey
```

Payload layout (fixed offsets relative to payload start, total length 43):

| Offset | Size | Field    | Value / encoding                                      |
|-------:|-----:|----------|-------------------------------------------------------|
| 0      | 4    | magic    | ASCII "ERGV" = 0x45 0x52 0x47 0x56                    |
| 4      | 1    | version  | 0x01                                                   |
| 5      | 1    | ergo_net | 0x01 = Ergo mainnet, 0x02 = Ergo testnet; all other   |
|        |      |          | values malformed                                       |
| 6      | 1    | btc_net  | 0x01 = Bitcoin mainnet, 0x02 = Bitcoin Testnet4       |
|        |      |          | (BIP-94); all other values malformed. Testnet3,       |
|        |      |          | signet, regtest are unsupported in v1 of this grammar |
| 7      | 4    | vout     | index of the payment output, uint32 little-endian,    |
|        |      |          | decoded UNSIGNED (0x80000000+ must not go negative    |
|        |      |          | through a signed intermediate)                         |
| 11     | 32   | vault_id | originating vault box id, raw 32 bytes                 |

vault_id byte order: the 64-character box id as displayed by Ergo tooling is
hex-decoded directly, NO byte reversal (unlike Bitcoin txid display order).
Test vector: displayed id
`00112233445566778899aabbccddeeff00112233445566778899aabbccddeeff`
→ payload[11..42] = 00 11 22 33 44 55 66 77 88 99 aa bb cc dd ee ff
                    00 11 22 33 44 55 66 77 88 99 aa bb cc dd ee ff
(payload[11]=0x00 is the first displayed byte pair; no reversal at any point).

This document PINS the candidate layout sketched in fixture-inventory-
SCRATCH.md (M2 set, 66c6074). Deliberate differences from that sketch:
(a) paymentVout widened from 1 byte to uint32 LE — a 1-byte vout artificially
caps settlement transactions at 256 outputs; uint32 LE matches Bitcoin's
encoding of an output index in an outpoint (outputs do not serialize their own
index; the parser derives it from position); (b) scalar fields ordered before
the 32-byte vault_id so all small-field offsets are low and stable. Both
network domains from the sketch are retained.

Field rationale:

- **magic "ERGV"**: 4-byte ASCII follows the dominant convention (Omni's
  "omni"). No ERGx variant appears in the known OP_RETURN identifier surveys,
  so within the family the choice is taste plus one governance point.
  Candidates: ERGV (vault — what the payload names; recommended), ERGO (most
  readable and brand-aligned, but claiming the bare ecosystem name for one
  marker protocol is a namespace grab that should be kushti's call), ERGB,
  ERGS, ERGM, ERGX. [NEEDS CONFIRMATION: final magic value at freeze —
  technically equivalent, kushti/Shannon taste; ERGO specifically requires
  kushti's sign-off as a brand-word claim.]
  What the magic does and does not provide: it makes ACCIDENTAL collision
  unlikely (survey evidence, Section 5); it does NOT prevent INTENTIONAL
  collision — anyone can construct an ERGV OP_RETURN. That is acceptable
  because an intentional collision inside a settlement transaction causes
  settlement FAILURE, never unauthorized settlement, and the settlement
  transaction's creator (the seller) controls its own outputs.
- **version**: unknown version inside our namespace is MALFORMED, not "ignore
  and hope". A version bump requires a successor of this document.
- **ergo_net / btc_net**: domain separation on BOTH chains, so a marker minted
  for any test combination can never validate a mainnet deal and vice versa.
  The verifier compares each byte against its deployment constants; any
  mismatch or unlisted value is MALFORMED.
- **Fixed total length**: any in-namespace payload that is not exactly 43
  bytes is malformed by length alone — the cheapest possible test.
- **value == 0**: a CANONICALIZATION rule, not load-bearing for claimant
  uniqueness or vault binding; it exists to leave exactly one accepted byte
  form. Retained deliberately.

## 2. Namespace membership (what counts as "claiming the magic")

An output CLAIMS the magic iff ALL of:

1. Its scriptPubKey begins with OP_RETURN (script[0] == 0x6a).
2. The byte(s) at script[1..] form a data-push opcode in ANY of Bitcoin
   Script's four push encodings, with payload start P:
   - direct push: script[1] in 0x01..0x4b → P = 2
   - OP_PUSHDATA1: script[1] = 0x4c, 1-byte length at script[2] → P = 3
   - OP_PUSHDATA2: script[1] = 0x4d, 2-byte LE length at script[2..3] → P = 4
   - OP_PUSHDATA4: script[1] = 0x4e, 4-byte LE length at script[2..5] → P = 6
3. The DECODED declared push length is >= 4. PUSHDATA1/2/4 length fields are
   decoded as UNSIGNED little-endian integers; in particular a PUSHDATA4
   length with its high bit set (e.g. 0x80000004) MUST NOT become negative
   through a signed intermediate — that would let the claimant escape.
4. len(script) >= P + 4 AND script[P .. P+3] == magic. All four magic bytes
   must be physically present inside the script slice; if fewer than four
   physical payload bytes exist, the output does NOT claim — the magic cannot
   be established from bytes that are not there.
5. Truncation rule: if the four magic bytes ARE physically present (rule 4)
   but the declared push length extends beyond the physical end of the script
   slice (len(script) < P + declaredLength), the output CLAIMS and is
   malformed under Section 3. If no complete length field exists (incomplete
   PUSHDATA1/2/4 prefix), there is no decodable first push and the output
   does NOT claim.

SCRIPT SLICE BOUNDARY: "script" above means the exact scriptPubKey byte slice
delimited by the TxOut's outer CompactSize script length. Membership checks
MUST NOT read beyond that slice — bytes past it belong to the next
transaction field, not to this output.

DETECTION PROCEDURE (normative for bounded verifiers): claimant detection
never allocates or skips declaredLength bytes. It only (a) decodes enough of
the length field to establish declaredLength >= 4 as unsigned, (b) checks
four physical bytes exist inside the script slice at P, (c) compares them
with the magic.

FIRST-PUSH NAMESPACE RULE (explicit): magic occurring anywhere except the
beginning of the FIRST decoded push does NOT claim the namespace. An empty or
unrelated first push followed by a magic-bearing second push is ignored, as is
magic embedded in P2WSH/P2TR/witness data, in a script whose first byte is not
0x6a, or anywhere else outside the position defined above.

Membership is deliberately WIDER than validity: a same-magic output using
PUSHDATA1/2/4, or a wrong length, or trailing pushes, is still a claimant — it
is counted, and being non-canonical it is malformed, which fails the
settlement closed. This prevents an attacker from smuggling a second marker
past the exactly-one rule by re-encoding the push. What the membership rule
does NOT claim to catch is magic hidden outside the first push — that is
excluded by explicit policy (first-push rule), not by oversight.

Rationale for the length checks (rules 3-5): without them, `6a 4c 00
45524756` — a declared EMPTY push physically followed by the magic bytes —
would count as a claimant even though the magic is outside the push, and
`6a 4e 04 00 00 80 45524756` — a high-bit PUSHDATA4 length — would escape a
signed-arithmetic verifier. Unsigned decoding, decoded length >= 4, physical
presence, and magic-at-push-start jointly close both families.

## 3. Validity (all conditions required, else MALFORMED)

A settlement transaction is VALID with respect to the marker iff:

1. Exactly one output claims the magic (Section 2 count == 1), where the
   claimant scan covers EVERY transaction output. A bounded verifier MUST
   either scan all outputCount outputs or REJECT any transaction whose
   outputCount exceeds its scan capacity. A partial scan that accepts is a
   defect: it lets a second claimant hide beyond the bound. This is a
   normative requirement of the grammar, not an implementation detail.
2. That output's scriptPubKey is byte-exact canonical: 0x6a 0x2b + 43-byte
   payload (direct push only; PUSHDATA1/2/4 encodings of even a correct
   payload are malformed), AND the marker output's value is exactly 0 satoshi.
3. version == 0x01.
4. ergo_net AND btc_net each equal the verifier's expected constant for its
   deployment.
5. vault_id == the id of the originating vault of the deal being settled.
6. vout, decoded as unsigned uint32: vout < outputCount, vout !=
   markerOutputIndex, and outputCount was itself fully and successfully
   parsed from the transaction.
7. The output at index vout — outputs[vout] SPECIFICALLY — pays the committed
   buyer script AT LEAST the committed amount (value >= committedSats,
   matching the adopted pays-at-least predicate). The verifier MUST apply the
   payment predicate to outputs[vout] and MUST NOT fall back to searching any
   output for a match: "vout in range AND some output matches" is exactly the
   anyOutputMatches behavior this marker exists to eliminate.

Zero claimants: the transaction is simply not a settlement in our namespace —
it cannot settle any deal. Two or more claimants, or one non-canonical
claimant: MALFORMED — fail closed, the transaction settles nothing.

## 4. Negative taxonomy (fixture families, gated on freeze)

Positives:
- P1 canonical marker + qualifying payment at named vout (marker first,
  middle, and last output positions; payment before and after marker)
- P2 canonical marker + unrelated-prefix OP_RETURNs before and after (must be
  ignored, settlement valid)
- P3 two outputs qualify for payment, named vout is one of them (valid —
  naming disambiguates, duplicates elsewhere are irrelevant)
- P4 vout = outputCount - 1 (upper boundary, valid)
- P5 vout = 1 encoded 01 00 00 00 (LE encoding control), named output
  qualifies
- P6 vout = 256 encoded 00 01 00 00, transaction with 257+ outputs, within
  scan capacity (valid; if capacity is lower this becomes an N15 rejection,
  which is a scan-capacity result, not an encoding error)

Claimant-count and encoding negatives:
- N1 zero claimants (payment present, no marker)
- N2 two canonical claimants (same and different vault_ids)
- N3 same-magic non-canonical: wrong payload length (42, 44); declared 43 but
  truncated; declared 43 with a trailing byte or trailing second push
- N4 same-magic non-canonical push encodings: PUSHDATA1, PUSHDATA2, PUSHDATA4
  each carrying an otherwise-correct payload — alone (malformed claimant) and
  alongside a canonical marker (two claimants)
- N5 push-length semantics: PUSHDATA1 declared length 0/1/2/3 physically
  followed by magic — decoded length < 4, does NOT claim (ignored-family);
  declared length >= 4 with all four magic bytes physically present but the
  declared push extending beyond the script slice — CLAIMS, malformed;
  script slice ending before four magic bytes exist — does NOT claim;
  incomplete PUSHDATA1/2/4 length prefixes — no decodable push, does NOT
  claim; PUSHDATA4 length 0x80000004 with magic present — CLAIMS (unsigned
  decode), malformed
- N6 first-push rule: empty first push then magic-bearing second push
  (ignored); unrelated first push then magic second push (ignored); magic in
  P2WSH/P2TR outputs (ignored); script not starting 0x6a (ignored); near-miss
  magics ERGU/ERGW/ergv (ignored)

Field negatives:
- N7 unknown version (0x02) with all else correct
- N8 network: btc_net wrong; ergo_net wrong (each separately); unlisted enum
  values
- N9 vault_id: names a different vault (the payment-output-reuse
  counterexample in byte form — the M2 counterexample fixture anchors this
  family); one-byte mismatch; full byte reversal of the correct id
- N10 vout encoding errors: intended index 1 encoded big-endian
  (00 00 00 01), decoding to 16777216 and naming a wrong or out-of-range
  output
- N11 vout out of range: vout == outputCount; vout == markerOutputIndex;
  0xffffffff and other high-bit-set values decoded unsigned, out of range
  for any realistic transaction
- N12 nonzero value on an otherwise-canonical marker output

Indexed-payment negatives (rule 7):
- N13 marker names output i which FAILS the payment predicate while output j
  qualifies — MUST fail (the anyOutputMatches-fallback killer)
- N14 named output: right script, insufficient amount; sufficient amount,
  wrong script

Scan-bound negatives (rule 1):
- N15 second claimant at the LAST output of a many-output transaction;
  outputCount at the verifier's scan capacity (accepted) and capacity+1
  (rejected)

## 5. Collision and standardness analysis

- Known OP_RETURN identifier surveys (~50 identifiers; Omni "omni" and
  Counterparty "CNTRPRTY" dominant): no ERGx variant appears. This is
  evidence against ACCIDENTAL collision only; the intentional-collision model
  is stated in Section 1 (fail closed, seller controls the tx).
- Rosen Bridge lock transactions, narrow claim: at rosen-bridge/utils commit
  f432788a95b1943518e40d9f853a998bc4e2e157 (packages/rosen-extractor/lib/
  getRosenData/utils.ts, parseRosenData; const.ts, SUPPORTED_CHAINS), valid
  Rosen lock payloads begin with a chain-index byte currently in 0x00..0x09
  and therefore do not begin with 0x45; conversely a marker payload parses as
  invalid Rosen data (chain index 69 throws). Verified 2026-07-11 against
  that commit. This holds for the bitcoin, doge, and firo extractors (shared
  parser). It is a statement about that pinned implementation and index
  range, not a forever guarantee; re-verify if Rosen's chain registry grows
  past index 0x44.
- Runes (protocol form OP_RETURN OP_13, i.e. 0x6a 0x5d): 0x5d is not a data-
  push opcode, so a Runes output fails Section 2 rule 2 and never claims —
  disjoint at byte 1. Source: Runes protocol as implemented in ord; re-pin at
  freeze.
- Standardness: the canonical 45-byte scriptPubKey is far below both the
  historical 80-byte datacarrier default and current Bitcoin Core defaults
  (Core 30.0 raised the default cap dramatically and permits multiple data
  outputs in aggregate). Relay and mining acceptance are POLICY, not
  consensus, and node operators configure them differently; the grammar
  depends on consensus validity plus inclusion, never on relay policy.
  Note the corollary: since Core treats OP_RETURN followed by any push-only
  script as nulldata, PUSHDATA2/4 same-magic outputs are relayable in
  practice — which is exactly why Section 2 must count them.

## 6. Explicitly out of scope

- Chronological freshness / payment-height floor (separate open item).
- Lifecycle (D1/D2, Claim mechanics) — kushti's pending ruling. The marker
  BYTE LAYOUT is intended to remain unchanged across that ruling (the Claim
  carries vault_id unchanged); lifecycle safety — e.g. that the mechanics
  never create multiple independently spendable claim boxes bearing the same
  originating vault_id — remains separately dependent on the adopted Claim
  design and is not established by this grammar.
- Batching: one settlement tx per deal is a design rule. What the byte-level
  exactly-one-claimant rule itself enforces is narrower: a Bitcoin
  transaction can name at most ONE originating vault. The transaction may
  still contain unrelated outputs and payments (see P2, P3); it is not
  exclusively devoted to the settlement.
