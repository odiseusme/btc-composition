# Plan: Composition Hand-off Lane, Spec to Shipped Seam Package

Status: DRAFT v2, 2026-07-13. Companion to composition-handoff-SPEC.md
v3.1 (the SPEC). v1 was reviewed by two independent reviewers; v2 applies
their convergent findings: a full coverage matrix, the reference-source
gate for structural tests, the construction-ordering problem for
deal-identity vectors, decision 14.5 pulled forward, a pilot-slice
integration gate, testable acceptance criteria, and an expanded risk
register. The SPEC defines WHAT the seam is; this Plan defines HOW the
lane's deliverables get built, reviewed, and handed over. Pipeline
position: Specify complete; this is the Plan stage; Tasks are derived
from the Section 3 coverage matrix and Section 4 workstreams after this
Plan is agreed.

## 1. Objective and deliverables

End state: the collaborator can begin the Scala composition harness
against a package whose completeness is verified by artifacts, not
assurances.

- **D1**: the SPEC, frozen at v1.0 (exact document hash recorded) after
  the collaborator's review and the Section 14 decisions.
- **D2**: the seam fixture package: transaction-layer artifact cores and
  final vectors per the Section 3 matrix, generated and independently
  oracle-verified in the existing generator architecture, plus a manifest
  satisfying SPEC Section 13 whose synthesis fields carry everything the
  harness needs per vector.
- **D3**: the structural-test package, two stages: SEMANTIC mutation
  specifications (the property, the mutation class, the discriminating
  vectors, expected verdict pairs) deliverable before any reference
  source exists; EXACT mutant sources (diffs against the committed
  conforming reference) deliverable only after the reference-source gate
  (Section 5). S2 is not a mutant test: its deliverable is an
  extension-mutation protocol with an invariance assertion, per the SPEC.
- **D4**: the harness-construction specification: exact recipes for the
  Ergo-side artifacts the harness synthesizes per vector: AVL key/value
  byte layout (88-byte record, display-order keys), relay-box registers
  and token vector, context-variable construction for vars 1 to 4,
  malformed-proof injection method, and descendant-count representation.
  This closes the gap between "manifest fields" and zero-guessing.
- **D5**: the verification and packaging artifacts: a machine-checkable
  traceability table (fixture and S-test ids keyed to SPEC 11.1 row ids;
  automated check fails on missing, duplicate, or unknown ids, or on any
  artifact claiming an 11.2 exclusion), the oracle report, regeneration
  hashes, and the handoff checklist of Section 8.

Out of scope for this lane (unchanged): vault lifecycle, relay
internals, marker grammar changes, anything gated on the design
authority's pending answer.

## 2. Inputs, dependencies, and gates

| Dependency | Blocks | Handling |
|---|---|---|
| SPEC v3.1 final pass (residuals list) | D1 freeze | Residuals travel WITH the SPEC to the collaborator; no further model round |
| Decision 14.5 (generation-machinery split + construction-ordering protocol for deal-identity vectors) | The largest share of W2; the W2a at-risk boundary | PULLED FORWARD: asked first, alone, before the batched 14.1 to 14.4, because it is cheap to answer and gates the most work |
| Decisions 14.1 to 14.4 | W2b finalization; exact S-test sources; category pins | Sent with D1 as one decision list |
| Committed conforming reference source (collaborator, post-14.4) | D3 stage 2 (exact mutants) | Reference-source gate, Section 5 |
| Design authority's pending answer | Nothing in this lane; may REPRIORITIZE it | Re-plan explicitly if it lands mid-lane |
| Upstream #1155 / relay native-AVL | Nothing here (verified not to cross the seam) | Watch only |
| Grammar v4 freeze | Blocks nothing, but the ERGV magic is final only at freeze and W2a marker vectors physically embed it | Priced as risk R5; regeneration path kept cheap |

Pin-check schedule (not a norm, a scheduled task): verify both PR heads
and the grammar-doc hash at three points: lane start, before W2a
generation begins, before handoff. Generation is BLOCKED on manifest
pin-hash mismatch; movement triggers the SPEC Section 0 re-verification
of the seam surface before anything continues.

## 3. Coverage matrix

Phases: **W2a** = decision-independent transaction-layer artifact cores
(start immediately, explicitly AT-RISK pending 14.5; artifacts designed
separable so either 14.5 outcome consumes them). **W2b** =
decision-dependent finalization (categories, register fields, loader
cases, manifest schema fields). **H** = harness-synthesized per D4
recipe and manifest synthesis fields. **Sem/Exact** = D3's two stages.
Layer scope of MARKER-only entries follows decision 14.1 per the SPEC's
deferral rule.

| Family | W2a core | W2b / H | Gates | Notes |
|---|---|---|---|---|
| V1 PLAIN positive | yes | categories W2b | 14.3 | |
| V1 MARKER positive | NO | W2b + H | 14.5 protocol, 14.1 | Deal-id-dependent: payload embeds the box id, txid commits payload, proof commits txid; generation order is 14.5 material |
| V2 | yes | | 14.3 manifest | Depends on SPEC Section 4 proof rules |
| V3 | yes | category pins W2b | 14.4 | Ships with {CONTRACT-FALSE, EVAL-FAIL} set until pinned |
| V4 | yes | category pins W2b | 14.4 | Same |
| V5 | yes (mapping) | scope W2b | 14.1; magic churn R5 | Reuses grammar vectors under the isolation rule |
| V6 | yes | | | |
| V7 | NO | H | D4 | Relay-box mutations are Ergo-side by nature |
| V8 deal-id-AGNOSTIC subset (exactly-one, malformed same-magic, vout range) | yes | | 14.1 | Depends on C8/8.6 |
| V8 IDENTITY subset (C8a equality + controlled near-miss) | NO | W2b + H | 14.5 protocol, 14.1, 14.2 if register-backed | Same construction-ordering problem as V1 MARKER |
| V9 | yes (crafted layouts) | | 14.1 for layer tags | |
| V10 tx-layer reversals (txid, sibling, root, script hash, deal id) | yes | | | |
| V10 AVL-key reversal | NO | H | D4 | Category is the set per SPEC 8.5/v3.1 |
| V11 | yes | | | Depends on Section 4 proof rules |
| V12 amount cases | yes | minSats representation + loader case W2b | 14.2, 14.3 | |
| V13 | NO | W2b + H | 14.2, D4 | Register-error categories are 14.2 material |
| V14 tx-layer | yes | relay state H | D4 | Confirmation convention per Section 4 |
| S1 | Sem | Exact | ref-source gate | Inspection mechanism per 14.4 |
| S2 | protocol (full) | | none | Invariance test, NOT a mutant; substantially decision-independent |
| S3 | Sem | Exact | ref-source gate, 14.2 | Positive variant names a register |
| S4 | Sem | Exact | ref-source gate | |
| S5 both layer variants | Sem | Exact | ref-source gate, 14.1 | |

The W2a dependency basis is per-family as noted (Sections 4, 8.1 to
8.3, 8.6, C8 of the SPEC), not a blanket claim.

## 4. Workstreams

**W1: SPEC finalization.** Send the SPEC v3.1 + the residuals list + the
Section 14 decision list (14.5 first and separate). Incorporate the
collaborator's review. FREEZE ORDER: decisions and review comments land,
are incorporated, the exact SPEC hash is frozen as v1.0, and ONLY THEN
are decision-dependent fixtures and exact mutants finalized against that
hash. Post-freeze changes follow the SPEC's Section 10 compatibility
contract.

**W2: Fixture package.** Owner: this side, existing generator
architecture (generator + independent oracle, doc-hash gated, LF-forced,
stdlib only), fixtures/seam/. Scope per the matrix. Acceptance per
Section 8, including SPEC Section 13 conformance (schema_version,
profile-verdict fields, per-fixture metadata), not merely "schema
versioned."

**W3: Structural-test package.** Owner: this side SPECIFIES, the
collaborator RUNS. Two stages per D3. Exact sources for S1 and S3 to S5
are diffs against the committed reference and are gated accordingly; no
exact mutant is authored against an assumed source shape.

**W4: Review machinery (continuous).** Multi-model loop per artifact;
findings triaged with pushback; presented first-person. One review
artifact per round, regenerated immediately after any edit to the
reviewed document. HARD GATE against over-rounding: the SPEC has had its
last model round; Plan v2's remaining findings and all future
non-blocking items travel to the collaborator as residuals.

**W5: Verification and packaging.** Produces D5: the machine-checkable
traceability table, isolation-provenance notes per reused vector, the
oracle report, cross-machine regeneration hashes, and the Section 8
handoff checklist. No family is "done" until its D5 entries exist.

## 5. Sequencing

```
now:       spec v3.1 + Plan v2 to the collaborator's queue:
           14.5 question FIRST (separate, cheap, gates the most work)
parallel:  W2a cores (AT-RISK re 14.5, separable artifacts)
           + S2 protocol + S1/S3-S5 semantic specs
gate A:    14.5 answered -> W2a de-risked or re-scoped per the recorded split
gate B:    14.1-14.4 + collaborator's SPEC review land -> incorporate ->
           FREEZE SPEC v1.0 (hash recorded)
then:      W2b finalization against the frozen hash; D4 written per 14.5
gate C:    reference source committed (collaborator) -> exact mutants (D3 stage 2)
gate D:    PILOT SLICE: one positive + one V2-style negative + one
           LOADER-REJECT case run end-to-end through a minimal Scala
           loader (the collaborator's stub or an agreed probe) BEFORE the
           full package is declared final; catches shared-misreading and
           schema incompatibility while they are cheap
handoff:   D1..D5 + Section 8 checklist walkthrough; harness begins.
           First harness milestone (recorded in the handoff note):
           S-mutant divergence demonstrations
```

## 6. Working rules

Unchanged and restated: baby steps with confirmation; one prompt in
flight in the coding loop; review diffs before merge; feature branches;
never patch tests to pass; scrub gate before any staging; no em-dashes
in anything drafted for external sending; multi-model findings presented
first-person. The pin-check SCHEDULE of Section 2 supersedes the v1
norm-only phrasing.

## 7. Risks and mitigations

| # | Risk | Impact | Mitigation |
|---|---|---|---|
| R1 | Pending design-authority answer redirects priorities mid-lane | Sequencing rework, not SPEC rework | Section 2 re-plan rule; W2a cores are lifecycle-independent |
| R2 | Collaborator REJECTS the candidate 14.5 split | Ownership, manifest fields, and Merkle-artifact placement change after W2a began | 14.5 asked first; W2a limited to raw cores with separable tx-set / proof / header-template layers so either side can pick up any layer; manifest fields not finalized until 14.5 recorded |
| R3 | Single-owner bottleneck (every workstream single-owned on this side; the collaborator single-points decisions and harness) | Any unavailability stalls the lane with no partial-progress path | Reviewable commits per checkpoint; runbook + reproducible commands; repo and decision list kept cold-resumable; interim pushes, never end-of-lane staging |
| R4 | Shared-misreading divergence: generator and oracle are both Python sharing one reading of the pinned sources; a shared misreading survives cross-check and surfaces post-handoff in Scala | Wholesale expectation rework, the exact failure the lane exists to prevent | Gate D pilot slice; hand-derived golden cases for byte-order and category-sensitive vectors; deliberately independent transcriptions (already the oracle's design rule) |
| R5 | Grammar freeze changes the ERGV magic; W2a marker vectors embed it | Regeneration of every marker vector, Merkle proof, and oracle constant: cheap in compute, not free in attention | Magic isolated as a single generator/oracle constant pair under the existing cross-transcription assert; regeneration + re-verification is one command; risk accepted, priced |
| R6 | Pinned PR head moves again (already happened once this lane) | Fixtures generated against stale semantics; worst case discovered post-handoff | Scheduled pin checks (Section 2); pin hashes embedded in every manifest; generation blocked on mismatch; seam-surface diff on movement |
| R7 | Reference source arrives late or differs from assumed structure | Exact mutants rewritten; category pins change | Gate C: no exact mutant before the committed reference hash; stage-1 semantic specs are source-independent by construction |
| R8 | Loader incompatibility discovered only at handoff | D2 satisfies Python-side schema but is unusable in Scala | Gate D includes the LOADER-REJECT demonstration in a schema-conformant loader |
| R9 | Decisions 14.1 to 14.4 stall | W2b, freeze, and exact mutants blocked | W2a + semantic specs + S2 keep the lane productive; decisions travel as ONE list answered once; 14.5 already decoupled |

## 8. Acceptance criteria (each checkable against an artifact)

1. **D1**: the collaborator records approval of the exact SPEC v1.0
   hash; the frozen document contains resolved answers for 14.1 to 14.5
   with no TBD markers.
2. **D2**: the coverage matrix of Section 3 is fully discharged: every
   required subcase has either a generated artifact (oracle
   re-verification green; regeneration byte-identical across two runs on
   two machines) or a D4 harness-construction recipe plus manifest
   synthesis fields; all manifests pass the agreed schema validator;
   every LOADER-REJECT case demonstrably rejects in the Gate D loader.
3. **D3**: S1, S3, S4, and both S5 layer variants each ship the
   conforming form, the exact mutant diff against the committed
   reference hash, at least one discriminating vector, and the expected
   verdict pair, each traced to the SPEC clause it enforces; S2 ships
   its mutation protocol and the invariance assertion. Divergence
   EXECUTION is the harness's recorded first milestone, not a lane
   criterion.
4. **D5**: the traceability table exists, is machine-checked (missing,
   duplicate, unknown ids, and 11.2-exclusion claims all fail the
   check), and the check passes.
5. **Handoff**: a pre-handoff walkthrough is held; the collaborator
   signs off the checklist (frozen SPEC hash, register map, layer
   scope, schema, recorded 14.5 split, fixture construction, category
   rules, S-test mechanisms) with no open questions AT SIGN-OFF.
   Post-handoff questions traceable to package gaps are logged as lane
   defects and feed the runbook; they are not retroactive criterion
   failures.
