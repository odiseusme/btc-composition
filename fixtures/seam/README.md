# Seam Fixture Lane

This directory holds the composition hand-off seam package: generated
fixture families, structural test specifications, the traceability
table, the pin ledger (PINS.md), and the tasks document (tasks.md)
derived from the lane plan. The seam is the byte-for-byte identity
between what the producer authenticates and what the consumer parses;
everything in this directory exists to prove that identity with
artifacts.

## Pin-movement procedure (standing control, task 0.2)

Triggered by ANY pin movement detected at ANY time: at a scheduled
check (PINS.md, points one to three), during work, or reported
externally. The pins are listed in PINS.md; the pinned sources and
their roles are SPEC Section 0.

1. HALT generation. No new artifact is generated or regenerated until
   the procedure completes. Record the moved pin (old value, new
   value, detection time) in PINS.md under a new check-log entry.

2. SEAM-SURFACE RE-VERIFICATION per SPEC Section 0: re-verify every
   claim in SPEC Sections 4, 5, 6, and 8 against the new head or
   document. Apply the Section 10 rule to each delta: a change is
   seam-relevant only if it touches a construct on the seam surface
   (the authenticated byte range, the decoding walk, the failure
   categories, the composition invariants). Record the per-delta
   verdicts. If any seam-surface construct changed, STOP: the change
   goes to the lane owner before any regeneration, because the SPEC
   itself may need revision (and after freeze, task 7.1's spec-delta
   assessment governs).

3. DERIVE THE INVALIDATION SET mechanically, never by judgment: every
   generated record's manifest entry carries the hash of each pinned
   document its bytes depend on. The invalidation set is exactly the
   set of records whose manifest carries the moved pin's OLD value,
   plus the gate constants that transcribe that pin (the doc-hash gate
   in the generator and oracle). Nothing outside that set is touched.

4. UPDATE the transcribed constants (expected hash in the gate,
   expected values in PINS.md) in one commit, so the ledger and the
   gate can never disagree.

5. REGENERATE the invalidation set via the one-command entry point
   (task 0.6). Run the oracle over the regenerated set. Confirm
   every artifact OUTSIDE the set is byte-identical (the entry point's
   control property).

6. REFRESH every affected D5 row in traceability.csv (evidence links
   point at the new oracle report and hashes) and close the PINS.md
   entry with commands, exit statuses, and the resulting HEAD.

## Worked example: hypothetical grammar-doc pin move

Suppose marker-grammar-DRAFT.md changes (say the payload magic is
re-chosen at the grammar freeze, risk R5) and its sha256 moves from
02790eaf...66ff to a new value NEWHASH.

1. Halt; log the move in PINS.md.
2. Seam-surface re-verification: the grammar doc defines the payload
   layer (marker magic and ABI). Diff old to new. If only the magic
   constant changed, the seam surface (walk, categories, invariants)
   is unchanged and the verdict is regenerate-only. If the ABI layout
   changed, that IS a seam-surface change: stop and escalate.
3. Derive the invalidation set: scan every manifest record for a
   grammar-doc hash field equal to 02790eaf...66ff. By construction
   these are exactly the magic-embedding artifacts, for example the
   V8 deal-id-agnostic same-magic vectors (task 1.7), the V10
   reversed-marker-deal-id vector (task 1.9), the 0.3 probe artifact,
   and V5 or V1-MARKER physical vectors if they exist yet. A V11
   proof-shape vector carrying no payload does not reference the
   grammar hash and is untouched, which is the point of mechanical
   derivation.
4. One commit updates EXPECTED_GRAMMAR_SHA256 in the gate and the
   expected value in PINS.md.
5. Run the 0.6 entry point; the flipped-magic rebuild regenerates
   exactly the set from step 3; oracle green; all other artifacts
   byte-identical.
6. Refresh the D5 rows for the affected families; close the PINS.md
   entry.
