"""Donor transaction constants for the marker fixture generator.

The donor is a real, legacy (non-SegWit) Bitcoin transaction from block 342854
(txid display b33c1252...), used ONLY as the structural base for synthetic
marker fixtures. Its own OP_RETURN payload ("First OPReturn Message...") is NOT
a protocol marker; it is the UNRELATED-PREFIX case. See fixture-inventory-
SCRATCH.md, section "M2 MARKER-BEARING TRANSACTION FIXTURE".

DONOR_HEX is transcribed verbatim from the bottom of that document. Every byte
is verified by computation in txkit.self_test (txid_display(donor) must equal
DONOR_TXID_DISPLAY); nothing here is trusted from construction.
"""

DONOR_HEX = (
    "0100000001754ed03940f9373d6796cc9b1dc97e6d06097f9aa5e2f8c5604f90e64d53e340"
    "010000006b483045022100a4347c689b6698079a5cb53189212a0fdc7037b0b3b22d557c2b"
    "84e4009bbaa1022028749cc4086a88bf60b7863e87614ce3235385c2146497977ce33f9945"
    "8d0c300121039abf21fc7e635c52970010333ed867aee862f6985f019ec37ea23d2376d988"
    "fbffffffff02204e0000000000001976a9143f53b874d776eea1da76b623c5bb4c43c2ff9d"
    "6e88ac0000000000000000266a244669727374204f5052657475726e204d65737361676520"
    "49207761732068657265203a2900000000"
)

DONOR_TXID_DISPLAY = (
    "b33c1252ddc2fdb5396c7dc3ceed3749c587e3310c6df2f3605a38cc3c129e1f"
)
