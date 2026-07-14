"""constants.py — BOOKKEEPING ONLY for the seam lane (task 0.3).

This module is deliberately thin. It holds the values that both the
construction side (generate.py, adapters.py) and the independent oracle
(verify.py) are ALLOWED to share: the pre-freeze status marker, the two
doc-hash gate pins, the pin values of the two PR heads, and the supply
bound.

NOT here, by design:

  * No layout constants. The marker payload layout, the magic bytes, the
    field offsets, the header-template shape, and the proof shape are all
    layout facts. At this stage the ONLY layout-bearing literal in the
    generator is the payload magic, and it lives in exactly ONE place on
    the construction side (generate.py), which is what task 0.6 flips.
    Putting it here would give it a second home and defeat that test.

  * No stage ownership. Nothing in this module says which side of the
    seam builds what; decision 14.5 has not landed (risk R2).

The oracle (verify.py) may import STATUS, EXPECTED_GRAMMAR_SHA256, and
EXPECTED_SPEC_SHA256 from here and NOTHING else — everything it checks it
retranscribes as its own literal. generate.cross_check_transcriptions()
enforces that at every run: if the oracle ever imports a value it is
supposed to transcribe, the comparison of the two copies degrades into a
comparison of a value with itself, and the build fails loudly.
"""

# --- Freeze state -----------------------------------------------------------
# The SPEC is pinned PRE-FREEZE. Task 7.1 freezes SPEC v1.0, flips this
# marker, and re-pins EXPECTED_SPEC_SHA256 to the frozen hash.
STATUS = "PRE-FREEZE"

# --- Doc-hash gate pins (transcribed from fixtures/seam/PINS.md) ------------
# Expected values change ONLY via the 0.2 movement procedure or the 7.1
# freeze, and the ledger and the gate move in the same commit so they can
# never disagree. generate.gate_docs() hashes the exact LF-only bytes of
# each document and refuses to run on a mismatch.
EXPECTED_GRAMMAR_SHA256 = (
    "02790eaf4652a5710a81afed7128345a120e197b11513bee91079a4ac49166ff"
)
EXPECTED_SPEC_SHA256 = (
    "5926f12a4427eabb30e7db31f623663b662316957b67fcfe9a852d15fc054831"
)

# --- Seam-surface PR head pins (PINS.md), carried as strings ----------------
# The two pinned sources the SPEC's seam surface is verified against. They
# are recorded here as bookkeeping so a generated manifest can name the
# heads its bytes were reasoned against; nothing in the generator resolves
# or fetches them.
PRODUCER_PR_HEAD = "247b07e99c19ba195e5cdc21a4733ad546d77edf"   # PR #1182
CONSUMER_PR_HEAD = "aff008b85f8b7562867e6cc2292ff174627e7732"   # PR #1180

# --- Amount arithmetic ------------------------------------------------------
# The 21M BTC supply bound in satoshi. INTEGER, always: never a float,
# never 21e14. Every satoshi value in this lane is a Python int, and the
# oracle retranscribes this bound as its own literal (verify._SUPPLY_BOUND_SATS)
# so a construction-side typo here cannot mask itself.
SUPPLY_BOUND_SATS = 2_100_000_000_000_000


def self_test() -> None:
    """Bookkeeping-only invariants of this module."""
    assert STATUS == "PRE-FREEZE", STATUS

    for name, value in (
        ("EXPECTED_GRAMMAR_SHA256", EXPECTED_GRAMMAR_SHA256),
        ("EXPECTED_SPEC_SHA256", EXPECTED_SPEC_SHA256),
    ):
        assert len(value) == 64, name
        assert all(c in "0123456789abcdef" for c in value), name

    for name, value in (
        ("PRODUCER_PR_HEAD", PRODUCER_PR_HEAD),
        ("CONSUMER_PR_HEAD", CONSUMER_PR_HEAD),
    ):
        assert isinstance(value, str), name
        assert len(value) == 40, name
        assert all(c in "0123456789abcdef" for c in value), name

    # Integer satoshis. bool is an int subclass, so exclude it explicitly;
    # a float here (2.1e15) would compare equal and must still be rejected.
    assert isinstance(SUPPLY_BOUND_SATS, int), type(SUPPLY_BOUND_SATS)
    assert not isinstance(SUPPLY_BOUND_SATS, bool)
    assert SUPPLY_BOUND_SATS == 2100000000000000, SUPPLY_BOUND_SATS

    print("constants.self_test: OK")


if __name__ == "__main__":
    self_test()
