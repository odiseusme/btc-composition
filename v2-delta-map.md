# OTC outline → parser-native v2 — DELTA MAP (2026-07-10)

Planning artifact, not the rewrite. Every §5 invariant marked against the
parser-native STRICT-fork design (kushti: buyer address fixed in vault; seller's
input/outpoint precommitted, "at most one transaction on the blockchain").
Legend: SURVIVES (carries into v2, possibly reworded) · DIES (no v2 counterpart) ·
MUTATES (principle survives, mechanism changes) · PENDING (blocked on an open answer).

| # | Invariant (v1) | Fate | v2 shape / reason |
|---|---|---|---|
| 1 | Signature validity | DIES* | no signed message. *May be reborn as formation authorization (seller sig at deal-box creation) — pending formation answer |
| 2 | Seller-key provenance | PENDING | only matters if formation uses a seller signature; else vault-structural |
| 3 | Field continuity (msg→registers) | MUTATES | source changes: creation-time commitments (outpoint, buyer script, amount, deadline) → registers; continuity principle unchanged |
| 4 | Canonical encoding defined | DIES* | no signed bytes to encode. *Reborn small if formation signs something |
| 5 | Encoding reproduced by signer | DIES* | same dependency as #4 |
| 6 | 255-bit response | DIES* | no Schnorr-in-script. *Only returns if formation uses explicit Schnorr rather than native proveDlog — prefer native, keep it dead |
| 7 | Replay | MUTATES / PARTIAL ★ | improved but NOT complete: precommitted outpoint + Bitcoin's double-spend rule stops one outpoint being spent twice on Bitcoin, and stops repeat settlement of a *single* consumed vault. It does NOT stop the same Bitcoin proof settling TWO deal boxes that committed the same outpoint (proof reuse across vaults). So one-live-deal-per-outpoint is the MISSING HALF of replay, not a side residue. v1's "target: contract" is partially reached: contract-bounded per vault, not globally contract-enforced. Global uniqueness needs a formation rule / factory / registry (pending) |
| 8 | Freshness window (msg) | MUTATES | message freshness dies; reborn as payment-height floor question: does the settlement tx have to confirm AFTER deal creation? (old-payment attack: seller commits an already-spent outpoint whose historical spend paid the buyer). Ties to Shannon Q6 relay-freshness-at-creation |
| 9 | Freshness clock + consistency | MUTATES | message-clock part dies; clock-domain consistency survives for the deadline |
| 10 | Deadline anchor | SURVIVES | 2-day/2-day still anchors to a contract-committed creation-time value |
| 11 | Timing-ordering (deadline adequacy) | SURVIVES | unchanged; exact semantics pending Q5 |
| 12 | Exit exclusivity | SURVIVES | relabel per Shannon: settlement path (not "cancellation") + buyer path |
| 13 | Post-deadline coexistence | PENDING | v1 said deliberate coexistence; kushti's "within 2 days / after 2 days buyer can claim" may CLOSE the seller branch at the deadline. Must be re-decided, not carried over (Shannon Q5) |
| 14 | Vault-bound asset sizing | SURVIVES | unchanged |
| 15 | Buyer-path output obligation | SURVIVES | unchanged |
| 16 | Seller-path output obligation | SURVIVES | renamed: settlement output obligation |
| 17 | Output anchoring | SURVIVES | unchanged |
| 18 | Authorization pinned (both branches) | SURVIVES | sharper: settlement is proof-authorized by construction |
| 19 | Funding (exact accounting) | SURVIVES | unchanged |
| 20 | Buyer-identity provenance | MUTATES / PARTIAL ★ | fixing the buyer script in the vault gives DESTINATION IMMUTABILITY (the settlement presenter cannot redirect payment), NOT buyer-identity provenance (that the committed script actually belongs to the intended buyer). The redirect hole closes on-chain; who authored the committed address, and whether the buyer inspected the authentic vault, remain formation + buyer-verification obligations (pending). Note: "buyer address" must mean a committed scriptPubKey or its hash, not a human-readable address string |
| 21 | Register consumption (per branch) | MUTATES | register set changes: committed outpoint replaces registered txid; buyer BTC script joins |
| 22 | Witness-stripped serialization | SURVIVES | unchanged |
| 23 | Amount + script-hash binding | SURVIVES | script is now the vault-fixed buyer address. v1's Q4 (script hash into tuple) DISSOLVED — no tuple exists |
| 24 | Txid derivation seam (same bytes) | MUTATES | seam survives (same bytes parsed AND hashed for the Merkle leaf); the equality target changes — see #25 |
| 25 | Txid equality (derived == registered) | DIES | no registered txid. Replaced by NEW invariant: spendsCommittedOutpoint (see below) |
| 26 | Txid representation continuity | SURVIVES+ | extended: the committed outpoint's prev-txid joins the internal-order-only rule (per outpoint fixture, 3e3ebb8) |
| 27 | Relay identity (NFT) | SURVIVES+ | plus Shannon hardening: successor must preserve relay proposition; pin quantity-one |
| 28 | Inclusion under relay | SURVIVES | unchanged |
| 29 | Best-chain meaning | SURVIVES+ | plus hardening list (work calc off-by-one, AVL metadata preservation) |
| 30 | Depth arithmetic + convention | SURVIVES+ | fix the 7-vs-6 (tip−h≥6 is seven conventional confirmations) |
| 31 | Confirmation-depth adequacy | SURVIVES | unchanged; coupled to deadline as before |
| 32 | 64-byte ambiguity guard | MUTATES | size!=64 is PARTIAL (Shannon: a real 64B tx in-block can act as an internal node to prove a different tx). Robust fix = authenticated depth/position (coinbase proof or chosen workaround) — its own scoped design task |
| 33 | Buyer verifies committed script is theirs | MUTATES | no tuple to inspect; buyer diligence moves to the DEAL BOX: verify vault registers (own BTC address, amount, seller's outpoint UNSPENT) before handing over cash |

## Born in v2 (no v1 counterpart)
- **spendsCommittedOutpoint** [contract] SPINE — presented tx's input (at the
  bounds-checked position var) matches the committed outpoint, internal order.
  Fixtures shipped (3e3ebb8).
- **One-live-deal-per-outpoint** [formation — locus pending] — Bitcoin prevents double
  SPEND, not double COMMITMENT; two live deal boxes could name one outpoint. Rule at
  formation, or factory. Raised with kushti, unanswered.
- **Formation / authorization** [pending kushti] — the signed message's second job
  (authorizing + gating deal-box creation, incl. deferred activation) has no
  replacement yet. Shannon's decision #1; the largest open hole.
- **Payment-height floor / relay freshness at creation** [pending] — Shannon Q6; only
  safe if the relay is synced at deal creation.

## Tally
17 survive (5 with hardening notes) · 5 die (4 conditionally, on the formation answer)
· 9 mutate (2 of them — replay #7 and buyer-identity #20 — improve but land as
PARTIAL, not completed on-chain wins) · 2 pending re-decision (coexistence; seller-key
provenance). Several "survive" fates (10, 11, 12, 18, 22, 25) carry qualifiers pending
the formation answer — see the pending correction pass for the full secondary downgrades.

## The v2 headline
kushti's simplification MATERIALLY NARROWS the v1 outline's two named limitations
(replay, buyer-identity) but does not fully close either. Replay: settlement is now
bound to one Bitcoin outpoint spend and a single vault can't re-settle, but one Bitcoin
proof can still settle two vaults that committed the same outpoint — global
one-settlement-per-outpoint needs a formation uniqueness rule. Buyer-identity: the
payment destination is now immutable (can't be redirected), but that the committed
script belongs to the intended buyer remains a formation + verification obligation.

So the honest statement: the strict parser-native fork removes the free-standing
settlement signature and binds every settlement to a vault-committed destination AND
outpoint, narrowing the replay and destination-substitution surfaces significantly. It
does NOT yet provide global one-settlement-per-outpoint or prove the committed
destination is the buyer's. Those depend on formation authorization, authenticated
creation-time freshness (payment-height floor), and duplicate-commitment prevention —
more than two open obligations, not "strictly better, pending two answers."
