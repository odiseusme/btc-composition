# Composition Hand-off Specification: BtcTxCheck to Amount-Binding Parser

Status: DRAFT v3.1, 2026-07-13. Not frozen. v2 survived a three-reviewer
verification round; v3 applied the resulting fixes; v3.1 applies six
regression fixes from the Plan-review round (naming collision, C8
obligation naming, S2 clarifications, absent-key category
structure-dependence, 14.1 layer scope), the largest being the
marker deal-identity equality (C8), the cross-input rationale correction
(C1), the minSats enforcement locus (8.3), and failure-category
determinism (8.5). Written for review by both contributors before any
Scala implementation binds to it.

---

## 0. Status and pins

This document is true against exactly these sources. If any pin moves,
re-verify every claim in Sections 4, 5, 6, and 8 against the new head
before relying on this document.

| Source | Pin | Role |
|---|---|---|
| ergoplatform/sigmastate-interpreter PR #1182 | head `247b07e99` (on `3bdfa03e9`, `7a7c383dc`) | Producer: BtcTxCheck and relay. Each delta since `7a7c383dc` was diffed and touches relay internals only; zero seam-surface constructs changed (Section 10 rule applied) |
| ergoplatform/sigmastate-interpreter PR #1180 | head `aff008b` | Consumer: amount-binding parser |
| btc-composition `marker-grammar-DRAFT.md` | grammar v4, repo main `88d9435` | Payload layer: settlement marker, sigmastate-v1 profile |
| sigma core `CollsOverArrays.scala` at the pinned trees | lines 18, 40 | Verified `apply` and `slice` semantics (Section 8.3) |
| sigma `ContextExtension.scala` | line 19 | Verified per-input extension data (Section 6, C1 rationale) |
| sigma `ast/trees.scala` | BinAnd eval, line 1272 | Verified `&&` short-circuits; affects failure category, never acceptance (Section 8.5) |
| sigma `ast/methods.scala` | line 1755 | Verified `getVarFromInput` EXISTS at the pinned tree (protocol v6 Context method); C1's rationale is worded accordingly |
| sigma interpreter `CErgoTreeEvaluator.scala` | get_eval, lines 95 to 109 | Verified AvlTree.get semantics: incorrect proof throws; valid proof with absent key returns None (Section 8.5, V10 categories) |

Every byte-level and semantic claim below was read from these sources
directly, not reconstructed from memory or discussion.

## 1. Purpose, scope, and non-goals

Two reference contracts exist independently. BtcTxCheck (#1182) proves that
a Bitcoin transaction, presented as raw bytes, is included under a
relay-confirmed header with sufficient descendants. The amount-binding
parser (#1180) proves that a Bitcoin transaction, presented as raw bytes,
contains an output paying at least N satoshis to a committed script.
Neither claim is useful alone: an inclusion proof over unread bytes asserts
nothing about payment, and a parse of unauthenticated bytes asserts nothing
about reality.

The composed claim is: "a real, relay-confirmed Bitcoin transaction paid at
least N satoshis to the committed script." Assuming the pinned producer and
consumer are sound for their stated trust models, byte-for-byte identity
between the value the producer hashes and the value the consumer parses is
a NECESSARY invariant of that claim; it is not alone sufficient. Together
with the invariants of Section 6, the decoding model of Section 8, and the
assumptions of Section 9, it supports the composed claim. That identity is
the seam. It exists only when the two contracts compose, which is why it is
documented in neither PR. This document defines it.

**Each primitive is complete for its own trust model.** The parser with its
R4 txid commitment is a sound standalone primitive; BtcTxCheck is a sound
standalone inclusion verifier. Nothing here implies either is incomplete
outside composition. This document governs only their composition.

**Non-goals, stated up front so no reader expects them later.** This seam
does NOT provide, and this document does not claim: chronological freshness
(the marker binds the deal identity, but a box id exists at construction,
before confirmation, so binding the id rejects reuse and proves nothing
about ordering), a payment-height floor, one-live-deal-per-outpoint (a
formation question, pending design-authority ruling), relay freshness,
authenticated Merkle depth, or any deal lifecycle semantics. Every item in
this list appears in the exclusions table of Section 11.2, with tracking
pointers in Section 15.

**Out of scope entirely:** relay internals (#1182's relay contract, its
transition rules, its pending ABI compaction), the marker grammar's byte
rules (grammar v4 is normative for those; Section 8.6 pins the integration
points this document needs), and vault lifecycle composition.

## 2. Terminology

These terms are used in exactly these senses. The first is the most
important, because "verified" here deliberately means less than most
readers assume.

- **Authenticated bytes**: the `Coll[Byte]` obtained from context variable
  1 whose double-SHA256 equals a Merkle-proven leaf under a relay-confirmed
  header. Authentication is a property of the complete byte value through
  its hash. No byte is individually authenticated, and no content claim is
  made.
- **Verified inclusion**: BtcTxCheck's verdict. It means precisely: these
  bytes hash to a txid included under an authenticated header with at least
  six descendants. It does not mean the transaction was inspected, is
  recent, or is unique to this deal.
- **Producer**: BtcTxCheck, which authenticates the byte value.
- **Consumer**: the amount-binding parser, which interprets the byte value.
- **Policy conjunct**: an optional additional check added by an extended
  policy (see C6). A policy conjunct is neither producer nor consumer; it
  may only narrow acceptance.
- **The seam**: the point where trust crosses from authentication to
  interpretation: the shared byte value and the invariants that keep the
  hashed view and the parsed view equal in content and extent.
- **Composed predicate**: the spending condition of the composed box,
  satisfying Section 6 in a single input evaluation.
- **Canonical walk**: the single deterministic decoding pass over the byte
  value defined in Section 8.1. All output boundaries, indices, amounts,
  and script slices used anywhere in the composed predicate derive from
  this one walk.
- **Output descriptor**: the tuple (valueStart, scriptLenPos, scriptStart,
  scriptEnd, outputEnd) the canonical walk derives for each output.
- **markerOutputIndex**: the canonical-walk output index of the unique
  magic-claimant output identified by the marker scan (Section 8.6).
- **Profile / sigmastate-v1 profile**: the bounded transaction shape the
  on-chain contracts accept, consolidated in Section 8.2. In 7.1's
  reference shape, `profileOk` names the 8.2 conjunction and `walkOk`
  names "the 8.1 recurrence completes with every declared field in
  bounds"; neither is a new rule, both are labels.
- **Abstract grammar verdict vs profile verdict**: the marker grammar's
  two verdict layers. A vector can be abstractly VALID yet out of profile;
  on chain it must reduce to rejection regardless (C7).
- **Payload layer**: which payment semantics the composition uses. Two are
  defined: PLAIN (any-output amount binding, #1180 semantics minus the
  txid register) and MARKER (grammar v4 marker-bound, named-vout-only).
  Threat rows and fixtures are tagged with the layers they apply to; CORE
  means both.
- **Payment predicate**: the consumer-side assertion, per the active
  payload layer, that a qualifying output pays at least the committed
  minSats to the committed script. "Committed minSats" is the single
  canonical name for this value throughout (v2's `committedSats` was an
  alias and is retired).
- **Failure categories** (Section 8.5): CONTRACT-FALSE (predicate evaluates
  to false), EVAL-FAIL (interpreter evaluation throws and the spend is
  rejected), LOADER-REJECT (fixture loader refuses before execution),
  PROOF-FAIL (proof construction fails in the harness). On chain the first
  two both reject; fixture expectations follow the 8.5 rules, including
  the acceptable-rejection set for structure-dependent cases.

## 3. Architecture and trust boundary

Dependency direction, which is the architecture:

```
relay box (data input, singleton NFT, best-chain AVL state)
        |  authenticates header membership and tip height
        v
BtcTxCheck (producer)
        |  authenticates: doubleSha256(var 1 bytes) == Merkle-proven leaf
        v
authenticated byte value (context variable 1 of the composed input)
        |  interpretation, zero further authentication
        v
canonical walk (one decoding pass, Section 8.1)
        |  output descriptors shared by all consumers of the bytes
        v
payment predicate (PLAIN or MARKER layer)
```

Trust classification of every artifact crossing the seam:

| Artifact | Class | Authenticated by |
|---|---|---|
| Relay box state (R4 bestChain, R6 tipHeight) | Trusted via induction | Singleton NFT from correctly deployed genesis; BtcRelay preserves proposition and exact token vector through every successor (authenticity). BtcTxCheck's size==1 token check additionally rejects any vector-extended box (compatibility; the two properties are distinct, see T8) |
| Header record (headerAndHeight) | Authenticated | AVL lookup proof (var 3) against relay R4; its 88-byte shape is a relay-produced invariant inherited by induction, not re-checked by BtcTxCheck (Section 9) |
| Transaction bytes (var 1) | Authenticated as a complete value | doubleSha256 equality with the Merkle-proven leaf (var 4 fold vs header Merkle-root field) |
| Committed script hash, committed minSats, committed deal identity (MARKER) | Trusted commitments | Set at box creation by the deal committer; immutable |
| Every parsed offset, length, amount, script slice | Unauthenticated derivations | Trustworthy ONLY through byte-value identity (C2) plus the canonical walk (C9) |
| Marker payload fields (deal id, vout) | Unauthenticated derivations | Same, meaningful only inside the profile, only at the MARKER layer, and only through the C8 equalities |

The last two rows are the point of this document: nothing derived by
parsing carries independent authority. Its authority is entirely
derivative of the invariants in Section 6.

## 4. Producer surface: BtcTxCheck at 247b07e99

Read verbatim from the contract source at the pinned head.

**Context variables (resolved from the composed input's own context
extension):**

| Var | Type | Content |
|---|---|---|
| 1 | `Coll[Byte]` | Bitcoin transaction bytes. BtcTxCheck accepts any byte collection and authenticates whatever it hashes; the requirement that this be the stripped non-witness serialization is a composition convention enforced by the consumer profile (Section 8.2), not a producer check |
| 2 | `Coll[Byte]` | Header id, display byte order (Section 8.4) |
| 3 | `Coll[Byte]` | AVL lookup proof for the header id against relay R4 |
| 4 | `Coll[Coll[Byte]]` | Merkle proof: each element exactly 33 bytes; index 0 is the side flag (0 or 1); indices 1 to 32 are the 32-byte sibling hash, extracted as `slice(1, 33)` |

No registers are used by BtcTxCheck.

**Relay reads (via `CONTEXT.dataInputs(0)`):** the token vector must have
exactly one token with the relay NFT id and amount 1 (`properRelay`). The
token read is guarded in-contract (`if (tokens.size == 1) tokens(0) else
default`), so a relay with zero or many tokens produces CONTRACT-FALSE,
not EVAL-FAIL. R4 is the best-chain AvlTree; R6 the tip height (`Int`).
Absent or wrong-typed R4/R6, or an absent data input 0, are EVAL-FAIL
(`.get` on none / index out of bounds), subject to the 8.5
structure-dependence note.

**The three conjuncts, and nothing else:**

1. `properRelay`: as above. Authenticity is inductive from a correctly
   initialized genesis; the contract records this dependency in comments
   at both ends, deliberately, so neither side's check is "optimized away"
   without seeing the consequence.
2. `enoughConfs`: `(tipHeight - height) >= 6`, where
   `height = byteArrayToLong(headerAndHeight.slice(80, 88))` from the
   authenticated header record. Convention (this contract's terminology):
   six descendants after the containing header, which this project counts
   as seven conventional confirmations, one stricter than the folk six.
   The arithmetic domain is Section 8.3.
3. `properProof`: `proofShapeOk` (every element is 33 bytes with flag 0 or
   1) AND the Merkle fold seeded with `txId = doubleSha256(var 1 bytes)`,
   each level `doubleSha256(sibling ++ prev)` for flag 0 or
   `doubleSha256(prev ++ sibling)` for flag 1, equals
   `headerAndHeight.slice(36, 68)`. An EMPTY proof folds to `txId` itself
   and accepts only when the header's Merkle-root field equals the txid,
   which is consensus-correct for a single-transaction block; fixtures
   cover it (V11).

**What "verified" means and does not mean.** The verdict authenticates the
byte value through its hash and nothing else. BtcTxCheck never reads the
transaction's content: the contract's own comments state that amount and
recipient parsing is composed by the amount-binding parser, and spending
policy is supplied by the composing contract. No chronology claim, no
uniqueness claim, no content claim.

## 5. Consumer surface: the parser at aff008b

Read verbatim from the contract source at the pinned head.

**Inputs.** The transaction bytes from context variable 1. Registers on
the spending box, in the STANDALONE #1180 contract: R4 expected txid,
internal byte order, checked as `sha256(sha256(txBytes)) == expectedTxid`;
R5 the SHA-256 of an output scriptPubKey (32 bytes); R6 minimum satoshis
(`Long`), bounds-checked `0 <= minSats <= 2100000000000000`.

**Bounds differ by layer, deliberately, and both are pinned.** Standalone
#1180 permits `minSats == 0` in-contract. Compositions under this document
SHALL enforce, IN-CONTRACT, `0 < minSats <= 2100000000000000` (a
zero-minimum deal commits to nothing); violation is CONTRACT-FALSE
(Section 8.3). This is a per-layer difference between the pinned sources,
not a contradiction: the standalone bound is a fact of #1180; the strict
in-contract guard is normative for compositions.

**Shape preconditions** (consolidated with the rest of the profile in
Section 8.2): size at least 61 (derivation in 8.2); the 4 version bytes
are UNCONSTRAINED (read past, never validated); inputCount 1 or 2;
outputCount 1 to 4; every scriptSig and scriptPubKey length a single byte
below 0xfd; zero-length scriptSigs permitted (stripped SegWit inputs have
them); zero-length scriptPubKeys permitted on outputs that are not the
payment-matching output, while a payment-matching output (one whose script
hash is compared against the commitment) requires `scriptLen > 0` and a
nonempty committed preimage; stripped serialization only, with the
zero-input BIP144 ambiguity rejected fail-closed by the inputCount rule.

**The walk and the full-accounting rule.** One deterministic pass (exact
recurrence in Section 8.1) must account for every byte: everything before
the final four bytes belongs to version, counts, inputs, and outputs as
declared; the final four are reserved as locktime (read as extent, not
interpreted); `locktimeOk = outputsEnd == txBytes.size - 4`. This
establishes complete structural extent. It is normative as C4.

**Amount decoding, verified at source.** Little-endian, unsigned via byte
normalization. The guard `amountFitsBitcoinSupply` (byte 7 zero, byte 6 at
most 7) is checked BEFORE `readAmount` decodes bytes 0 to 6, so every
decoded amount is nonnegative, below 2^51, and free of Long overflow;
`amountOk` further requires `amount <= 2100000000000000 && amount >=
minSats`. Exact rules in Section 8.3.

**The slice-safety property, stated correctly.** The pinned contract
contains exactly one clamping operation: `txBytes.slice(scriptStart,
scriptStart + scriptLen)` inside `outputMatches`, hashed against the
committed script hash (whether the eventual COMPOSED contract adds further
slices, for example in the marker scan, is constrained by C5 and C9: any
added slice must be covered by the same theorem or locally
bounds-guarded). The safety property is NOT temporal ("the clamp never
executes"); under eager evaluation the slice may run and even hash before
another conjunct fails. The property is: **a clamped result cannot
contribute to an accepting verdict**, because on every accepting path the
complete walk and `locktimeOk` also hold, and the slice's upper bound
equals the walk's `outputEnd` for that output. In the pinned #1180 source
this equality holds by same-position determinism: `outputMatches` and the
walk both decode the script length as `readByte(start + 8)` on the
immutable byte value, two reads of one position yielding one value. The
premises and case analysis are the checkable theorem of Section 8.3; the
normative consequence is C5.

**What composition drops and keeps.** The txid register is DROPPED in the
base composition: the composed vault cannot know the txid in advance, and
Merkle inclusion under a relay-confirmed header supplies the txid binding
(policy statement and extension rule in C6). The committed script hash and
committed minSats are KEPT as the composed vault's commitments; their
exact register assignment in the composed box is a Section 14 decision.
At the MARKER layer the amount test applies to the marker-named output
only, and the marker's deal id must equal the committed deal identity
(C8).

## 6. The composition contract (NORMATIVE)

A composition claiming conformance with this seam SHALL satisfy all of the
following. This section is the document's center of gravity; everything
else is explanation, and Section 8 supplies the exact decoding rules these
invariants reference. Enforcement mapping: C1 via S1/S4, C2 via S1/S2 and
V1/V2, C3's testable clause via S3, C4 via V3, C5 via V4, C6 via S3, C7
via V5/V6, C8 via V8, C9 via S5/V9.

- **C1. Both verdicts, one evaluation, one byte value.** Acceptance SHALL
  imply both the producer verdict (Section 4's three conjuncts) and the
  consumer verdict (the active payload layer's payment predicate over the
  Section 8 decoding rules), evaluated in the same input evaluation over
  the byte value defined by C2. No Boolean structure of the predicate may
  permit acceptance without both (no disjunctive or conditional bypass;
  threat row T11). The source form is free: helper functions, nested
  conjunctions, and named intermediates are all conforming so long as
  acceptance implies both verdicts. Rationale, verified at source:
  context extensions are per-input (`ContextExtension.scala:19`) and
  provide NO AUTOMATIC identity relation between values supplied to
  different inputs. Cross-input reads DO exist at the pinned tree
  (`Context.getVarFromInput`, `methods.scala:1755`, a protocol v6 method), so a
  cross-input design could enforce byte equality explicitly, either by
  comparing another input's variable or through a shared register
  commitment. Such designs are sound in the protocol but are OUTSIDE this
  profile by choice: the single-predicate, single-input form is the
  simplest to audit, adds no equality machinery, and is what the
  reference implements. This profile does not rely on cross-input reads;
  a composition using them is a different seam.
- **C2. Byte-value identity, complete extent.** The composed predicate
  SHALL define one transaction-byte value, obtained from
  `getVar[Coll[Byte]](1)` resolved in the composed input's own context
  extension. The producer SHALL hash the complete byte sequence of that
  value, without normalization, transformation, or re-serialization. The
  consumer SHALL derive every parsed field from that same complete byte
  value via the canonical walk. Conformance is SEMANTIC: byte-for-byte
  equality and complete extent; runtime collection-object identity is NOT
  required (a byte-identical copy is cryptographically equivalent). The
  REFERENCE implementation binds the value once and passes it to both
  components, which is the simplest auditable construction; S1 verifies
  that mechanism in the reference, while conformance of other
  implementations is judged against the semantic rule. Within one
  evaluation the extension is immutable, so every resolution of variable
  1 yields the same value; the verdict SHALL be independent of every
  other input's extension (this profile makes no cross-input reads;
  tested metamorphically, S2).
- **C3. No independent txid source (testable clause).** The composed
  predicate SHALL NOT consult any txid source other than the
  double-SHA256 of the C2 value, except as a policy conjunct under C6's
  extension rule. Enforced by S3. Rationale, not separately testable:
  authority separation. The producer conjuncts carry no payment
  semantics; the consumer conjuncts carry no authentication; a policy
  conjunct may only narrow acceptance. The slogan "authentication
  precedes interpretation" describes the LOGICAL dependency only; Boolean
  evaluation order is free and short-circuiting affects failure category,
  never acceptance (8.5).
- **C4. Full accounting.** The canonical walk SHALL account for every
  byte of the C2 value: all bytes before the final four SHALL belong to
  the declared version, counts, inputs, and outputs; the final four SHALL
  be reserved as locktime; no bytes may remain unaccounted before or
  after that layout (`outputsEnd == txBytes.size - 4`). Prefix parsing
  and trailing bytes are non-conforming even where the txid equality
  would independently reject them (the rule keeps the consumer sound
  standalone and removes object-extent ambiguity). For degenerate tiny
  collections (size below the walk's first reads), rejection occurs as
  EVAL-FAIL or CONTRACT-FALSE depending on evaluation structure; the 8.5
  set rule applies.
- **C5. Bounds and arithmetic safety on accepting paths.** On every
  accepting path: all offset arithmetic SHALL be free of overflow and of
  negative or reversed ranges (guaranteed within the Section 8.3 domain);
  every indexed byte access SHALL be within bounds or the evaluation
  fails (EVAL-FAIL rejects); and for every output whose script hash can
  contribute to acceptance, `0 <= scriptStart <= scriptEnd <=
  txBytes.size - 4` SHALL hold. The pinned contract satisfies this via
  the derived mechanism proven in Section 8.3 (walk plus locktimeOk); a
  composed contract MAY strengthen it with local bounds guards, and any
  slice it ADDS must be covered by the 8.3 theorem or locally guarded.
  Weakening `locktimeOk`, decoupling any slice bound from the canonical
  walk, permitting arithmetic wraparound, or adding an uncovered clamping
  operation is seam-breaking.
- **C6. Txid commitment: base-profile drop, strict extension rule.** The
  base composition SHALL NOT require or consume a precommitted txid:
  inclusion supplies the txid binding, and a deal cannot know the
  transaction in advance (this is the functional reason for the drop; it
  is a profile decision, not a claim that a redundant commitment is
  unsafe). An extended policy MAY add a txid commitment ONLY as a POLICY
  CONJUNCT hashing the same C2 value; it SHALL NOT replace, bypass, or
  select between authentication mechanisms. Two checks that can each
  independently authenticate, where the implementation substitutes or
  selects between them, is the two-source defect class and is
  non-conforming; an additional conjunct over the same bytes can only
  narrow acceptance and is permitted.
- **C7. Profile supremacy on chain, scoped by layer.**
  Transaction-profile violations (Section 8.2) SHALL reject in BOTH
  payload layers. Marker-profile violations SHALL reject whenever the
  MARKER layer is active. The abstract marker-grammar verdict has no
  bearing on a PLAIN composition, which evaluates no marker. The contract
  stays fail-closed only: no witness classification and no diagnostic
  lists on chain (a rejection-only classifier would not be unsound, but
  it is excluded from this reference profile as complexity without
  strengthened acceptance).
- **C8. Marker binding at the MARKER layer.** Three requirements, all
  mandatory. (a) IDENTITY: the marker's parsed deal id SHALL equal the
  composed vault's committed deal identity. In the reference composition
  (no lifecycle successors) the committed deal identity IS `SELF.id`;
  where successors exist, it is the ORIGINATING deal box id carried in a
  register per 7.2, and the successor mechanism is lifecycle scope.
  Without this equality T10 is not resisted. (b) NAMED OUTPUT ONLY: the
  payment predicate SHALL apply to `outputs[vout]` and never any-output
  matching, with `0 <= vout < outputCount` (the ACTUAL decoded output
  count, not the profile capacity of four) and
  `vout != markerOutputIndex`. (c) DECODE DOMAIN: the vout field (uint32
  LE per grammar v4) SHALL be decoded from all four bytes, unsigned, into
  `Long`, and range-checked as a `Long` BEFORE any use; no cast to `Int`
  may precede the range check (a high-bytes-set encoding then fails the
  upper bound naturally, since outputCount is at most 4). The
  exactly-one-magic-claimant rule and candidate validity are grammar
  v4's, pinned through Section 8.6.
- **C9. One canonical walk, shared descriptors.** All components that
  interpret the C2 value (shape checks, marker scan, vout resolution,
  amount decoding, script hashing) SHALL use the same decoded output
  count and the same output descriptors derived by the single canonical
  walk of Section 8.1. No independent output walk, second parser, or
  separately computed index mapping may determine the named payment
  output or any other accepted fact. This applies to BOTH layers: in
  PLAIN, amount decoding and script hashing must use one descriptor set
  just as the marker scan must in MARKER. Byte identity (C2) does not by
  itself force interpretation identity; this invariant does, and it is
  what kills threat T12.

## 7. The composed predicate

**7.1 Boolean form (reference shape, non-normative source layout per
C1).**

```
sigmaProp(
  properRelay && enoughConfs && properProof     // producer, Section 4
  && profileOk && walkOk && locktimeOk          // labels per Section 2;
                                                // content is 8.1 + 8.2
  && paymentPredicate                           // active payload layer, 7.3
)
```

All conjuncts are mandatory on every accepting path; short-circuiting
changes failure category only (Section 8.5).

**7.2 Register, constant, and identity ownership.**

| Item | Owner | Notes |
|---|---|---|
| Relay NFT id | Composed contract constant | A deployed instance substitutes its real NFT id |
| minDescendants = 6 | Producer convention | This project's terminology counts it as seven conventional confirmations; do not silently relax |
| Committed script hash (single SHA-256 of scriptPubKey, 32 bytes) | Composing vault register | Semantics of #1180 R5; exact register index is a Section 14 decision |
| Committed minSats (`Long`, strict in-contract bound per 8.3) | Composing vault register | Semantics of #1180 R6; exact register index is a Section 14 decision |
| Committed deal identity (MARKER layer) | Composing vault, structural | Reference: `SELF.id`. With lifecycle successors: the ORIGINATING deal box id carried in a successor register, never a successor box's own id (a recreated box cannot keep its id); the successor mechanism itself is lifecycle scope and out of this document. C8(a) consumes this value |
| Context vars 1 to 4 | Spender supplies | Per Section 4 table |

The consumer adds NO context variables: the composed spend uses exactly
vars 1 to 4.

**7.3 Payload layers.** PLAIN: some output pays at least minSats to the
committed script (#1180 semantics minus the txid register), subject to C4,
C5, C9. This is the first-stage core vault predicate agreed between the
contributors. MARKER: grammar v4 marker-bound, named-vout-only, C8 plus
C9. The layers have different security properties: cross-deal payment
reuse is rejected at the MARKER layer ONLY (T10 is scoped accordingly);
the PLAIN layer does not resist it and says so. Which layer (or both) the
first Scala target implements is a Section 14 decision.

**7.4 Responsibility split.** Producer proves inclusion and confirmations;
the canonical walk derives descriptors, with the profile predicates
constraining counts and lengths and `locktimeOk` proving complete extent;
the payment predicate proves payment per layer; the composing vault
supplies commitments and policy; the spender supplies the four context
variables. No component checks another's homework, which is exactly why
C1, C2, and C9 must hold structurally.

## 8. Normative decoding and failure model

This section gives the exact rules the Section 6 invariants reference. A
harness implements against THIS section, not against prose.

**8.1 Canonical walk: offset recurrence.** All offsets zero-based into the
C2 value `txBytes`; `readByte(p)` is the unsigned value of `txBytes(p)`
(indexed access, EVAL-FAIL past the end); all lengths decoded unsigned
(therefore nonnegative, therefore offsets are monotonically
non-decreasing along the walk).

```
version        = bytes [0, 4)          // read past, unconstrained
inputCount     = readByte(4)           // must be 1 or 2
inputStart_1   = 5
// per input i at inputStart:
//   outpoint   = [inputStart, inputStart+36)
//   sigLenPos  = inputStart + 36
//   sigLen     = readByte(sigLenPos)      // < 0xfd; zero permitted
//   sigStart   = inputStart + 37
//   sequence   = [sigStart+sigLen, sigStart+sigLen+4)   // read past
//   inputEnd   = inputStart + 37 + sigLen + 4
inputsEnd      = inputEnd of the last input
outputCount    = readByte(inputsEnd)   // must be 1..4
outputStart_1  = inputsEnd + 1
// per output j at outputStart:
//   valueStart   = outputStart          // 8 bytes, little-endian
//   scriptLenPos = outputStart + 8
//   scriptLen    = readByte(scriptLenPos)   // < 0xfd; zero permitted,
//                                           // but a MATCHING output needs > 0
//   scriptStart  = outputStart + 9
//   scriptEnd    = scriptStart + scriptLen
//   outputEnd    = scriptEnd
outputsEnd     = outputEnd of the last output
locktime       = bytes [outputsEnd, outputsEnd+4)   // reserved, not interpreted
ACCEPT-EXTENT  : outputsEnd == txBytes.size - 4      (locktimeOk, C4)
```

The output descriptor of output j is (valueStart, scriptLenPos,
scriptStart, scriptEnd, outputEnd); C9 requires every consumer of the
bytes to use these descriptors and this outputCount.

**8.2 Consolidated transaction profile (sigmastate-v1).** Size at least
61 bytes. Derivation: the structural minimum under the recurrence (1
input, sigLen 0, 1 output, scriptLen 0) is 60 bytes, but no such
transaction can be ACCEPTED, because a payment-matching output requires
scriptLen at least 1; the accepted minimum is therefore 61, and the
precondition pins it. Version unconstrained. inputCount in {1, 2};
outputCount in [1, 4]; every sigLen and scriptLen a single byte, value
below 0xfd; zero-length scriptSigs permitted; zero-length scriptPubKeys
permitted on non-matching outputs; matching output requires scriptLen > 0
and a nonempty committed preimage; stripped non-witness serialization
only. The BIP144 ambiguity: a full witness serialization presents 0x00 at
the inputCount position and the {1, 2} rule rejects it, fail-closed; no
witness classifier exists on chain. There is NO explicit size-upper-bound
check; nevertheless no transaction longer than 1640 bytes can satisfy
both the bounded recurrence and `locktimeOk`, so accepted values are
bounded to 1640 (per input 37 + 252 + 4 = 293, two inputs 586; per output
9 + 252 = 261, four outputs 1044; 4 + 1 + 586 + 1 + 1044 + 4 = 1640),
which bounds every offset far below `Int` overflow (8.3). Widening the
profile re-opens the bound and is seam-breaking without a new derivation
(Section 10).

**8.3 Arithmetic domain, bounds, and the slice theorem.**

- Offsets and lengths are ErgoScript `Int`; amounts and minSats are
  `Long`; the marker vout decodes into `Long` (C8c).
- Domain bound: within the 8.2 profile every derived offset is at most
  1640, so offset arithmetic cannot overflow `Int`.
- Amount decoding: 8 bytes little-endian, unsigned per byte;
  `amountFitsBitcoinSupply` (byte 7 == 0 and byte 6 <= 7) is required
  BEFORE the 7-byte decode contributes, so every contributing amount is
  in [0, 2^51) with no `Long` overflow; acceptance further requires
  `amount <= 2100000000000000 && amount >= minSats`.
- minSats: standalone #1180 permits `minSats >= 0` in-contract.
  Compositions under this document SHALL enforce IN-CONTRACT
  `0 < minSats <= 2100000000000000` (exact integer, `Long`); a composed
  spend presenting minSats == 0 or above the supply is CONTRACT-FALSE.
  Deal formation SHOULD also refuse to create such a box, but the
  on-chain guard is the normative locus.
- Confirmation arithmetic: `height` is `Long`, decoded via
  `byteArrayToLong(headerAndHeight.slice(80, 88))` (big-endian 8-byte,
  relay-written); `tipHeight` is `Int`, promoted for the subtraction;
  `(tipHeight - height) >= 6`. Values are relay-produced under relay
  invariants (heights derive from the authenticated parent record as
  parentHeight + 1); overflow is unreachable for any realistic chain and
  the relay, not this seam, owns height sanity (Section 9).
- Verified access semantics: indexed access `apply` is raw array access
  (`CollsOverArrays.scala:18`), out-of-bounds throws, EVAL-FAIL,
  rejected; `slice` (`CollsOverArrays.scala:40`) delegates to Scala
  `Array.slice` and CLAMPS silently on out-of-range bounds.
- **Slice theorem.** Premises: (i) `scriptEnd = scriptStart + scriptLen`
  without overflow (domain bound above); (ii) `scriptEnd` equals the
  walk's `outputEnd` for that output (holds in the pinned source by
  same-position determinism, Section 5; holds in a composed contract by
  C9); (iii) all outputs declared by outputCount are walked; (iv)
  `locktimeOk` is mandatory on every accepting path; (v) exceptions
  reject and cannot be caught (ErgoTree has no exception handling); (vi)
  all decoded lengths are unsigned, so walk offsets are monotonically
  non-decreasing. Claim: a clamped slice result cannot contribute to an
  accepting verdict. A clamp requires `scriptEnd > txBytes.size`
  (scriptStart is at most size because `readByte(scriptLenPos)`
  succeeded). Cases: LAST output (including outputCount == 1):
  `outputsEnd = scriptEnd > size > size - 4`, locktimeOk false, (iv)
  blocks acceptance. INTERMEDIATE output: by (vi) the next output's
  `scriptLenPos` is at least `scriptEnd > size`, so its `readByte`
  throws, EVAL-FAIL by (v); independently the final extent equality
  cannot hold, by (vi) and (i). Boundary non-clamp cases, included for
  completeness: `scriptEnd == txBytes.size` (no clamp; locktimeOk false
  since size != size - 4); LAST output's script ending inside the
  locktime window, `size - 4 < scriptEnd <= size` (no clamp; locktimeOk
  false); an INTERMEDIATE output ending in that window rejects through
  the continued walk (later reads or the final extent), category per 8.5.
  A zero-length script with an out-of-range start cannot arise on an
  accepting path (matching outputs need scriptLen > 0, and non-matching
  scripts are never sliced in the pinned contract). Under eager
  evaluation the slice MAY execute and hash before another conjunct
  fails; that changes nothing about acceptance. Reordering mandatory
  conjuncts changes failure category and cost only, never the accepting
  set.

**8.4 Byte-order and hash-domain table.** One row per boundary;
"internal" = raw hash output, "display" = byte-reversed. Verified at the
pinned heads.

| Boundary | Function | Order | Note |
|---|---|---|---|
| txid seeding the Merkle fold | doubleSha256(var 1) | internal | Never reversed in-contract |
| Merkle sibling hashes (var 4, indices 1..32) | n/a (carried) | internal | Concatenation per side flag: flag 0 -> sibling ++ prev, flag 1 -> prev ++ sibling |
| Header Merkle-root field | headerAndHeight.slice(36, 68) | as serialized in the 80-byte header (internal) | Compared raw against the fold result |
| Header id (var 2, AVL keys) | reverse(doubleSha256(80-byte header)) | display | The one display-order value in the seam |
| Height field | headerAndHeight.slice(80, 88), byteArrayToLong | big-endian 8-byte | Relay-written record suffix layout |
| Committed script hash | sha256(scriptPubKey slice) | single SHA-256, no reversal | 32 bytes exactly; double-hash or reversal is a fixture bug the V10 vectors catch |
| Marker deal id (payload field) | n/a (carried, 32 bytes) | as written in the payload, compared raw against the committed deal identity | No reversal anywhere; grammar v4 owns the payload layout |
| Fixture hex loading | n/a | as written | Reversal happens at NO other boundary; a harness that logs display txids reverses at the logging boundary only |

**8.5 Failure model.** `&&` on Booleans compiles to BinAnd, verified
short-circuiting at source (`trees.scala:1272`); ErgoTree evaluation has
no exception handling, so any throw rejects the spend. AvlTree.get,
verified at source (`CErgoTreeEvaluator.scala:95`): an incorrect proof
THROWS; a valid proof with an absent key returns None, and the contract's
subsequent `.get` throws; both are EVAL-FAIL, at different sites.

Normalized categories:

| Condition | Category |
|---|---|
| Any mandatory conjunct false (relay checks, confirmations, proof mismatch, profile bounds, extent, payment, minSats guard) | CONTRACT-FALSE |
| Var 1 to 4 absent or wrong type (`.get` on none); data input 0 absent; indexed read past the end; malformed count driving reads out of bounds; AVL INCORRECT-PROOF (throws inside get, structure-invariant) | EVAL-FAIL |
| AVL valid proof with ABSENT key (None; the reference's `.get` throws, but an isDefined-guarded form returns false): structure-dependent per the determinism rule | {CONTRACT-FALSE, EVAL-FAIL} set |
| Relay token vector empty or oversized | CONTRACT-FALSE (guarded read, Section 4) |
| Fixture schema violations, hash-length violations, unknown profile name | LOADER-REJECT (harness, never on chain) |
| Unprovable spend during harness construction | PROOF-FAIL |

**Determinism rule.** Because Boolean order and val-binding style are
implementation-free (C1, Section 10), the category of SOME rejections is
structure-dependent: eager vals may throw (EVAL-FAIL) where a
short-circuited form returns false (CONTRACT-FALSE). Therefore: a fixture
SHALL declare either an exact category, where the category is invariant
across conforming structures, or the acceptable-rejection set
{CONTRACT-FALSE, EVAL-FAIL}, where it is not. Exact pins for
structure-dependent fixtures are finalized together with decision 14.4
(the reference's source organization). On chain both categories reject; a
category flip within a pinned fixture remains a behavior change this
document wants caught.

**8.6 Marker integration points (pins into grammar v4; MARKER layer
only).** The scan domain is output scriptPubKeys only, via the C9
descriptors, never arbitrary transaction bytes. A claimant is an output
whose script claims the protocol magic per the grammar's membership rules
(all four push encodings, physical presence, script-slice boundary).
Exactly one claimant must exist; `markerOutputIndex` is that claimant's
canonical-walk output index. The claimant must then pass version, both
network domains, exact length, and canonical-push validity, else reject
(a malformed same-magic output is a rejection, not an ignorable output).
Deal id: 32 bytes, compared raw for equality against the committed deal
identity per C8(a). vout: uint32 LE per the grammar, decoded per C8(c),
then range-checked per C8(b). The marker output's own value must be
exactly 0. The marker scanner obtains outputCount and every boundary from
the canonical walk (C9).

## 9. Assumptions and conventions ledger

Categorized, so later reviews can challenge each item on its own terms.

**Security assumptions (violations break the seam's trust story):**
- Correctly deployed relay genesis; NFT authenticity induction holds from
  there (relay transition rules preserve proposition and token vector).
- Bitcoin double-SHA256 collision resistance (the txid binds the byte
  value).
- The bestChain record shape (80-byte header ++ 8-byte big-endian height,
  88 bytes) is a relay-produced invariant. BtcTxCheck does NOT re-check
  the value length before slicing; it inherits the shape by induction. A
  relay defect writing malformed rows would be consumed (this mirrors the
  forward-only deployment note on the relay height fix).

**Protocol conventions (deliberate choices, changeable only by
revision):**
- Six descendants; this project's terminology counts seven conventional
  confirmations. The 5-vs-6 descendant boundary fixtures matter more than
  the label.
- Stripped non-witness serialization only; SegWit payments verify through
  their stripped txid preimage; full witness serialization rejected via
  the inputCount rule.
- Byte-order table of Section 8.4.

**Implementation constraints:** the consolidated profile of Section 8.2
and the arithmetic domain of Section 8.3.

**Interpreter-level facts (verified at pinned source):** indexed access
throws on out-of-bounds; slice clamps; context extensions are per-input;
within one evaluation every resolution of a context variable yields the
same value (evaluator property, exercised by S2's metamorphic runs);
cross-input reads exist via `getVarFromInput` (this profile does not use
them); BinAnd short-circuits; ErgoTree evaluation cannot catch
exceptions; AvlTree.get throws on incorrect proof and returns None on
absent key.

## 10. Compatibility contract

**The seam's compatibility surface** (wider than "ABI"): the four context
variable indices and types of Section 4 and their semantics; the register
SEMANTICS of 7.2 (indices are a Section 14 decision, then frozen); the
byte-order table of 8.4; the serialization form; the consolidated profile
of 8.2 and its arithmetic domain; the confirmation convention; the C8
identity and decode rules; and the normative invariants C1 to C9.

**Seam-breaking changes** (any requires a revision of this document and
re-verification of both sides): renumbering or retyping vars 1 to 4;
changing what var 1 contains; weakening full accounting (C4) or the C5
bounds property (removing locktimeOk, decoupling a slice bound from the
canonical walk, permitting wraparound, adding an uncovered clamping
operation); introducing a second walk or descriptor source (C9);
replacing, bypassing, or selecting between authentication sources (C6);
weakening the C8(a) deal-identity equality or the C8(b) named-vout binding (range check and marker-output inequality); relaxing the profile without re-deriving
the arithmetic domain bound and C7 handling; changing any row of the
byte-order table.

**Explicitly NOT seam-breaking, each verified by diff:** the `3bdfa03e9`
height-derivation fix and the `247b07e99` work-coherence follow-up change
the relay contract and tests only; the BtcTxCheck surface, header record
layout, and confirmation rule are untouched. The pending relay ABI
compaction (awaiting upstream #1155) remaps RELAY context variables only
(old 5 to 4, 6 to 5, 8 to 6, 9 to 7; retarget uses 6 and 7); BtcTxCheck's
vars 1 to 4, the entire seam surface, are untouched, and the consumer
adds no vars. Reordering mandatory conjuncts is not seam-breaking
(Section 8.3); it can flip structure-dependent failure categories, which
the 8.5 determinism rule absorbs, so it is harness-visible but not
security-relevant.

**Evolution note.** Widening the profile (more outputs, multi-byte
CompactSize), adding transaction classes (witness-aware parsing), or a
grammar v5 gets a new profile name, a re-derived arithmetic bound, and a
revision of this document; sigmastate-v1 compositions remain valid. A
change to the identity mechanism itself (C1/C2) is not an evolution of
this seam; it is a different seam and needs its own specification.

## 11. Threat traceability matrix

**11.1 Resisted threats.** Layer: CORE applies to both payload layers.

| ID | Layer | Attack | Invariant | Fixture / test (Section 12) |
|---|---|---|---|---|
| T1 | CORE | Prove one transaction, parse another (cross-input or cross-variable divergence) | C1, C2 | S1 structural, S2 metamorphic, V1 |
| T2 | CORE | Byte mutation after proof | C2 + txid equality | V2 |
| T3 | CORE | Trailing bytes / prefix parsing (extent ambiguity) | C4 | V3 |
| T4 | CORE | Declared length overruns; clamped slice hashes a truncated script | C5 (slice theorem 8.3) | V4 boundary classes |
| T5 | CORE | Authentication-source substitution or selection (txid commitment replacing inclusion) | C6 | S3 mutant |
| T6 | CORE | Out-of-profile transaction accepted because abstractly grammar-valid | C7 | V5 |
| T7 | CORE | Witness serialization smuggled via the zero-input ambiguity | Profile inputCount rule | V6 |
| T8 | CORE | Relay substitution (forged or token-mutated relay as data input) | properRelay; NFT authenticity by induction (a vector-extended successor is additionally rejected by the size==1 check: compatibility, distinct from authenticity) | V7 |
| T9 | MARKER | Any-output ghost: a non-named output satisfies the amount while the named one does not | C8(b) | V8 |
| T10 | MARKER | Cross-deal payment reuse (one qualifying output settles two deals with distinct deal ids) | C8(a) identity equality + C8(b) + grammar exactly-one rule. MARKER layer only; the PLAIN layer does not resist this and is documented as such | V8 |
| T11 | CORE | Boolean bypass: a branch permits acceptance without both verdicts | C1 | S4 mutant |
| T12 | CORE | Interpretation divergence: two components decode different output boundaries or indices from the same bytes (marker scan vs payment in MARKER; amount vs script descriptors in PLAIN) | C9 | S5 mutants + V9 |
| T13 | CORE | Byte-order or hash-domain confusion at any 8.4 boundary (fixtures validating a convention the contract does not use) | 8.4 table | V10 reversal-boundary vectors |
| T14 | CORE | Malformed Merkle proof shape (wrong element length, bad flag, truncated element); empty-proof semantics | properProof shape rule; empty proof accepts only when root == txid (consensus-correct) | V11 |
| T15 | CORE | Amount / bound edge cases (zero or over-supply minSats, high-bit amounts, over-supply amounts, LE reconstruction) | 8.3 rules incl. the in-contract minSats guard | V12 |
| T16 | CORE | ABI/index confusion (relay at wrong data-input index, swapped registers, wrong var index or type) | Section 4 tables + 8.5 categories | V13 |
| T17 | CORE | Confirmation boundary error (off-by-one at the descendant rule) | enoughConfs convention | V14 (5 vs 6 descendants, composed) |

**11.2 Explicit exclusions (no "killed by" row exists; do not infer
fixture coverage).**

| Excluded attack / gap | Status | Tracked |
|---|---|---|
| Stale-but-valid relay tip (understates confirmations; cannot fabricate them if relay state was valid) | Open by design: relay freshness | Section 15 |
| Chronological freshness / payment made before deal creation | Open: authenticated payment-height floor | Section 15 |
| Multiple live deals committed to the same Bitcoin outpoint (distinct from T10's payment reuse, which C8 kills at the MARKER layer) | Open: formation design, pending ruling | Section 15 |
| Deal lifecycle semantics (successor states, claim windows, deal-identity carriage mechanism) | Out of scope; paused pending ruling. C8(a)'s reference target `SELF.id` needs no lifecycle | Section 15 |
| Deep reorganization beyond the confirmation convention | Out of scope of any SPV design at this depth | n/a |
| Authenticated Merkle depth | Open follow-up design | Section 15 |

## 12. Fixture families and structural tests

Two kinds, deliberately separated. VECTOR families run real inputs
through the real composed predicate; STRUCTURAL tests (S) prove
properties no vector can, using mutants, source or IR inspection, and
metamorphic runs. Each entry names its threat rows; the matrix in 11.1 is
the master mapping. Each fixture SHALL declare its payload layer(s), its
intended failing conjunct (or positive), and its expected failure
category per the 8.5 determinism rule (exact category or the
{CONTRACT-FALSE, EVAL-FAIL} set; structure-dependent pins finalized with
decision 14.4).

**Isolation rule.** A negative fixture SHALL make every conjunct other
than the intended one valid BY CONSTRUCTION. For malformed-transaction
vectors this requires the harness to AUTHENTICATE the malformed bytes:
build a synthetic header whose Merkle-root field commits to the vector's
txid, a synthetic best-chain AVL state containing that header with
sufficient descendants, and a valid lookup proof. This generation
machinery is owned per decision 14.5. Reused primitive vectors
(#1180/#1182 suites, grammar v4's 63 vectors) are NOT automatically seam
fixtures: a reused vector must run through the composed predicate under
this isolation rule and declare which conjunct is intended to fail.

- **S1 (T1):** structural single-dataflow check on the REFERENCE
  implementation: its source (or compiled tree) binds the transaction
  bytes once, feeding both producer hash and canonical walk (the
  reference's chosen C2 mechanism; semantic conformance of other
  implementations is judged against C2 itself). Plus a NON-CONFORMING
  mutant (producer reads var 1, consumer reads var 5) demonstrating the
  A/B attack the rule prevents; the mutant is evidence, never a
  production vector.
- **S2 (T1):** metamorphic independence, exercising C2: Ergo spending
  transactions with multiple Ergo inputs (not multi-input Bitcoin
  transactions) where every OTHER input's extension is mutated arbitrarily
  while the composed input is held constant; verdict must not change.
- **S3 (T5):** mutant substituting a txid register check FOR properProof
  (non-conforming, accepts a non-included tx); plus the extended-policy
  positive: txid commitment added as a policy conjunct over the same
  bytes rejects mismatches and cannot bypass inclusion.
- **S4 (T11):** Boolean mutants (producer OR consumer; conditional
  bypass) shown to accept vectors the conforming predicate rejects.
- **S5 (T12):** divergent-walk mutants, one per layer: MARKER, a marker
  scan using its own output walk disagreeing with the payment walk's
  boundaries (named-vout misdirection); PLAIN, amount decoded from one
  descriptor derivation while the script hash uses an independently
  recomputed one.
- **V1 (T1):** shared-value positive: one valid value authenticated and
  parsed, both layers.
- **V2 (T2):** var-1 mutation with transaction A's proof retained;
  CONTRACT-FALSE at properProof.
- **V3 (T3):** trailing byte, truncated tail, extent mismatches, with
  the malformed bytes AUTHENTICATED per the isolation rule so that
  locktimeOk (or the walk) is the only failing element; category per
  8.5 (extent mismatch with a completed walk: CONTRACT-FALSE; walks
  whose reads run past the end: the {CONTRACT-FALSE, EVAL-FAIL} set).
- **V4 (T4):** boundary classes, each its own vector, authenticated per
  the isolation rule: last output with outputCount == 1 overrunning
  (CONTRACT-FALSE at locktimeOk); last output with outputCount > 1
  overrunning (CONTRACT-FALSE); intermediate output overrunning (the
  set: eager forms EVAL-FAIL, short-circuited forms may reach
  CONTRACT-FALSE); script end inside the locktime window, last output
  (no clamp, CONTRACT-FALSE); script end exactly at size - 4 (positive);
  script end exactly at size (CONTRACT-FALSE); maximal one-byte script
  length 0xfc.
- **V5 (T6):** out-of-profile abstract-VALID vectors reduce to rejection
  (reuses P6 / at-capacity N15 / N15d-N15e from the grammar set, run
  composed under the isolation rule).
- **V6 (T7):** full witness serialization; CONTRACT-FALSE at inputCount
  (byte 4 is 0x00).
- **V7 (T8):** wrong NFT id (CONTRACT-FALSE); wrong quantity
  (CONTRACT-FALSE); zero tokens (CONTRACT-FALSE, guarded read);
  token-vector-extended relay box (CONTRACT-FALSE at size==1).
- **V8 (T9, T10):** MARKER layer: grammar v4 marker families run
  composed under the isolation rule: deal-id mismatch (the C8(a)
  equality; the direct T10 discriminator), named-vout amount/script
  mismatch, vout == outputCount, vout == markerOutputIndex, vout with
  high bytes set (fails the Long range check, C8c), exactly-one
  violations, malformed same-magic, cross-deal two-vault
  one-marked-transaction.
- **V9 (T12):** vectors where a plausible SECOND walk would select a
  different output (crafted boundary layouts); the conforming
  predicate's verdict pins the canonical walk's interpretation. Layers:
  BOTH (marker misdirection in MARKER; descriptor divergence
  observability in PLAIN).
- **V10 (T13):** reversal-boundary vectors, categories per source
  verification: display-order txid fed as internal and inverse
  (CONTRACT-FALSE at properProof); reversed sibling (CONTRACT-FALSE at
  properProof); reversed Merkle-root comparison (CONTRACT-FALSE);
  reversed header id as AVL key (the {CONTRACT-FALSE, EVAL-FAIL} set:
  incorrect-proof resolution throws invariantly, absent-key resolution is
  structure-dependent; pinned exactly at 14.4); double-hashed or reversed
  script commitment (CONTRACT-FALSE at payment); reversed marker deal id
  (CONTRACT-FALSE at C8a, MARKER).
- **V11 (T14):** proof elements of length 32 and 34 (CONTRACT-FALSE at
  proofShapeOk), flag byte 2 (CONTRACT-FALSE), truncated element
  (CONTRACT-FALSE at shape), empty proof against a root == txid header
  (positive, consensus-correct) and against a normal header
  (CONTRACT-FALSE).
- **V12 (T15):** composed minSats == 0 (CONTRACT-FALSE at the 8.3
  in-contract guard) and minSats over supply (CONTRACT-FALSE); a
  SEPARATE loader-level schema case may also exist (LOADER-REJECT) but
  never replaces the contract-guard vector; amount with byte 7 nonzero
  (CONTRACT-FALSE at the supply guard), byte 6 == 8 (CONTRACT-FALSE),
  amount over supply (CONTRACT-FALSE), amount == minSats (positive
  boundary).
- **V13 (T16):** relay absent at data-input index 0 (EVAL-FAIL);
  impostor at index 0 WITH well-typed R4 AvlTree and R6 Int but the
  wrong NFT (CONTRACT-FALSE at properRelay); impostor WITHOUT well-typed
  R4/R6 (the {CONTRACT-FALSE, EVAL-FAIL} set: register reads may be
  eagerly bound); swapped commitment registers (category per 14.2's
  register-error decisions); var at wrong index or wrong var type
  (EVAL-FAIL).
- **V14 (T17):** exactly 5 descendants (CONTRACT-FALSE) and exactly 6
  (positive), composed variant of the producer's confirmation
  regression.

## 13. Scala integration requirements

Normative for any harness or loader binding this seam's fixtures:

- Require `schema_version == "2"` exactly; LOADER-REJECT otherwise.
- Read `profile_verdicts["sigmastate-v1"]` and
  `profile_violations["sigmastate-v1"]` explicitly, NO fallback to
  `grammar_verdict`.
- Decode `committed_script_hash` to exactly 32 bytes into the committed
  script-hash register; `committed_script` is construction provenance
  ONLY and never the committed value.
- Expected-result rule, exact formula: for a MARKER-layer fixture in
  which producer authentication, confirmations, commitments, and
  non-marker walk conditions are valid BY CONSTRUCTION (the isolation
  rule),
  `expectedMarkerAcceptance = grammar_verdict AND
  profile_verdicts["sigmastate-v1"]`.
  The whole-predicate expectation is NEVER derived from the grammar
  verdict alone; every fixture declares its own expectation per the 8.5
  determinism rule.
- Diagnostic classification (violation lists such as [3, 4]) lives in
  the loader and off-chain oracle only; the contract rejects, nothing
  more.
- Every fixture carries: unique id, payload layer(s), intended failing
  conjunct (or positive), expected failure category or set, and, for
  reused primitive vectors, how the isolation rule was satisfied.

## 14. Decisions required before the harness (joint, with the
collaborator)

Deliberately NOT pinned unilaterally by this document:

1. First Scala target: PLAIN layer, MARKER layer, or both as two named
   compiled contracts with two suites. Families and S-variants of a
   non-selected layer remain REQUIRED as specifications but their
   execution is deferred to that layer's target; the first harness is
   complete without them.
2. Exact composed-box register assignment for the committed script hash,
   committed minSats, and (MARKER) the committed deal identity where a
   register is used, including behavior for missing, wrong-typed, or
   extra registers (the 8.5 category for each).
3. Fixture-loader file layout and full schema (location, field names for
   relay/header/proof/tx, hex case rules, unknown-field behavior),
   extending the existing marker manifest schema v2.
4. Reference source organization: one compiled script or a thin
   conjunction over shared helpers (both conforming under C1). This
   decision FINALIZES the exact failure-category pins for
   structure-dependent fixtures (8.5).
5. Ownership and design of the fixture generation machinery required by
   the Section 12 isolation rule (synthetic header, best-chain AVL
   state, and lookup proof per vector). Candidate split, mirroring the
   existing division of labor: transaction-layer artifacts (tx bytes,
   markers, Merkle proofs over synthetic tx sets, expected verdicts)
   generated in the existing Python generator architecture;
   Ergo-side/AVL artifacts synthesized in the Scala harness.

## 15. Open-item tracking pointers

So no reader mistakes this document for claiming these solved:

- Chronological freshness / authenticated payment-height floor: open,
  checkpoint item with the design authority.
- One-live-deal-per-outpoint (formation; factory/registry branch): open,
  same checkpoint.
- Deal lifecycle (passive vs active claim, successors, deal-identity
  carriage mechanism referenced conditionally in 7.2 and C8a): paused
  pending the design authority's ruling; recommendation sent 2026-07-11.
- Relay freshness and authenticated Merkle depth: separate follow-up
  designs, explicitly not claimed by #1182.
- Marker grammar freeze: gated on the lifecycle ruling; ERGV magic final
  at freeze.
- Relay-side native-AVL and ABI compaction: complete locally, awaiting
  upstream #1155; verified not to cross the seam (Section 10).
