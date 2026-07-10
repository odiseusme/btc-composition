# DEAL-NFT FACTORY — proposal addendum to the v2 delta map (2026-07-10, rev 3 — final review absorbed, GO)

STATUS: PROPOSED formation structure, pending kushti. Three external review rounds absorbed; final review verdict: GO after fixes (applied). Does NOT rewrite the 33-invariant map as decided. Option A (minimal
reference) is ready to present as a fork; Option B (this factory) is a credible
design direction, not yet a fully shaped alternative.

WHAT IT ADDRESSES: the delta map left replay (#7) and buyer-identity (#20) at PARTIAL,
plus the open formation/authorization hole. All three involve formation-layer gaps (though cross-chain script ownership needs an
additional authorization/binding mechanism beyond factory provenance): nothing
enforces that a deal box is uniquely and legitimately formed. A CORRECTLY SPECIFIED canonical
factory could close that root and conditionally reclaim the two properties. (Not:
"flips them back to full" — reclaim is conditional on the mechanisms below.)

---

## The mechanism (consensus facts verified; inference marked)

Ergo consensus (EIP-4, node-enforced): a newly minted token's id equals the box id of
the minting tx's FIRST input; one new token id per transaction. Box ids are hashes of
contents+context; a box spends once. So a minted deal-NFT id is globally unique and
one-time. That is the verified bedrock. Everything the design INFERS from that
uniqueness is what the invariants below must pin.

**Proposed shape (explicit):** the factory state and the AVL registry reside in ONE
canonical singleton box. That box carries the pinned factory/registry NFT, is
INPUTS(0) for every mint, and is recreated under the full successor-continuity
invariant. (If ever split into two lineages instead, every mint must consume and
atomically recreate both, with identities bound so neither advances independently —
the combined box is cleaner for a reference.)

A **deal factory** is the only protocol-recognized way to create a deal box. eUTXO
accuracy: the off-chain builder proposes outputs; the factory input's contract
VALIDATES them. So the factory does not "write the fields" — it **requires the minting
transaction to create exactly one deal output whose proposition, registers, assets,
NFT, and committed terms satisfy the factory predicate.** The security question is
precisely which builder-controlled outputs the contract verifies.

At mint the factory must enforce (each TO SPECIFY at mechanism level):
1. **Minting-input identity**: the canonical factory state box is INPUTS(0), so the
   deal-NFT id derives from that exact box.
2. **Mint quantity and placement**: exactly one unit of the new token; exactly one
   deal output contains it; no other output carries that id.
3. **Atomic NFT+script+terms binding**: the deal-NFT is issued only inside the
   correctly-guarded deal box with the committed registers, in the same tx — no path
   issues it to a free box.
4. **Registry admission**: under the reference's permanent-retirement policy, minting
   fails if the canonical outpoint key already exists in the registry in ANY lifecycle
   state (LIVE, SETTLED, REFUNDED, CANCELLED). A future reusable-after-refund variant
   may admit only an explicitly released entry under its authenticated freshness rules.
   (Registry: AVL, same MutableAvl tooling as #1182.)

**Mint-time binding alone is NOT enough** (review 2): a token cannot leave a guarded
box unless that box's script permits it — so the deal contract must ALSO enforce
**deal-state continuity**: the deal-NFT cannot leave its canonical deal state except
through defined terminal branches, and any non-terminal successor preserves the NFT,
proposition, outpoint, buyer script, amount, asset, deadline, and all immutable terms
exactly. mint-time binding + custody/state-transition binding, both.

## The uniqueness model (four levels — all required, none substitutes for another)

    per-deal uniqueness      → deal-NFT (consensus)
    per-outpoint uniqueness  → registry (contract)
    term/identity binding    → registry entry ↔ NFT ↔ box ↔ authorized terms
    authority uniqueness     → canonical factory/registry LINEAGE

Level 3 (deal identity binding): the registry value must commit to at least the deal
NFT id, the outpoint, the deal proposition/version, a hash of the immutable terms, and
lifecycle status — else the registry proves an outpoint is reserved without proving
FOR WHICH deal. Level 4 (canonical authority): anyone can mint a unique NFT and call
its box "a registry"; deals must be rooted in THE protocol-pinned factory/registry
singleton (pinned NFT id, quantity one, expected proposition, AVL type/params,
network identity, upgrade/migration rules — including how old and new factory versions
avoid accepting the same outpoint concurrently). Without level 4 the protection is
registry-local, not global.

## Registry lifecycle (corrected — review 2 caught a genuine security defect)

A **settled outpoint must never be re-admitted**: its confirmed Bitcoin spending
transaction is permanent, reusable evidence, and a later deal admitting the same
outpoint could be settled by the historical spend. So:

    SETTLED   → permanently tombstoned. Never eligible again.
    REFUNDED/ CANCELLED (no settlement) → released ONLY under a fully specified
    authenticated payment-height-floor rule (the old spend provably older than the new
    deal's floor) — or, simpler and safe: never released either.

Policy choice for the spec: **simple policy = every committed outpoint permanently
retired after any deal closes** (recommended for a reference), vs. reusable-after-
refund only once the freshness mechanism exists. Consequence: payment freshness is NOT
independent of the factory if any reuse is allowed — the earlier claim of independence
was wrong.

Terminal transitions (settle / refund) and their registry updates must be **atomic in
one transaction**. The risk of non-atomicity is not box double-spend (consensus
prevents that) but **state desynchronization and premature reuse**: registry and deal
state diverging, a registry key released while a settlement-capable deal lives, a deal
closed without retiring its record, a replacement deal created against wrongly
released state, and settlement/refund transactions racing to consume the singleton
registry box.

## What is reclaimed — honest table (rev 2)

| Property | Verdict | Conditions |
|---|---|---|
| Replay (#7) | **CONDITIONALLY FULL — mechanism unproven** | requires ALL OF: one canonical factory/registry authority; one canonical outpoint-key encoding; under the reference policy, each outpoint key admitted only once ever; registry↔NFT↔terms binding; atomic mint/register; atomic terminal transition; permanent settlement tombstone; safe refund-release rule or none; authenticated height floor if release allowed. Until then: plausible solution, not a completed invariant |
| Buyer (#20) | **Buyer-authorized destination provenance — potentially reclaimable** | verifiable form: the factory tx must contain authorization under the buyer's committed Ergo proposition, binding the COMPLETE immutable term set. ("Buyer runs the mint" is not an enforceable condition — the chain cannot see who built a tx.) FULL buyer identity (Bitcoin-script ownership / cross-chain identity) is scope-dependent: expressible for a narrow script family (P2PKH/P2WPKH key-to-script derivation), complicated-to-impossible uniformly for multisig/P2SH/P2WSH/Taproot |
| Formation (open hole) | **STRUCTURAL FORMATION SOLVED IN DESIGN; PARTY AUTHORIZATION PENDING** | a factory proves protocol-admissible construction, NOT principal consent. Separate invariants required: (1) structural validity (factory-checked shape); (2) seller/asset-owner authorization binding the funder to exact terms; (3) buyer authorization with term continuity (terms authorized == terms written); (4) outpoint-owner authorization if required. Some may ride tx inputs guarded by party keys — but must be specified, not implied by "the factory authorizes it" |

## Consolidated invariant list (names; mechanisms TO SPECIFY)

1. Canonical factory/registry lineage (authority pinning + upgrade/migration rules)
2. Minting-input position and identity (factory state box = INPUTS(0))
3. Mint quantity and placement (one token unit, one deal output, nowhere else)
4. Atomic NFT+script+terms binding at mint
5. Deal-state/NFT custody continuity (no path moves the NFT into altered rules/terms;
   terminal branches must burn or irreversibly retire the deal-NFT under a defined
   rule — never transfer it into another settlement-capable deal state)
6. Registry admission/non-duplication — enforce the selected lifecycle policy: under
   the reference's permanent-retirement policy an outpoint key may be inserted once ever
7. Operation exclusivity and issuance discipline — every tx consuming the canonical
   state box (INPUTS(0)) is consensus-eligible to mint a token with that box's id, not
   only deal-creation. The script must classify each transition as exactly one
   operation (MINT / SETTLE / REFUND-CANCEL / UPGRADE-MIGRATE), mutually exclusive:
   only MINT may issue the first-input-derived deal token and it creates exactly one
   registered deal + one deal-NFT; terminal and maintenance operations mint no deal
   token and create no unregistered deal output; no settling-while-secretly-minting
   unless atomic batching is separately designed. (Most important previously-omitted
   invariant, final review.)
8. Registry–NFT–terms binding (deal identity binding, level 3 above)
9. Permanent settlement tombstone
10. Safe refund-release rule (or: never release)
11. Atomic terminal deal/registry transition (state-desync prevention)
12. Seller/asset-owner authorization
13. Buyer authorization with term continuity
14. Bitcoin network / relay domain binding (keys and deals bound to the intended
    network and relay authority — no cross-domain proof reuse)
15. Full registry successor continuity (preserve singleton id/quantity, proposition,
    AVL digest AND type params, immutable protocol fields, upgrade state — the #1182
    successor-proposition discipline, extended)
16. Canonical outpoint identity and encoding — registry keys use exactly the
    protocol-defined Bitcoin network/domain + 32-byte internal-order prev-txid +
    4-byte LE vout, fixed lengths, no alternative encoding of the same logical
    outpoint (network binding may live in the registry namespace, but the choice must
    be explicit)

## Honest costs (corrected)

- An extra contract plus a maintained singleton registry — real surface, real state.
- **All lifecycle operations serialize, not just minting**: every mint, settle, refund
  consumes the singleton registry box. Competing txs are not "last-write-wins" — one
  confirms, the others become invalid and must REBUILD against the new successor state
  (fresh AVL proofs, mempool races). Under load: settlement/refund latency, contention,
  and denial-of-service/liveness pressure. Mitigations (batching, request-box
  architecture) are production concerns a reference should name, not solve.
- The canonical factory/registry is a **protocol trust anchor**: its pinned identity,
  immutable rules, and bootstrap must be specified. If it is upgradeable or
  permissioned, the upgrade authority and administrator become ADDITIONAL trust
  assumptions — but an immutable autonomous deployment has no controller, so state
  which it is. Must be disclosed the way §6 states relay trust; authorization is
  relocated and named, not eliminated.
- Permanent registry growth under the tombstone policy (keys are never deleted), and
  off-chain AVL prover/state maintenance — a genuine ongoing cost, disclosed not
  blocking.
- Does NOT solve: payment-height floor (and is COUPLED to it via refund-release), reorg
  semantics, committed-outpoint viability at formation.

## The fork for kushti

- **(A) Minimal reference — ready now.** No factory. Replay and buyer-identity stay
  PARTIAL, documented as named limitations (one-live-deal-per-outpoint as an off-chain
  formation rule; destination immutable but unproven as the buyer's). Smallest
  reference; teaches the composition seam without formation machinery.
- **(B) Factory-backed reference — credible design direction, not yet fully shaped.**
  Conditionally reclaims replay and buyer-authorized-destination provenance and supplies
  structural formation — once the invariant list above is specified. NOT yet
  "copy-safe-to-production": even after the core mechanisms, seller authorization,
  authority migration, tombstone policy, state continuity, and freshness remain.

Recommendation to put to him: (A) if the reference's job is teaching the seam;
(B) as the named upgrade path, presented honestly as design-in-progress. His call,
like strict-vs-dynamic.

NEXT (reordered per final review GO): this document is now presentable to kushti AS
the fork — Option A ready, Option B honestly labeled a credible not-yet-specified
direction. Present the fork FIRST; run the worked mechanism pass (registry lifecycle
policy and canonical authority/lineage first, then custody continuity + atomic
binding) ONLY IF kushti picks B or wants it explored — no point specifying B's
machinery if the reference goes minimal.
