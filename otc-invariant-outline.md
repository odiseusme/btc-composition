# Bitcoin On-Ramp OTC — Composition Invariant Outline

**Reference implementation of the published "Insuring a Bitcoin on-ramp with Ergo contracts" design.**

Status: DRAFT for review (Shannon → kushti checkpoint) · 2026-07-08 · repo: btc-composition

---

## Structural note (flagged for confirmation — see Q1, §7)

This outline is sequenced in **dependency order**: all seam primitives (the deal
message, freshness, the verified-payment inclusion proof) appear *before* the deal
paths that consume them. This differs from the narrative order of the original forum
design, where the inclusion proof lives *inside* the seller-cancellation path. The
reorder optimizes for a copier reading start-to-finish without holding a forward
reference. It is a deliberate trade — copier comprehension over prose-fidelity — and
is posed as a question rather than assumed. See Q1.

---

## 0. Purpose & scope

This is a minimal, safe-to-copy reference example: an ErgoScript test specification
showing how to compose a **verified Bitcoin payment** into an OTC deal that releases
an Ergo-side asset (a Bitcoin-backed token). It is a **reference the ecosystem copies
to learn the pattern**, not a production product.

Design stance: the composition **seam** — how a proven Bitcoin payment plugs into an
Ergo contract — is the subject. The deal is the thinnest wrapper that demonstrates it.

**Lifecycle in one sentence:** a fresh seller-signed deal message creates the deal
box; the box then has exactly two exits — delayed buyer withdrawal, or seller
cancellation on verified Bitcoin payment.

Invariants are tagged by **tier** — SPINE (the seam), THIN-SHELL (the minimal deal),
NAMED BOUNDARY (trust/scope) — and by **enforcement locus** — `[contract]`,
`[relay-protocol]`, or `[off-chain-tooling]`. The consolidated map is §5.

---

## 1. The deal message  · SPINE

The seller signs a message committing to the deal, using a Schnorr signature verified
on-chain.

**Contents (the signed tuple):** Bitcoin amount, Bitcoin transaction id, deal timestamp.
(The seller's public key is *not* in the tuple — it is the key the signature is verified
against; see key-provenance below.)

**Invariants:**

- **Signature validity** `[contract]` — the Schnorr proof verifies against the seller's
  public key (see key-provenance).
- **Seller-key provenance** `[contract]` — the verification key must be **inherited from
  the vault box**, not supplied freely when the deal box is created. Otherwise an
  attacker signs their own message with their own key and the check passes trivially.
  The key is carried from the vault into the deal box; the deal box is not an
  independent source of truth about the seller's key.
- **Field continuity** `[contract]` — the amount and txid from the signed message must be
  faithfully projected into the deal-box registers at creation. The timestamp must be
  consumed by the freshness rule and, if it anchors the withdrawal deadline, either
  carried into the box or used to derive a deadline that is carried into the box (§2).
- **Canonical encoding defined** `[contract]` — the contract must fix one unambiguous
  encoding of the signed bytes: field boundaries, amount units, txid byte order,
  timestamp representation, and a fixed domain-separation tag. Ambiguity here is a
  contract-side defect that can let a signature be accepted under an unintended
  interpretation.
- **Encoding reproduced** `[off-chain-tooling]` — the off-chain signer must serialize the
  message to match the contract's canonical encoding exactly. A mismatch produces
  signatures the contract rejects.
- **255-bit response (liveness obligation)** `[off-chain-tooling]` — the signature
  response must fit in 255 bits (the language's integer limit). A naive signer produces
  a fitting response only about half the time, so an implementation that omits nonce
  iteration does not fail cleanly — it works intermittently, passes casual testing, and
  fails in production on unlucky nonces. The signer must iterate the nonce until the
  response fits. This is the pattern's most common footgun.
- **Replay** `[off-chain-tooling]` *(target locus: contract; mechanism pending Q2)* — the
  same underlying Bitcoin payment must not be able to fund more than one Ergo-side asset
  release. The *requirement* is a fixed SPINE invariant. In **v1 this is not enforced
  on-chain**; the test setup assumes single use through off-chain coordination (as on the
  stage-1 vault, where the pre-committed txid register was dropped) — this is a **known
  limitation of the reference, not a recommended pattern**. A copier deploying beyond a
  demonstration must move this on-chain. The concrete mechanism (signed-message identity
  per the published design, vs. a fresh one-time Bitcoin address) is pending Q2 (§7). The
  precise identity of "the same payment" — whole txid, qualifying output, or unique
  destination — is also resolved in Q2.

---

## 2. Freshness  · SPINE (window/clock) + THIN-SHELL (deadline & timing)

A deal message is only admissible if it is recent. This bounds how long a signed
message can sit before it is used to create a deal box, limiting the window in which a
stale message is dangerous.

**Freshness is an admission condition, not a spend-time check** — it gates *creation*
of the deal box, not later spending. Once the box exists, its two exits are governed by
the deadline (§3), not by re-checking freshness.

**Freshness is not a replay defense.** It bounds exposure *duration*; it does not
prevent the same signed message or Bitcoin payment from being reused to create another
deal box from **another eligible vault state** (the originating vault box is consumed,
so literal resubmission of one creation transaction is impossible — the exposure is
reuse elsewhere). Replay is a separate invariant (§1) and is **not enforced on-chain in
v1**. A copier must not file replay as "handled by freshness." Given the v1 limitation,
this cross-reference is load-bearing.

**Invariants:**

- **Freshness window** `[contract]` · SPINE — the deal box may be created only if the
  message is neither older than the window (published design: ~4 hours) **nor dated too
  far in the future**. A one-sided window that only rejects old messages lets a seller
  post-date — which extends how long the message remains admissible beyond the intended
  window; the future-side check is what the bound actually defends against, not ritual.
  Checked once, at creation.
- **Freshness clock** `[contract]` · SPINE — the window is measured against the
  contract's own notion of time — either block `HEIGHT` or the pre-header timestamp
  (`CONTEXT.preHeader.timestamp`) — **not** the seller-asserted timestamp taken on its
  own. The seller's timestamp is an *input the seller controls*; judged purely against
  it, a seller could back- or post-date freely. The contract must bound the seller's
  timestamp against a native clock. *(Instrument choice is an implementation detail the
  spec must pin: the pre-header timestamp allows a direct timestamp comparison but is
  miner-influenceable within consensus bounds; HEIGHT is not a wall clock and requires a
  defined height-to-time approximation. Either way the invariant is that the seller's
  clock is not trusted unchecked.)* **Clock consistency:** the creation-time freshness
  check, the stored deadline, and the spend-time deadline comparison must all use the
  **same clock domain** — a height-derived deadline is later compared with `HEIGHT`, a
  timestamp deadline with the pre-header timestamp; heights and milliseconds are never
  mixed without an explicit conversion rule. The future-side tolerance must account for
  the chosen clock's own uncertainty (notably miner influence over the pre-header
  timestamp).
- **Deadline anchor** `[contract]` · THIN-SHELL — the withdrawal deadline (§3) is
  anchored to a contract-committed value fixed at creation (a native-clock value at
  creation, or a deadline derived from it and stored), **not** to the seller-asserted
  timestamp alone. This cashes the check §1 deferred here: the value the deadline is
  measured from must be one the seller cannot manipulate after the fact. *(Governs exit
  mechanics, so it serves §3; placed here because §1 deferred the anchor to freshness.)*
- **Timing-ordering (honest-seller liveness)** `[off-chain-tooling]` · THIN-SHELL — the
  deadline must leave enough time, after a deal is struck, for the named Bitcoin
  transaction to reach the required confirmation depth **and** for the seller to submit
  the cancellation proof. No finite deadline can *guarantee* this — Bitcoin confirmation
  time has an unbounded tail — so the spec must choose a **conservative operational
  bound** on confirmation delay and acknowledge the residual liveness risk explicitly.
  The relationship: `deadline > (chosen-conservative-confirmation-bound +
  proof-submission time)`, with margin — and the confirmation bound is a function of
  the required confirmation **depth**, a §4 parameter: if depth changes, this bound
  must be recalculated and the deadline retuned (§4, confirmation-depth adequacy). **Nothing on-chain enforces this ordering** — the
  contract runs with whatever deadline constant it was compiled with; a copier who
  tightens the constant "to protect the buyer" breaks the seller's cancellation path
  while ordinary validity-path tests may still pass and no contract condition is
  violated. That is why *this* invariant's locus is off-chain parameterization; the
  enforcement of the configured deadline itself is the `[contract]` deadline-anchor
  invariant above — the two bullets are the two halves of one mechanism. **The failure is asymmetric:** if Bitcoin confirms too
  slowly and the deadline passes, an honest seller has already paid the Bitcoin *and*
  loses the token — the buyer collects both sides of the deal. That asymmetry is why the
  conservative bound matters; it is not tuning advice. Exact values are a tuning
  decision; the *ordering relationship* is the invariant a copier must preserve.
  *(Note: only two durations appear here, not three. The freshness window drops out
  because the deadline anchors at box creation, not at signing — so the ≤4h gap between
  signing and creation never eats into the seller's cancellation time. This is a
  deliberate, useful property, not an omission.)*

---

## 3. The two spending paths  · THIN-SHELL

Once created, the deal box has **exactly two exits**. No other spending path exists or
is intended; a copier adding a third path (admin recovery, mutual-consent close) is
extending the design, not copying it.

**Path 1 — buyer withdrawal (after deadline).** If the deadline (anchored per §2) has
passed, the deal box may be spent to the committed buyer.

**Path 2 — seller cancellation (verified payment).** At any time before the box is
spent — **including after the deadline** — the box may be spent back to the seller by
proving the Bitcoin payment named in the signed message. The full proof predicate is
§4; this section defines only what the branch requires and must produce.

**Register provenance (who fixes what, at creation):**

- *From the signed message, per §1 field-continuity* `[contract]`: expected txid,
  expected Bitcoin amount, timestamp/deadline derivation.
- *From the vault box* `[contract]`: the seller payout proposition (either derived from
  the §1-inherited verification key or itself inherited from the vault — the spec must
  pin which; key provenance alone does not automatically provide a payout proposition),
  the token identity, and the token amount (see vault-bound asset sizing below).
- *Chosen by the creation-transaction builder* — exactly **one** field is freely chosen:
  the **buyer proposition** (see buyer-identity provenance below). §4's proof consumes
  an expected Bitcoin destination script **hash**; its provenance is currently unpinned — not in
  the signed tuple, not in the vault — and is resolved in §4.

**Invariants:**

- **Exit exclusivity** `[contract]` — the guarding proposition is exactly
  `(deadlinePassed && buyerOutputObligation) || (paymentProven && sellerOutputObligation)`
  — where each named obligation is the corresponding output invariant below, **not a
  signature**. There is no third disjunct.
- **Post-deadline coexistence (deliberate)** `[contract]` — the seller branch has **no
  upper time bound**: after the deadline both disjuncts are live and the first spend
  wins. This is intentional and seller-protective — a slow-confirming seller can still
  cancel if the buyer has not yet withdrawn. A copier who adds `&& !deadlinePassed` to
  the seller branch "for symmetry" removes the seller's recovery path entirely; the
  loss then occurs whenever the buyer exercises withdrawal.
- **Vault-bound asset sizing** `[contract]` — the token identity and token amount in
  the deal box are fixed by the **vault's spending condition** at creation, never by
  the creation-transaction builder: identity trivially (it is the vault's token),
  amount by a rule the seller committed to and the **contract computes** — a fixed
  per-deal size, or a deterministic calculation from the signed Bitcoin amount and a
  vault-committed rate. The contract must never merely accept a builder-supplied token
  amount that happens to be consistent with a rate; it computes the amount itself.
  Without this, a builder holding a signed message for a
  small payment can size the deal box with the entire vault balance, turning the
  seller's downside on a lost cancellation race from the deal's value into everything
  in the vault. The signed message binds the Bitcoin side; this invariant binds the
  token side.
- **Buyer-path output obligation** `[contract]` — the buyer branch must produce an
  output carrying the committed token identity and amount to the committed buyer
  proposition. Authorization is not enough: binding *who may spend* is not the same as
  binding *where the assets go* — without the output obligation, anyone satisfying the
  deadline condition could direct the tokens anywhere.
- **Seller-path output obligation** `[contract]` — the cancellation branch must return
  the committed token identity and amount to the committed seller proposition. Same
  principle: the branch states what it produces, not just who triggers it.
- **Output anchoring** `[contract]` — each output obligation must be anchored (e.g., a
  designated output index or a uniqueness condition) so it cannot be satisfied by an
  unrelated output while the guarded tokens leave through another. An obligation that
  merely says "some output pays the buyer" invites exactly that diversion.
- **Authorization source — both branches (must be pinned)** `[contract]` — **neither
  branch requires a signature in the formula above**: each is authorized by its
  condition (deadline / proof) plus its output obligation. Both are therefore
  permissionlessly triggerable — anyone, including a relayer, may submit the buyer's
  withdrawal after the deadline or the seller's cancellation proof; in each case the
  output obligation forces the tokens to the committed party, which makes permissionless
  triggering a feature, not a hole. The spec must pin the authorization choice
  **explicitly for each branch**; it must not silently imply signatures the contract
  doesn't require — a copier pinning one branch and assuming the other is
  signature-gated has misread the formula.
- **Funding (exact accounting)** `[contract]` — the deal box must contain **exactly**
  the committed token amount of the committed token identity, funded from the vault at
  creation, and the disposition of the box's ERG value and any surplus assets on each
  exit is stated **where the output obligations above are made concrete at spec time**
  — that is where this requirement is discharged; the §5 map points there. The output obligations bind register values; this
  invariant binds the box's real contents to them — and "at least" instead of "exactly"
  leaves any surplus legitimately divertible under the written obligations.
- **Buyer-identity provenance** `[off-chain-tooling]` *(named limitation; see Q3, §7;
  also disclosed at the trust boundary, §6)* — the buyer is **not in the signed
  tuple**, so whoever submits the creation transaction names the buyer: possession of
  the signed message is the ability to name yourself buyer. An interceptor can create
  the deal box with themselves as recipient, leaving the cash-paying buyer with nothing
  unless the seller wins the cancellation race. In v1 this is mitigated only off-chain
  (message confidentiality; the buyer submits promptly) — a **known limitation of the
  reference, not a recommended pattern**, same template as replay (§1). Whether the
  buyer should be added to the signed tuple is a design question for the published
  design's author (Q3, §7).
- **Register consumption (per branch)** `[contract]` — each branch consumes the
  committed fields relevant to *its* predicate and output obligation: the seller path
  consumes the expected txid and amount (fed to §4's proof) and the seller proposition;
  the buyer path consumes the stored deadline and the buyer proposition; both consume
  token identity and amount. The txid the seller must prove is the one **projected into
  the deal-box register at creation from the signed message** (the published design's
  txid-into-register mechanic) — the cancellation path proves *that* txid, never a txid
  supplied at spend time.
- **Asymmetric-loss restatement (why the deadline is not "just a parameter")** — if the
  named Bitcoin transaction confirms too slowly and the deadline passes, the buyer path
  opens while the seller has already paid the Bitcoin; if the buyer **wins the race**,
  the buyer collects both sides. This is the consequence the §2 timing-ordering
  invariant exists to prevent; it is restated here because this is the branch where the
  loss occurs.

**Dispute UX property (published design, informational):** the buyer can dispute
immediately (one Ergo transaction) or, given a large vault and some trust, postpone
(zero on-chain transactions). No trusted third parties resolve disputes. This is a
property of the two-path shape, not an additional mechanism.

---

## 4. Seller cancellation: the verified-payment seam  · SPINE

This is the section the reference exists to teach. "Verified payment" is not Merkle
inclusion alone — it is a **chain of cross-bindings**, every link of which is part of
the canonical pattern. A copier who preserves the parser and the relay proof but drops
one equality between them has an exploitable gap that looks like a working system.

**The chain, in order (all `[contract]` unless noted):**

1. **One raw Bitcoin transaction is supplied** (a single context variable). The bytes
   must be the **witness-stripped serialization** `[off-chain-tooling]` — hashing a
   witness-inclusive serialization yields the wtxid, not the txid — and it is the txid
   that appears as a leaf in the transaction Merkle tree whose **root** the block header
   commits to — so the proof fails after the Bitcoin is already paid (a liveness
   failure, not a safety one; the tooling must strip deterministically).
2. **The parser proves the payment**: some output of those bytes pays **at least the
   registered Bitcoin amount** (§3 register, from the signed message) to the
   **expected destination script hash** (provenance discussed below; pending Q4).
   *(At-least, not exact: overpayment must never invalidate the proof — contrast §3's
   exact Ergo-side token accounting; the asymmetry is deliberate.)*
3. **The txid is derived from those same bytes** — `doubleSha256(txBytes)`. Same
   context variable feeds steps 2 and 3; two validations, one transaction. This is the
   seam.
4. **The derived txid equals the registered txid** (§3: projected into the deal-box
   register at creation from the signed message — never supplied at spend time).
5. **That txid is proven included** under a header in the relay's authenticated
   best-chain state — relay box identified by its NFT, consumed as a **read-only data
   input**, header membership via the relay's authenticated tree, transaction
   membership via Bitcoin Merkle proof against that header.
6. **The confirmation depth is satisfied** — the header sits at least the required
   depth below the relay's tip. The spec must **pin both the terminology and the
   arithmetic**: Bitcoin's conventional "N confirmations" counts the inclusion block as
   confirmation one (`tip − inclusionHeight + 1 ≥ N`); `tip − inclusionHeight ≥ N` is a
   valid parameter only if deliberately defined as *descendant depth*, not
   confirmations. The two differ by one block, and off-by-one here is a classic quiet
   divergence between implementations.
7. **Only then** — as the thin-shell consequence — is the seller-cancellation branch
   enabled (§3's output obligation takes over from here).

**A structural consequence worth stating: the registered txid commits the entire
transaction.** A txid is the double-SHA256 of the full (witness-stripped) transaction,
so once step 4 holds, every output, script, and amount in the transaction was fixed at
the moment the seller signed. Step 2's checks are therefore checks on **what the
seller committed to**, made verifiable on-chain rather than left entirely to the
buyer's off-chain diligence.

**Destination-script provenance (resolving §3's IOU).** The expected script hash is in
neither the signed tuple nor the vault. Three candidate answers:

- *(a) Drop the on-chain script/amount check* — cancellation = txid equality +
  inclusion + depth only, and the buyer inspects the named transaction off-chain before
  accepting the deal message. Coherent, but it removes the amount-binding parser from
  the composition — the seam this reference exists to demonstrate.
- *(b) Builder-supplied at creation* — **unsafe**. The builder can commit a script the
  committed transaction does not pay, bricking the seller's cancellation after the
  Bitcoin is already sent — it converts the buyer-identity limitation (§3) into a
  griefing lever against the seller.
- *(c) Add the destination script hash to the signed tuple* — the seller commits to it;
  **contract-side provenance solved**: the builder cannot substitute the script, and the
  contract verifies the internal consistency of the seller's own claims. **Recommended —
  but it is not "self-certifying."** Nothing on-chain can know *whose* script the hash
  is: a seller could sign a tuple naming their **own** script, pay themselves, keep the
  cash, and cancel — the contract certifies a seller-to-seller payment just as happily.
  (c) therefore creates one explicit `[off-chain-tooling]` obligation on the **buyer**:
  verify, before handing over cash, that the script hash in the signed message is
  their own Bitcoin destination. (c) relocates that single act of diligence; it does
  not eliminate it. Two dependencies if (c) is adopted: the signed tuple grows, so §1's
  canonical-encoding, 255-bit, and field-continuity invariants apply to the extended
  tuple and must not silently drift; and this is a **blocking SPINE decision** — (b) is
  unsafe and (a) removes the very composition this reference demonstrates, so (c) is
  effectively required unless the design's author changes the reference's scope. **Q4,
  §7**, adjacent to Q3 (both gaps share one root: the signed tuple is thinner than the
  deal it binds).

**Relay-boundary invariants (imported, not re-derived here):**

- **Relay identity** `[contract]` — the data input must carry the expected relay NFT
  (a genuine quantity-one singleton); an arbitrary relay-shaped box must not satisfy
  the check.
- **Best-chain meaning** `[relay-protocol]` — that the relay's authenticated state
  reflects the actual Bitcoin best chain (reorg handling, tip integrity, freshness) is
  the relay's maintenance guarantee, **not** something this contract verifies. The
  contract checks membership against relay state; relay maintenance establishes what
  that state means. (Relay trust is disclosed at the boundary, §6.)
- **Depth arithmetic** `[contract]` — the depth comparison itself (header height vs.
  relay tip) is contract arithmetic; the *meaning* of the tip is the relay-protocol
  guarantee above. Two halves of one mechanism, same pattern as §2's deadline pair.
- **Confirmation-depth adequacy** `[off-chain-tooling]` — the required depth is a
  compiled-in constant nothing on-chain validates: the document's **second** off-chain
  parameterization invariant, paired with §2's timing-ordering. Lowering it "for
  faster deals" weakens reorg safety with no test failing; **raising it silently
  violates §2's timing-ordering**, because the chosen conservative confirmation-time
  bound must be recalculated upward when depth increases (the true worst case is
  unbounded, per §2) while the deadline was tuned for the old value. Depth and deadline are
  the document's one parameter pair where tightening one invariant loosens another —
  retune them together (§2).
- **Txid representation continuity** `[contract]` — the derived digest (step 3), the
  registered txid (step 4), and the Merkle-proof leaf (step 5) must all use the **exact
  32-byte output of `doubleSha256(witnessStrippedTxBytes)`, unchanged** — reversal is
  for human-facing display only and never enters the contract's comparisons. This is
  distinct from the signed tuple's encoding (§1): it is the consistency of one value
  across three uses inside the proof, and a single reversed comparison anywhere in the
  chain fails closed at best and, at worst, is "fixed" by a copier reversing the wrong
  side.
- **64-byte ambiguity guard** `[contract]` *(dependency disclosure)* — the underlying
  parser building block carries an explicit `txBytes.size != 64` guard against the
  known SPV internal-node/transaction ambiguity, with a dedicated regression fixture.
  This reference **inherits** that guard and does not re-derive it; a copier pulling
  the parser without its guard reopens the ambiguity. (See the parser's own
  documentation for the full analysis.)

---

## 5. Invariant map  · NAMED BOUNDARY

The consolidated ledger: one row per invariant, tier and enforcement locus stated
independently. **Locus is v1-honest** — it records where enforcement actually lives
today; where a target locus differs (pending an open question), the Notes column says
so. A copier diffing an implementation against this document diffs against this table.

| Invariant | § | Tier | Locus (v1) | Notes |
|---|---|---|---|---|
| Signature validity | 1 | SPINE | contract | |
| Seller-key provenance (from vault) | 1 | SPINE | contract | |
| Field continuity (msg → registers) | 1 | SPINE | contract | tuple may grow per Q4/Q3 |
| Canonical encoding defined | 1 | SPINE | contract | extends to grown tuple (Q4/Q3) |
| Encoding reproduced by signer | 1 | SPINE | off-chain-tooling | |
| 255-bit response (nonce iteration) | 1 | SPINE | off-chain-tooling | liveness footgun |
| Replay (one payment, one release) | 1 | SPINE | off-chain-tooling | **named limitation**; target: contract; pending Q2 |
| Freshness window (two-sided) | 2 | SPINE | contract | |
| Freshness clock + clock consistency | 2 | SPINE | contract | instrument choice pinned at spec time |
| Deadline anchor | 2 | THIN-SHELL | contract | |
| Timing-ordering (deadline adequacy) | 2 | THIN-SHELL | off-chain-tooling | parameterization; coupled to depth (§4) |
| Exit exclusivity (two disjuncts) | 3 | THIN-SHELL | contract | |
| Post-deadline coexistence | 3 | THIN-SHELL | contract | deliberate; do not add upper bound |
| Vault-bound asset sizing | 3 | THIN-SHELL | contract | contract computes amount |
| Buyer-path output obligation | 3 | THIN-SHELL | contract | anchored |
| Seller-path output obligation | 3 | THIN-SHELL | contract | anchored |
| Output anchoring | 3 | THIN-SHELL | contract | |
| Authorization pinned (both branches) | 3 | THIN-SHELL | contract | permissionless is a valid pin |
| Funding (exact accounting) | 3 | THIN-SHELL | contract | ERG/surplus disposition pinned at spec time |
| Buyer-identity provenance | 3 | THIN-SHELL | off-chain-tooling | **named limitation**; pending Q3 |
| Register consumption (per branch) | 3 | THIN-SHELL | contract | |
| Witness-stripped serialization | 4 | SPINE | off-chain-tooling | liveness; wtxid ≠ txid |
| Amount + script-hash binding | 4 | SPINE | contract | script-hash provenance pending Q4 |
| Txid derivation seam (same bytes) | 4 | SPINE | contract | the seam |
| Txid equality (derived = registered) | 4 | SPINE | contract | |
| Txid representation continuity | 4 | SPINE | contract | one byte order across three uses |
| Relay identity (NFT) | 4 | SPINE | contract | |
| Inclusion under relay (Merkle, step 5) | 4 | SPINE | contract | NFT-identified read-only data input |
| Best-chain meaning | 4 | SPINE | relay-protocol | trust disclosed in §6 |
| Depth arithmetic + convention | 4 | SPINE | contract | terminology pinned (confirmations vs depth) |
| Confirmation-depth adequacy | 4 | SPINE | off-chain-tooling | parameterization; coupled to deadline (§2) |
| 64-byte ambiguity guard | 4 | SPINE | contract | inherited from parser block |
| Buyer verifies committed script is theirs | 4 | THIN-SHELL | off-chain-tooling | deal semantics, not seam; exists only if Q4 → (c) |

Reading guide: every `off-chain-tooling` row is an obligation the contract **cannot
produce or guarantee** — but they fail differently. The encoding and serialization rows
fail *closed*: the contract rejects the malformed input (a liveness cost, caught
loudly). The **two parameterization rows** (timing-ordering, depth adequacy) and the
two **named limitations** (replay, buyer-identity) fail *silent* — nothing on-chain
catches the mistake — and deserve a copier's closest attention.

---

## 6. Deliberately out of scope  · NAMED BOUNDARY

What this reference does **not** do, stated as plainly as what it does:

- **No product mechanics** — no multi-party deals, order books, partial fills, batching,
  wallet UX, relayer operation, or dispute coordination beyond the two spending paths.
  The two-path shape *is* the dispute mechanism.
- **Relay governance and trust** — the relay is a **trusted component**. Who controls
  the relay NFT, how the relay state is updated, and what happens if the relay goes
  stale or malicious are outside this reference. The confirmation-depth check bounds
  *staleness of the proven header relative to the relay's tip*; it does **not** bound
  the relay's own trustworthiness or freshness. A copier must not read "trustless" into
  a design that verifiably contains a trusted relay.
- **On-chain replay enforcement** — pending Q2; v1's off-chain handling is a named
  limitation (§1), not a pattern.
- **On-chain buyer binding** — pending Q3; v1's off-chain handling is a named
  limitation (§3).
- **Bitcoin-side generality** — the parser building block accepts a **bounded
  transaction subset** (limited input/output counts, standard encodings). Payments
  outside the subset are valid on Bitcoin but **unprovable here** — the one boundary
  where an honest seller can lose funds by constructing a perfectly valid Bitcoin
  payment the proof then cannot cover. Constraining payment construction to the subset
  is a deal-formation obligation, not the contract's.
- **Bitcoin finality is probabilistic** — satisfying the configured confirmation depth
  reduces reorg risk; it does not prove irreversible finality. The depth is a chosen
  risk bound, not a finality proof.
- **Production hardening** — key management, message transport/confidentiality
  practices, monitoring, and recovery procedures are the deploying party's
  responsibility.
- **The token-sale stage** — OP_RETURN-based deal commitments belong to the next rung
  of the published ladder, not this reference.

---

## 7. Open questions  · for the design's author (and collaborator review first)

Ordered by precedence, not by section: **Q4 first because it blocks**, and because
Q4/Q3 together determine the signed tuple's final shape — on which §1's encoding and
field-continuity invariants depend (the 255-bit invariant itself holds regardless of
tuple fields; what changes with the tuple is the serializer, the signature fixtures,
and the resulting proof values). Q2 and Q3 are non-blocking limitations by comparison;
Q1 is presentation.

- **Q4 (blocking, SPINE): does the destination script hash join the signed tuple?**
  Recommended (option (c), §4): builder-supplied is unsafe, dropping the check removes
  the composition this reference demonstrates. Extends the published tuple — the
  author's call. If adopted: §1's encoding/continuity invariants extend to the grown
  tuple, and the buyer gains one explicit off-chain check (the committed script is
  their own).
- **Q3: does the buyer's identity join the signed tuple?** Same root as Q4 — the
  published tuple is thinner than the deal it binds. If not, buyer-identity remains a
  named v1 limitation (§3) mitigated by message confidentiality and prompt submission.
- **Q2a: which replay-identity mechanism?** Signed-message identity (per the published
  design) vs. a fresh one-time Bitcoin address; stronger on-chain options also exist
  (a claimed-outpoint registry consuming a singleton state box, or a factory-issued
  deal-NFT with deterministic script derivation). Which mechanism should the reference
  name as the target? The *requirement* (one payment, one release — §1) stands
  regardless.
- **Q2b: what precisely is "the same payment"?** Whole txid, a qualifying output, or a
  unique destination — the granularity Q2a's mechanism must bind.
- **Q1 (presentation): dependency order vs. narrative order.** This outline sequences
  seam primitives before the paths that consume them, deviating from the forum post's
  prose order (where inclusion lives inside the cancellation path) — a deliberate
  trade for copier comprehension, flagged in the structural note. Confirm or veto.
- **Q5 (adjacent, stage-1): retrofit boundary notes?** Should recipient-binding and
  payment-freshness — both handled here — be back-annotated into the stage-1 vault
  spec as explicit "what a real deployment must add" notes, or named only here?
- **Q6 (process): sequencing.** Does the author's own extraction branch exist, and
  does this stage build on it or on the in-review relay extraction?

**Spec-time pins (not author questions).** Four choices the body leaves open are
implementation decisions for the spec itself, listed here so they are not mistaken for
unresolved design questions: the freshness clock instrument and its tolerance (§2:
HEIGHT vs. pre-header timestamp); the seller payout proposition's derivation (§3:
derived from the inherited key vs. itself inherited); the confirmation
terminology/arithmetic convention (§4: confirmations vs. descendant depth); and the
vault token-sizing rule (§3: fixed per-deal amount vs. contract-computed rate formula).
