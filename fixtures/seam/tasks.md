# Tasks: Composition Hand-off Seam Package

Status: DRAFT v4, 2026-07-14. Derived from composition-handoff-PLAN.md v2
(Sections 3, 4, 5) and composition-handoff-SPEC.md v3.1. v1 received one
review round scoped to task-level content; v2 applies the accepted
findings: the end-game dependency cycle broken, phase-wide dependency and
parallelism conventions made explicit, verify lines made falsifiable and
present on every task, gate annotations completed against the matrix
(including the 14.5 prerequisite on the SPEC freeze), the appendix
normalized to one row per canonical key, 5c.3 split into real tasks, and
the D4 pseudo-gate replaced with explicit dependencies. v3 re-scoped
Phase 5c per an adjudicated gating decision: owner-neutral construction
contracts separated from ownership-bound recipes. v4 applies the human
review round: contracts and recipes are real tasks with their own ids
and states (a/b, plus 5c.2c for the 14.4 closure), and the V13 contract
is gated behind 5c.3a because its case semantics are 14.2 outputs. The Plan's
coverage matrix (Plan Section 3) is the master inventory; the appendix
proves every matrix row and subrow lands in exactly one task. Pipeline
position: Tasks stage; Build begins only after this document is approved.

Spark: the collaborator can start the Scala composition harness against a
deliverable package (D1 to D5) whose completeness is proven by artifacts,
not assurances, because the seam's byte-identity claim is exactly the
thing neither pinned PR tests on its own.

## Conventions

- All paths are repo-relative. All generated artifacts live under
  `fixtures/seam/`. All work happens in the repository working tree on a
  feature branch; every commit is runnable (bisect-green).
- Task states: `[ ]` open, `[x]` done, `BLOCKED-ON:<gates>` listed but
  not startable (comma-separated when multiple; ALL must land). Blocked
  tasks are never dropped; they close or re-scope only through the task
  that owns their gate.
- Dependencies name task ids. "Everything above" is not an edge.
- `[P]` marks tasks safe to run in parallel with their listed siblings,
  under the shared-file rules: goldens, oracle evidence, and reports are
  per-family files; each task edits ONLY its own pre-populated rows in
  `traceability.csv`; commits touching any shared file serialize (one
  writer at a time, rebase before push).
- Every task carries a `verify:` line naming checkable evidence. A task
  without its verify evidence is not done.
- Core-vs-family status: a FAMILY is done only when its core task, every
  blocked child, and its D5 rows (status `done` with evidence) are all
  closed. Core completion alone never closes a family. The traceability
  table computes this; no human declares it. Tasks owning multiple keys
  enumerate them; each key closes independently.
- Pin ledger: `fixtures/seam/PINS.md` is the committed ledger of
  expected pin values (producer PR head, consumer PR head, grammar doc
  hash, pre-freeze SPEC hash, repo HEAD). Expected values change ONLY
  via the 0.2 movement procedure or the 7.1 freeze; every check records
  the command, exit status, and actual values. Schedule point one of
  three (lane start) was executed 2026-07-14 with all pins verified
  equal; it is recorded as the first PINS.md entry by 0.1.
- Failure categories follow SPEC 8.5: exact category where
  structure-invariant, the {CONTRACT-FALSE, EVAL-FAIL} set where
  structure-dependent. For structure-dependent fixtures the pre-14.4
  expectation IS the set; decision 14.4 replaces it with one exact
  pinned value (closed by the owning 5b task).
- Standing rule, not a task: a reality check against the spark statement
  runs after every three to five build tasks.
- Standing rule, not a task: if the design authority's pending ruling
  lands, it blocks nothing here, but priorities are re-reviewed before
  the next task starts; it cannot change seam scope or completion
  criteria without a recorded revision of this document.
- Standing rule, not a task: once the 14.5 split is recorded (5a.1),
  every task completing afterward adds split-conformance to its verify.

## Phase 0: Lane controls and scaffolding

- [ ] 0.1 Before-generation pin check (schedule point two of three).
  Create `fixtures/seam/PINS.md`; record the lane-start entry (point
  one, 2026-07-14) and the point-two entry: expected values from this
  document's pinned sources, actual values re-derived, comparison
  command and exit status recorded. Generation (Phase 1) is
  hard-blocked on any mismatch; a mismatch routes to 0.2. Includes the
  pre-freeze SPEC file hash alongside the grammar doc hash. Updates D5
  key PINS to core-done.
  verify: PINS.md committed; every expected equals actual; expected
  fields diff-clean against the ledger; command, exit status, and
  actuals recorded; dated.
- [ ] 0.2 Pin-movement procedure (standing control, written once).
  Document in `fixtures/seam/README.md`: on any pin movement at any
  time, halt generation; run the SPEC Section 0 seam-surface
  re-verification; derive the invalidation set (every artifact whose
  inputs include the moved pin, resolved from manifest pin-hash
  fields); regenerate via 0.6; refresh every affected D5 row.
  verify: procedure text exists AND one worked example is included
  deriving the invalidation set for a hypothetical grammar-doc pin
  move.
- [ ] 0.3 Generator scaffolding under `fixtures/seam/gen/`, following
  the established architecture: constants module; generator;
  independent oracle with its own transcribed literals (no imports from
  the generator's constants beyond the shared gate constants);
  per-family hardcoded goldens; doc-hash gate over the grammar doc and
  the SPEC file as pinned (SPEC constant carries a PRE-FREEZE marker,
  re-pinned at freeze by 7.1); every write LF-only with newline="\n";
  integer satoshis; supply bound 2_100_000_000_000_000 as an integer.
  Ownership neutrality (risk R2, all stages, not only deal identity):
  every stage (tx-set, proof, header-template, packaging) consumes and
  produces serialized inputs through replaceable adapter boundaries; no
  stage calls another stage's internals directly; no filesystem or API
  boundary assigns machinery ownership before 5a.1; identity-bearing
  orchestration is entirely absent from Phase 0 and Phase 1 code (it
  belongs to 5a.2). Banned identifiers, greppable by name: box-id
  derivation calls, txid-from-payload helpers, payload-assembly
  functions. Emits one magic-embedding probe artifact and one unrelated
  control artifact (consumed by 0.6).
  verify: scaffolding imports cleanly; probe artifact round-trips
  generator to oracle; byte-level test confirms LF-only output;
  cross-transcription assert green; forbidden-import check green; grep
  for the named banned identifiers finds nothing; adapter boundary test
  proves each stage's inputs can be supplied externally.
- [ ] 0.4 Oracle seeded-defect self-test. A test mode corrupts one
  generator output in a temporary run; the oracle must detect it and
  fail. depends on: 0.3.
  verify: the self-test script demonstrates detection of the seeded
  defect; output stored under `fixtures/seam/gen/selftest/`.
- [ ] 0.5 D5 traceability framework and checker v1 (schema-independent).
  `fixtures/seam/traceability.csv` pre-populated with the full canonical
  key set (appendix, one row per key, including control keys), each row
  carrying: status (`open` / `blocked:<gates>` / `core-done` / `done`),
  owning task id, SPEC 11.1 threat row, expected failure category or
  set, evidence links. `check_traceability.py` fails on: missing key,
  duplicate key, unknown key, any `done` row lacking evidence links,
  any category value outside the SPEC 8.5 vocabulary, any exact
  category on a fixture the SPEC marks structure-dependent (the
  exact-vs-set rule), any artifact claiming a SPEC 11.2 exclusion.
  Schema-specific manifest validation is explicitly NOT in v1 (added by
  5b.10 after decision 14.3). [P] with 0.3.
  verify: checker green on the pre-populated table; one negative
  fixture per rejection rule listed above, each failing with a
  diagnostic naming the offending key or rule.
- [ ] 0.6 Regeneration entry point (risk R5 made executable). One
  command rebuilds every magic-embedding artifact generated in this
  repository from clean state. depends on: 0.3.
  verify: flip the magic constant in its single location; clean
  rebuild; the 0.3 probe's hash changes and the control artifact is
  byte-identical; restore the constant, rebuild, byte-identical to the
  committed state. Non-vacuity over the full artifact inventory is
  re-asserted by 1.13. Evidence stored in PINS.md.
- [ ] 0.7 D4 recipe template, structure only. [P] Headings, required
  inputs, provenance fields, expected outputs, failure-evidence slots
  per recipe. Every SPEC Section 13 bullet gets a stable requirement id
  and the template maps each id to exactly one slot. No family-specific
  content (that is 5c). Updates D5 key D4-DOC to core-done.
  verify: template at `fixtures/seam/d4-recipe-template.md`; the
  id-to-slot checklist is complete with no unmapped ids.
- [ ] 0.8 Phase verify. Full clean-state dry run: checker green
  including all negative fixtures; regeneration entry point run;
  seeded-defect test green. depends on: 0.1, 0.2, 0.3, 0.4, 0.5, 0.6,
  0.7.
  verify: exact commands, timestamps, exit codes, tool versions, and
  output hashes from the clean run recorded in PINS.md (single evidence
  location).

## Phase 1: W2a transaction-layer artifact cores (runnable now, AT-RISK per Plan R2)

Binding on every task in this phase: depends on 0.8. Artifacts built as
separable layers (tx-set / proof / header-template) consumed only as
serialized inputs through the 0.3 adapters; no task calls another
layer's generator directly; no reusable identity-bearing
payload/txid/proof assembly API exists anywhere before 5a.2, and where
identity-bearing bytes are syntactically required they are inline
per-vector literals. Expected categories declared per SPEC 8.5; oracle
green; hand-derived goldens for byte-order-sensitive vectors (risk R4);
each family's case inventory is machine-checked against the SPEC
Section 12 enumeration for that family; D5 row updated within the task,
never batched. Any task found to require an assumption about the 14.5
split STOPS and is re-scoped.

- [ ] 1.1 V1 PLAIN positive core (T1, C1/C2): one valid value
  authenticated and parsed. Deferred aspect: category closure under
  14.3, closed by 5b.1 (manifest fields are owned by 5b.9).
  verify: oracle green; golden hand-derived; case inventory green; D5
  key V1-PLAIN-core core-done.
- [ ] 1.2 V2 proof-vs-bytes mutation core (T2): var-1 mutation with
  transaction A's proof retained, CONTRACT-FALSE at properProof.
  Artifact schema-neutral (no loader-schema field names baked in).
  Deferred aspect: schema-dependent population under 14.3, closed by
  5b.2 against the 5b.9 schema. [P]
  verify: oracle green; the mutated byte and retained proof recorded as
  the case delta; case inventory green; D5 key V2-core core-done.
- [ ] 1.3 V3 extent-mismatch cores (T3): trailing byte, truncated tail,
  extent mismatches, malformed bytes AUTHENTICATED per the isolation
  rule. Completed-walk mismatch: CONTRACT-FALSE; past-end reads: the
  set. Deferred aspect: exact pins under 14.4, closed by 5b.3. [P]
  verify: oracle green; per-case authentication status and expected
  category recorded; case inventory green; D5 key V3-core core-done.
- [ ] 1.4 V4 overrun boundary-class cores (T4): all seven classes of
  SPEC Section 12, one vector each, authenticated per the isolation
  rule. Deferred aspect: category pins under 14.4, closed by 5b.4. [P]
  verify: oracle green including both positive boundary cases; case
  inventory green against the seven-class enumeration; D5 key V4-core
  core-done.
- [ ] 1.5 V5 mapping only (T6): case-to-requirement mapping for the
  reused grammar vectors (P6, at-capacity N15, N15d, N15e) plus
  isolation-provenance notes per reused vector. NO new composed
  payload-bearing artifact is generated by this task. Deferred aspect:
  V5 scope and physical composed vectors under 14.1 (R5 priced via
  0.6), closed by 5b.5. [P]
  verify: script cross-check confirms every cited grammar-vector id
  exists in the pinned grammar suite and every requirement id exists in
  the SPEC; every reused vector has a provenance note; D5 key
  V5-mapping core-done.
- [ ] 1.6 V6 witness-serialization core (T7): full witness serialization
  vector, CONTRACT-FALSE at inputCount (byte 4 is 0x00). No deferred
  aspect. [P]
  verify: oracle green; case inventory green; D5 key V6 done.
- [ ] 1.7 V8 deal-id-AGNOSTIC subset cores (T9, T10 partial):
  exactly-one violations, malformed same-magic, vout-range cases.
  Runnable output is identity-independent transaction semantics only;
  committed deal identity, where syntactically required, is a synthetic
  constant carried as inline per-vector literals with a provenance note
  proving no data-flow source from any box identifier.
  Magic-embedding: regenerable via 0.6. Deferred aspect: 14.1 layer
  binding and tagging, closed by 5b.6. [P]
  verify: oracle green; banned-identifier grep green; provenance note
  present; case inventory green; D5 key V8-AGN-core core-done.
- [ ] 1.8 V9 divergent-walk layout cores (T12): crafted boundary layouts
  where a plausible second walk selects a different output. Deferred
  aspect: 14.1 layer tags, closed by 5b.7. [P]
  verify: oracle records BOTH the canonical walk's and the plausible
  alternative walk's selected output descriptors and asserts they
  differ while the canonical walk selects the expected output; case
  inventory green; D5 key V9-core core-done.
- [ ] 1.9 V10 tx-layer reversal cores (T13): display-order txid as
  internal and inverse; reversed sibling; reversed Merkle-root
  comparison; double-hashed and reversed script commitment; reversed
  marker deal id against a synthetic committed identity constant
  (inline per-vector literal, no box-id derivation, no assembly API).
  Boundary expectations per the SPEC 8.4 table; failure categories per
  SPEC 8.5. Magic-embedding (the reversed-deal-id vector carries a
  marker payload): regenerable via 0.6. All goldens hand-derived. No
  deferred aspect at the tx layer. [P]
  verify: oracle green against hand-derived goldens; per-boundary
  expected values recorded; case inventory green; D5 key V10-TX done.
- [ ] 1.10 V11 Merkle-proof shape cores (T14): element lengths 32 and
  34, flag byte 2, truncated element, empty proof against root == txid
  (positive) and against a normal header (CONTRACT-FALSE). No deferred
  aspect. [P]
  verify: oracle green; case inventory green; D5 key V11 done.
- [ ] 1.11 V12 amount-case cores, mathematical cases only (T15): byte 7
  nonzero, byte 6 == 8, amount over supply, amount == minSats positive
  boundary, minSats == 0 and minSats over supply as contract-guard
  vectors with expected outcomes. No register encoding, no loader file
  representation. Deferred aspect: minSats representation and the
  loader-level schema case under 14.2 and 14.3, closed by 5b.8. [P]
  verify: oracle green; case inventory green; D5 key V12-core
  core-done.
- [ ] 1.12 V14 tx-layer confirmation cores (T17): exactly 5 descendants
  (CONTRACT-FALSE) and exactly 6 (positive) at the header-template and
  descendant-count level. MAY emit header-template bytes and descendant
  counts; PROHIBITED from constructing relay boxes, best-chain AVL
  state, or lookup proofs (that is 5c.4). Deferred aspect: relay-state
  harness recipe, closed by 5c.4. [P]
  verify: oracle green; artifact-type and path whitelist check confirms
  no relay-box, AVL-state, or lookup-proof artifact or constructor code
  was emitted; case inventory green; D5 key V14-TX core-done.
- [ ] 1.13 Phase verify. Full oracle run over all Phase 1 artifacts;
  checker green (blocked keys show `blocked:<gates>`, never missing);
  regeneration run twice from clean state, byte-identical; the 0.6
  magic-flip re-run over the FULL artifact inventory asserts every
  magic-embedding artifact's hash changes (non-vacuity, closing the 0.6
  probe-only scope) and every non-embedding artifact is byte-identical;
  second independent environment reproduces the hashes. depends on:
  1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 1.9, 1.10, 1.11, 1.12.
  verify: oracle report, magic-flip inventory result, and
  cross-environment hashes stored under `fixtures/seam/reports/`.

## Phase 2: S2 extension-mutation protocol (full deliverable, no gate)

- [ ] 2.1 S2 protocol (T1, invariant C2): metamorphic independence over
  Ergo spending transactions with multiple Ergo inputs, every OTHER
  input's extension mutated arbitrarily while the composed input is
  held constant; verdict must not change. Deliverable is a written
  protocol, not a Python artifact (the mutation surface is Ergo-side
  and belongs to the harness). S2-specific acceptance checklist (S2 is
  an invariance test, not a mutant; the Phase 3 template does not
  apply): baseline transaction defined; mutation domain over
  other-input extensions defined; held-constant field list; the
  invariance equality assertion; repetition count; harness-executable
  procedure. depends on: 0.8.
  verify: every checklist element present; D5 key S2-protocol done.

## Phase 3: S1/S3/S4/S5 semantic mutation specifications (D3 stage 1)

Binding on every task in this phase: depends on 0.8 (D5 rows live in the
0.5 table). Abstract-roles rule: these specifications name abstract
roles (the reference, the producer conjunct, the walk) and layer names
only. Decisions 14.1 and 14.2 gate ONLY concrete register references,
target-layer binding, and exact diffs; nothing in this phase waits for
them. Acceptance template per spec: baseline named; single mutation
described source-independently; invariant (C1 to C9) and threat row
named; layer declared; expected failure set declared per 8.5;
non-mutated fields listed; source-independent implementation recipe;
Gate-C exact mutant diff placeholder; D5 row updated in-task.

- [ ] 3.1 S1 semantic spec (T1): single-dataflow property of the
  reference (bytes bound once, feeding both producer hash and canonical
  walk) plus the non-conforming A/B mutant description (producer reads
  var 1, consumer reads var 5). [P]
  verify: acceptance-template checklist attached, every item mapped to
  a section; D5 key S1-sem done.
- [ ] 3.2 S3 semantic spec (T5): mutant substituting a txid register
  check for properProof, plus the extended-policy positive (txid
  commitment as an added conjunct rejects mismatches, cannot bypass
  inclusion). Concrete register references deferred per the
  abstract-roles rule, closed by 5b.11a. [P]
  verify: acceptance-template checklist attached, every item mapped to
  a section; D5 key S3-sem core-done (done at 5b.11a).
- [ ] 3.3 S4 semantic spec (T11): Boolean-bypass mutants (producer OR
  consumer; conditional bypass). The spec identifies the discriminating
  vectors the mutant is REQUIRED to accept when implemented; execution
  evidence belongs to 6.3, not this stage. [P]
  verify: acceptance-template checklist attached, every item mapped to
  a section; D5 key S4-sem done.
- [ ] 3.4 S5 semantic specs, BOTH layer variants (T12): MARKER, marker
  scan using its own output walk disagreeing with the payment walk;
  PLAIN, amount decoded from one descriptor derivation while the script
  hash uses an independently recomputed one. Both variants remain
  REQUIRED specifications regardless of decision 14.1; 14.1 selects
  which variant EXECUTES in the first harness, an execution deferral
  recorded by 5b.7, never a discard. Layer bindings closed by 5b.11b.
  [P]
  verify: acceptance-template checklists attached for both variants;
  D5 keys S5-M-sem and S5-P-sem core-done (done at 5b.11b).
- [ ] 3.5 Phase verify. depends on: 3.1, 3.2, 3.3, 3.4.
  verify: committed requirement-id-to-section checklist per spec; the
  phase verifier rejects blank, duplicate, or unresolved entries; D5
  statuses as declared per task.

## Phase 4: Aggregate audit of the runnable scope

- [ ] 4.1 Oracle report consolidated across Phase 1 to 3 artifacts;
  cross-environment regeneration hashes recorded; full checker run over
  the canonical key set (runnable keys done or core-done, blocked keys
  correctly gated). Adds NO new D5 rows; audits that producing tasks
  already wrote theirs. depends on: 1.13, 2.1, 3.5.
  verify: report committed under `fixtures/seam/reports/`; checker
  green.

## Phase 5a: BLOCKED-ON:14.5

- [ ] 5a.1 Re-scope on landing (risk R2 discharge). Fires the moment
  decision 14.5 is answered: record the accepted split verbatim; audit
  every Phase 0/1 artifact, adapter boundary, and drafted 5c construction
  contract (a-task) existing at landing against it; re-scope
  any conflicting task; update this document and every affected D5
  row. ROLLING: remains open until every Phase 1 task
  started before or during the audit has a conformance note; Phase 1
  tasks completing after the split is recorded carry split-conformance
  in their own verify (conventions standing rule). The ONLY authorized
  path from `blocked:14.5` to open. Owns D5 key RESCOPE-14.5.
  BLOCKED-ON:14.5.
  verify: recorded split committed; machine-readable conformance report
  with one entry per audited artifact, adapter, and drafted contract; D5 key RESCOPE-14.5 done.
- [ ] 5a.2 Construction-ordering protocol adoption for identity-bearing
  vectors, per the recorded split: the box id to payload to txid to
  proof chain. Owns D5 key PROTO-14.5. depends on: 5a.1.
  BLOCKED-ON:14.5.
  verify: protocol documented; a dry-run ordering trace recomputes the
  full chain and matches at every link; D5 key PROTO-14.5 done.
- [ ] 5a.3 V1 MARKER positive fixtures (T1). depends on: 5a.2.
  BLOCKED-ON:14.5,14.1.
  verify: oracle green; split-conformance note; ordering trace per
  5a.2 recomputed for each vector; D5 key V1-MARKER done.
- [ ] 5a.4 V8 IDENTITY subset fixtures (T10): C8a equality plus the
  controlled near-miss. depends on: 5a.2. BLOCKED-ON:14.5,14.1
  (conditionally 14.2: resolved by the recorded representation choice;
  if register-backed, 14.2 must also have landed).
  verify: oracle green; the near-miss delta is exactly one recorded
  field and is recomputed; split-conformance note; D5 key V8-ID done.

## Phase 5b: BLOCKED-ON:14.1-14.4 (each task names its exact gate)

- [ ] 5b.1 V1 PLAIN category closure. depends on: 1.1, 5b.9.
  BLOCKED-ON:14.3.
  verify: category recorded against the 14.3 decision; D5 key
  V1-PLAIN-core moved core-done to done.
- [ ] 5b.2 V2 schema-dependent population against the 5b.9 schema.
  depends on: 1.2, 5b.9, 5b.10 (checker evidence). BLOCKED-ON:14.3.
  verify: manifest validates under the 5b.10 rules; D5 key V2-core
  moved core-done to done.
- [ ] 5b.3 V3 exact category pins for structure-dependent cases.
  depends on: 1.3. BLOCKED-ON:14.4.
  verify: every set-valued case re-pinned to one exact category with
  the 14.4 rationale recorded; D5 key V3-core moved core-done to done.
- [ ] 5b.4 V4 exact category pins. depends on: 1.4. BLOCKED-ON:14.4.
  verify: as 5b.3 for the seven classes; D5 key V4-core moved
  core-done to done.
- [ ] 5b.5 V5 scope finalization and physical composed vectors
  (regeneration via 0.6; R5). Owns TWO keys. depends on: 1.5.
  BLOCKED-ON:14.1.
  verify: scope decision recorded; composed vectors oracle green; D5
  key V5-mapping moved core-done to done AND D5 key V5-scope done.
- [ ] 5b.6 V8-agnostic layer binding and tagging closure. depends on:
  1.7. BLOCKED-ON:14.1.
  verify: bindings recorded; D5 key V8-AGN-core moved core-done to
  done.
- [ ] 5b.7 V9 layer-tag finalization (re-tag of 1.8 outputs) and the S5
  execution-layer selection record. depends on: 1.8, 3.4.
  BLOCKED-ON:14.1.
  verify: tags applied and oracle re-run green; the S5 execution
  deferral recorded; D5 key V9-core moved core-done to done.
- [ ] 5b.8 V12 minSats representation and the loader-level schema case
  (LOADER-REJECT; never replaces the contract-guard vectors of 1.11).
  depends on: 1.11, 5b.9. BLOCKED-ON:14.2,14.3.
  verify: representation recorded per 14.2; loader case validates under
  5b.10 and demonstrably rejects; D5 key V12-core moved core-done to
  done.
- [ ] 5b.9 Manifest schema implementation, the single owner of every
  14.3-dependent field definition: file layout, field names for
  relay/header/proof/tx, hex case rules, unknown-field behavior. It
  IMPLEMENTS the layout and compatibility policy selected by decision
  14.3; SPEC Section 13 as pinned normatively fixes schema_version "2"
  exact and the profile-verdict fields (if 14.3 revises Section 13
  pre-freeze, the 7.1 spec-delta assessment governs). Family tasks
  populate against this schema; none defines fields. Owns D5 key
  MANIFEST-14.3 (blocked to done, jointly with 5b.10).
  BLOCKED-ON:14.3.
  verify: schema document committed; every affected family listed;
  D5 key MANIFEST-14.3 done after 5b.10.
- [ ] 5b.10 Checker schema-rules update: adds manifest validation per
  5b.9 to the 0.5 checker. depends on: 0.5, 5b.9. BLOCKED-ON:14.3.
  verify: one negative fixture per new schema rule fails with the rule
  named; joint closure of MANIFEST-14.3 recorded.
- [ ] 5b.11a S3 concrete register bindings folded into the 3.2 spec.
  depends on: 3.2. BLOCKED-ON:14.2.
  verify: bindings named against the 14.2 decision; D5 key S3-sem
  moved core-done to done.
- [ ] 5b.11b S5 layer bindings folded into the 3.4 specs. depends on:
  3.4. BLOCKED-ON:14.1.
  verify: bindings named against the 14.1 decision; D5 keys S5-M-sem
  and S5-P-sem moved core-done to done.

## Phase 5c: D4 harness-construction recipes (contract and recipe as separate tasks)

Two-stage model, each stage a real task with its own state. The a-task
is the owner-neutral CONSTRUCTION CONTRACT: immutable byte layouts,
required final states, mutation deltas, semantic inputs, required
evidence. Banned from every contract, because each encodes the 14.5
split: producer or consumer identity, interfaces, artifact locations,
injection procedure, provenance allocation. A contract closes its
family key to core-done ONLY, never to done. The b-task is the
OWNERSHIP-BOUND RECIPE, open only after 5a.1 records the split:
producer, consumer, interfaces, artifact locations, malformed-injection
procedure, provenance flow; it moves the key toward done (done requires
every child of the key closed). The 5a.1 rolling audit covers every
drafted contract. 5c.5 owns only D4-DOC and assembles authoritative D4
from ownership-bound recipes only, preserving the Plan's ordering (D4
written per the recorded split).

- [ ] 5c.1a V7 relay-box mutation contract (T8): exact token and
  register mutation deltas and required final box states for wrong NFT
  id, wrong quantity, zero tokens, token-vector-extended relay box.
  depends on: 0.7.
  verify: contract slots filled with banned content absent; D5 key
  V7-H core-done.
- [ ] 5c.1b V7 ownership-bound recipe: baseline box origin,
  mutate-vs-load method, injection method, provenance flow. depends
  on: 5c.1a, 5a.1.
  verify: every remaining template slot filled, provenance populated;
  D5 key V7-H done.
- [ ] 5c.2a V10 AVL-key reversal contract (T13): correct and reversed
  key bytes, the 88-byte record semantics, expected outcome recorded
  as the pre-14.4 {CONTRACT-FALSE, EVAL-FAIL} set. depends on: 0.7.
  verify: contract slots filled with banned content absent; D5 key
  V10-AVL-H core-done.
- [ ] 5c.2b V10 AVL-key ownership-bound recipe: proof production,
  injection method, state-digest ownership, provenance flow. depends
  on: 5c.2a, 5a.1.
  verify: every remaining template slot filled; D5 key V10-AVL-H
  ownership slots closed (key done only with 5c.2c).
- [ ] 5c.2c V10 AVL-key category closure: decision 14.4 replaces the
  set with one exact pinned category (recorded erratum: the matrix row
  lists D4 only; the 14.4 pin element is grounded in SPEC Sections 12
  and 8.5 and is carried deliberately). depends on: 5c.2a.
  BLOCKED-ON:14.4.
  verify: set-to-exact replacement recorded with the 14.4 rationale;
  D5 key V10-AVL-H done (jointly with 5c.2b).
- [ ] 5c.3a V13 semantic vector definitions (T16) for register/var
  error cases per 14.2's register-error decisions. Ownership-neutral
  by construction (case semantics and categories, no synthesis
  machinery), so it carries no 0.7 or 5a.1 dependency.
  BLOCKED-ON:14.2.
  verify: every V13 case of SPEC Section 12 carries a defined expected
  category per the 14.2 decisions; D5 key V13-SEM done.
- [ ] 5c.3b V13 construction contract (T16): required box and
  context-extension final states and per-case deltas for relay-absent,
  impostor (typed and untyped), swapped-register, wrong-var cases.
  NOT runnable in the waiting window: the case semantics it fixes are
  14.2 outputs, so the contract cannot be final before them. depends
  on: 0.7, 5c.3a. BLOCKED-ON:14.2 (via 5c.3a).
  verify: contract slots filled with banned content absent; D5 key
  V13-H core-done.
- [ ] 5c.3c V13 ownership-bound recipe: box and context-extension
  construction ownership, injection method, provenance flow. depends
  on: 5c.3b, 5a.1.
  verify: every remaining template slot filled; D5 key V13-H done.
- [ ] 5c.4a V14 relay-state contract: descendant arithmetic, required
  tip and inclusion record contents, the 88-byte layout, completing
  the 1.12 cores at the contract level. depends on: 0.7, 1.12.
  verify: contract slots filled with banned content absent; D5 key
  V14-RELAY-H core-done.
- [ ] 5c.4b V14 relay-state ownership-bound recipe: count origin,
  best-chain AVL state and lookup-proof production ownership,
  injection method, provenance flow. depends on: 5c.4a, 5a.1.
  verify: every remaining template slot filled; D5 keys V14-RELAY-H
  done AND V14-TX moved core-done to done.
- [ ] 5c.5 Authoritative D4 document assembly: template plus all
  ownership-bound recipes, plus the AVL key/value byte layout (88-byte
  record, display-order keys), relay-box registers and token vector,
  context-variable construction for vars 1 to 4, malformed-proof
  injection method. This task is where the Plan's "D4 written per
  14.5" lands: no assembly before the recorded split. depends on:
  5a.1, 5c.1b, 5c.2b, 5c.2c, 5c.3a, 5c.3c, 5c.4b.
  verify: every SPEC 13 requirement id and Plan D4 bullet maps to a
  recipe section; one worked example per recipe whose derived bytes
  and hashes are independently recomputed; D5 key D4-DOC moved
  core-done to done.

## Phase 6: BLOCKED-ON:Gate-C (exact mutants, D3 stage 2)

Acceptance, applied to every task: the diff applies cleanly to the
committed reference at its recorded hash; the mutant builds where the
mutation class permits; the designated discriminating vector fails for
the designated reason; all control tests still pass; the diff is
minimal and reviewed; execution evidence stored.

- [ ] 6.1 S1 exact mutant. depends on: 3.1. BLOCKED-ON:Gate-C.
  verify: phase acceptance met; D5 key S1-exact done.
- [ ] 6.2 S3 exact mutant. depends on: 3.2, 5b.11a.
  BLOCKED-ON:Gate-C,14.2.
  verify: phase acceptance met against the 14.2 bindings; D5 key
  S3-exact done.
- [ ] 6.3 S4 exact mutants. depends on: 3.3. BLOCKED-ON:Gate-C.
  verify: phase acceptance met; D5 key S4-exact done.
- [ ] 6.4 S5 MARKER-variant exact mutant. depends on: 3.4, 5b.11b.
  BLOCKED-ON:Gate-C,14.1.
  verify: phase acceptance met against a layer-specific conforming
  source at its recorded hash; if MARKER is the non-selected layer,
  execution defers with the source hash recorded; D5 key S5-M-exact
  done.
- [ ] 6.5 S5 PLAIN-variant exact mutant. depends on: 3.4, 5b.11b.
  BLOCKED-ON:Gate-C,14.1.
  verify: as 6.4 for the PLAIN variant; D5 key S5-P-exact done.

## Phase 7: End-game (strictly ordered)

- [ ] 7.1 Gate B closure, independent of the pilot: incorporate the
  collaborator's SPEC review and decisions 14.1 to 14.4; the recorded
  14.5 split is a prerequisite because the frozen document must
  resolve 14.1 to 14.5 with no TBD markers (Plan acceptance 1); run
  the spec-delta impact assessment (invalidation set derived per the
  0.2 procedure and recorded; conditional regeneration rerun via 0.6);
  freeze SPEC v1.0 and record the exact hash; flip the PRE-FREEZE
  marker and re-pin the doc-hash gate constants; regenerate. Owns D5
  key D1-FREEZE. depends on: 0.6, 5a.1, 5b.9. BLOCKED-ON:Gate-B.
  verify: frozen hash recorded in PINS.md and the manifest; no TBD
  markers; invalidation set and regeneration evidence recorded; D5 key
  D1-FREEZE done.
- [ ] 7.2 Near-full-matrix D5 closure: every canonical key at status
  done with evidence EXCEPT GATE-D (closed by 7.4) and the final PINS
  entry (written by 7.3). depends on: every task in Phases 0 to 6 plus
  7.1; the checker's open-key report is the machine-checkable
  prerequisite list.
  verify: checker output committed showing exactly {GATE-D} open and
  PINS at core-done.
- [ ] 7.3 Before-handoff pin check (schedule point three of three),
  executable: expected values from the committed ledger (diff-clean),
  actuals re-derived, command and exit status recorded; handoff is
  hard-blocked on any mismatch (route to 0.2). Moves D5 key PINS to
  done. RE-RUN RULE: if 7.4 or any later step changes any artifact,
  7.3 re-executes before 7.5. depends on: 7.2.
  verify: dated PINS.md entry, all pins equal, evidence per the ledger
  convention.
- [ ] 7.4 Gate D pilot slice. Prerequisites: 14.3 decided, the selected
  vectors finalized, and an agreed minimal loader or probe (the
  collaborator's stub or an agreed alternative; agreeing it is part of
  this task, building it is not this side's deliverable). One
  positive, one V2-style negative, one LOADER-REJECT case run
  end-to-end; the successful recorded run IS Gate D closure. Owns D5
  key GATE-D. depends on: 7.1, 7.3.
  verify: run transcript with artifact hashes, loader version,
  commands, exit codes, and expected/actual verdicts; the LOADER-REJECT
  case demonstrably rejects; D5 key GATE-D done.
- [ ] 7.5 Handoff checklist walkthrough per Plan Section 8 item 5:
  frozen SPEC hash, register map, layer scope, schema, recorded 14.5
  split, fixture construction, category rules, S-test mechanisms. Runs
  the FINAL all-key checker pass (GATE-D now done; zero open keys).
  First harness milestone recorded in the handoff note: S-mutant
  divergence demonstrations. depends on: 7.4 (and a re-run 7.3 if
  triggered).
  verify: final checker output with zero open keys committed; dated,
  signed checklist with a zero-entry unresolved-items field.

## Appendix: coverage-matrix traceability (canonical key set)

One row per canonical key; this table is the 0.5 checker's key
universe. Multi-key tasks appear once per key they own.

| D5 key | Matrix row / subrow | Core task | Closing / blocked child (gates) |
|---|---|---|---|
| V1-PLAIN-core | V1 PLAIN positive | 1.1 | 5b.1 (14.3) |
| V1-MARKER | V1 MARKER positive | 5a.3 | 5a.3 (14.5, 14.1) |
| V2-core | V2 | 1.2 | 5b.2 (14.3) |
| V3-core | V3 | 1.3 | 5b.3 (14.4) |
| V4-core | V4 | 1.4 | 5b.4 (14.4) |
| V5-mapping | V5 mapping | 1.5 | 5b.5 (14.1) |
| V5-scope | V5 scope / composed vectors | 5b.5 | 5b.5 (14.1) |
| V6 | V6 | 1.6 | none |
| V7-H | V7 | 5c.1a | 5c.1b (5a.1) |
| V8-AGN-core | V8 deal-id-agnostic | 1.7 | 5b.6 (14.1) |
| V8-ID | V8 identity | 5a.4 | 5a.4 (14.5, 14.1, 14.2 cond.) |
| V9-core | V9 | 1.8 | 5b.7 (14.1) |
| V10-TX | V10 tx-layer | 1.9 | none |
| V10-AVL-H | V10 AVL-key | 5c.2a | 5c.2b (5a.1), 5c.2c (14.4, erratum) |
| V11 | V11 | 1.10 | none |
| V12-core | V12 amount cases | 1.11 | 5b.8 (14.2, 14.3) |
| V13-SEM | V13 semantic definitions | 5c.3a | 5c.3a (14.2) |
| V13-H | V13 harness recipe | 5c.3b (14.2 via 5c.3a) | 5c.3c (5a.1) |
| V14-TX | V14 tx-layer | 1.12 | 5c.4b (5a.1) |
| V14-RELAY-H | V14 relay state | 5c.4a | 5c.4b (5a.1) |
| S1-sem | S1 semantic | 3.1 | none |
| S1-exact | S1 exact mutant | 6.1 | 6.1 (Gate-C) |
| S2-protocol | S2 | 2.1 | none |
| S3-sem | S3 semantic | 3.2 | 5b.11a (14.2) |
| S3-exact | S3 exact mutant | 6.2 | 6.2 (Gate-C, 14.2) |
| S4-sem | S4 semantic | 3.3 | none |
| S4-exact | S4 exact mutant | 6.3 | 6.3 (Gate-C) |
| S5-M-sem | S5 MARKER semantic | 3.4 | 5b.11b (14.1) |
| S5-M-exact | S5 MARKER exact mutant | 6.4 | 6.4 (Gate-C, 14.1) |
| S5-P-sem | S5 PLAIN semantic | 3.4 | 5b.11b (14.1) |
| S5-P-exact | S5 PLAIN exact mutant | 6.5 | 6.5 (Gate-C, 14.1) |
| MANIFEST-14.3 | Manifest schema (cross-family) | 5b.9 | 5b.9 + 5b.10 (14.3) |
| D4-DOC | D4 document | 0.7 | 5c.5 (5a.1; all a/b/c tasks) |
| PINS | Pin controls | 0.1 | 7.3 (handoff) |
| RESCOPE-14.5 | R2 re-scope control | 5a.1 | 5a.1 (14.5) |
| PROTO-14.5 | Construction-ordering protocol | 5a.2 | 5a.2 (14.5) |
| D1-FREEZE | SPEC freeze (D1) | 7.1 | 7.1 (Gate-B; 14.5 recorded) |
| GATE-D | Gate D pilot | 7.4 | 7.4 (14.3, loader agreed) |
