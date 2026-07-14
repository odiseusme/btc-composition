# Seam Lane Pin Ledger

This file is the committed ledger of expected pin values for the seam
lane (tasks.md conventions). Expected values change ONLY via the 0.2
movement procedure or the 7.1 freeze. Every check records command,
exit status, and actual values. Generation is hard-blocked on any
mismatch.

## Expected pins (source: tasks.md pinned documents)

- producer PR head (#1182): 247b07e99c19ba195e5cdc21a4733ad546d77edf
- consumer PR head (#1180): aff008b85f8b7562867e6cc2292ff174627e7732
- grammar doc sha256 (marker-grammar-DRAFT.md):
  02790eaf4652a5710a81afed7128345a120e197b11513bee91079a4ac49166ff
- SPEC pre-freeze sha256 (composition-handoff-SPEC.md):
  5926f12a4427eabb30e7db31f623663b662316957b67fcfe9a852d15fc054831
  (PRE-FREEZE: re-pinned at v1.0 by task 7.1)
- base commit: 283062c (HEAD must be this or a fast-forward of it)

## Check log

### Point one of three: lane start

RECONSTRUCTION, and labelled as one: this check ran at the lane-opening
session, before this ledger existed, so the evidence below is
transcribed from that session's log rather than re-derived here. It is
recorded to the same standard as any other entry — command, exit
status, actual value — because an entry that merely asserts the pins
were equal is an assurance, which is the one thing this ledger does not
accept. A later re-derivation of these actuals is a check of its own
and would be its own entry.

Date: 2026-07-14
Commands: git ls-remote (PR refs); sha256sum (grammar doc);
git rev-parse HEAD
Exit status: 0 (all)
Actuals:
- #1182 head: 247b07e99c19ba195e5cdc21a4733ad546d77edf  MATCH
- #1180 head: aff008b85f8b7562867e6cc2292ff174627e7732  MATCH
- grammar doc:
  02790eaf4652a5710a81afed7128345a120e197b11513bee91079a4ac49166ff  MATCH
- repo HEAD: 283062c (exact, pre-merge)  MATCH
- SPEC pre-freeze sha256: NOT IN THE PIN SET at point one. It was added
  to the pin set at point two (below), which is why no actual for it is
  recorded here and why none can be reconstructed after the fact.
Result: every pin then in the set was equal. Lane opened.

### Point two of three: before generation (task 0.1)

Date: 2026-07-14T08:41:07Z
Commands: git ls-remote (PR refs); sha256sum (both docs);
git rev-parse HEAD; git merge-base --is-ancestor 283062c HEAD
Exit status: 0 (all)
Actuals:
- #1182 head: 247b07e99c19ba195e5cdc21a4733ad546d77edf  MATCH
- #1180 head: aff008b85f8b7562867e6cc2292ff174627e7732  MATCH
- grammar doc:
  02790eaf4652a5710a81afed7128345a120e197b11513bee91079a4ac49166ff  MATCH
- SPEC pre-freeze:
  5926f12a4427eabb30e7db31f623663b662316957b67fcfe9a852d15fc054831  MATCH
- repo HEAD: 9427c716afb79767d8857aa3140d436893b00818
  (fast-forward of base 283062c: confirmed ancestor)  MATCH
Result: ALL PINS EQUAL. Generation unblocked.

D5 note: key PINS reaches core-done at this task; the traceability
table created by task 0.5 pre-populates that status.

### Point three of three: before handoff (task 7.3)

Pending.
