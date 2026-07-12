"""Protocol-agnostic Bitcoin transaction toolkit for the marker fixture set.

This module knows NOTHING about the marker grammar. It provides CompactSize
encoding, raw TxOut splicing, double-SHA256 txids, a stripped-form transaction
walker, and an output rebuilder. It imports nothing from the other generator
modules (donor.py is used only inside self_test).

STRIPPED (NON-WITNESS) SERIALIZATION ONLY: the operative form is the txid
preimage. parse_tx_sections aborts if it sees the BIP144 witness marker/flag
(0x00 followed by a nonzero flag byte) after the version, rather than
interpreting it as zero inputs. verify.py implements the same check
independently. SegWit PAYMENTS remain fully supported — they serialize into the
stripped form like any other output; what is rejected is the witness
serialization itself. The term is "stripped/non-witness serialization only",
not "legacy-only".

RAW SPLICE discipline: txout() uses the given script verbatim. No validation,
no normalization, no recalculation of anything inside the script, and never any
allocation or padding to a declared push length. Malformed scripts pass
through untouched.
"""

import hashlib
import struct


class UnsupportedSerializationError(ValueError):
    """Raised when a full BIP144 witness serialization is encountered."""


def compact_size(n: int) -> bytes:
    """Minimal CompactSize (varint) encoding of a non-negative integer."""
    if n < 0:
        raise ValueError("compact_size requires n >= 0")
    if n < 0xFD:
        return bytes([n])
    if n <= 0xFFFF:
        return b"\xfd" + struct.pack("<H", n)
    if n <= 0xFFFFFFFF:
        return b"\xfe" + struct.pack("<I", n)
    if n <= 0xFFFFFFFFFFFFFFFF:
        return b"\xff" + struct.pack("<Q", n)
    raise ValueError("compact_size out of range for a 64-bit varint")


def _read_compact_size(raw: bytes, off: int) -> tuple:
    """Decode a CompactSize at offset; return (value, next_offset). Strict."""
    if off >= len(raw):
        raise ValueError("truncated CompactSize prefix")
    first = raw[off]
    if first < 0xFD:
        return first, off + 1
    if first == 0xFD:
        if off + 3 > len(raw):
            raise ValueError("truncated CompactSize (fd)")
        return struct.unpack_from("<H", raw, off + 1)[0], off + 3
    if first == 0xFE:
        if off + 5 > len(raw):
            raise ValueError("truncated CompactSize (fe)")
        return struct.unpack_from("<I", raw, off + 1)[0], off + 5
    if off + 9 > len(raw):
        raise ValueError("truncated CompactSize (ff)")
    return struct.unpack_from("<Q", raw, off + 1)[0], off + 9


def txout(value_sats: int, raw_script: bytes) -> bytes:
    """8-byte LE value + CompactSize(len(script)) + script, RAW SPLICE.

    raw_script is spliced verbatim: no validation, no normalization, no
    recalculation, and never any allocation/padding to a declared push length.
    """
    return (
        struct.pack("<Q", value_sats)
        + compact_size(len(raw_script))
        + raw_script
    )


def dsha256(b: bytes) -> bytes:
    """Double SHA-256."""
    return hashlib.sha256(hashlib.sha256(b).digest()).digest()


def txid_internal(raw_tx: bytes) -> bytes:
    """Internal-order txid: dsha256 of the raw tx. NO reversal."""
    return dsha256(raw_tx)


def txid_display(raw_tx: bytes) -> str:
    """Display-order txid hex: the REVERSAL of the internal byte order."""
    return dsha256(raw_tx)[::-1].hex()


def parse_tx_sections(raw_tx: bytes) -> dict:
    """Stripped (non-witness) transaction walk. Returns offsets and slices.

    Used ONLY by the construction side; the verifier has its own parser. Aborts
    with UnsupportedSerializationError on the BIP144 witness marker/flag.
    """
    off = 0
    n = len(raw_tx)
    if n < 4:
        raise ValueError("transaction too short for version")
    version = raw_tx[0:4]
    off = 4

    # BIP144 abort: 0x00 marker followed by a nonzero flag byte.
    if off + 1 < n and raw_tx[off] == 0x00 and raw_tx[off + 1] != 0x00:
        raise UnsupportedSerializationError(
            "unsupported serialization: BIP144 witness marker/flag detected; "
            "stripped/non-witness serialization only"
        )

    input_count, off = _read_compact_size(raw_tx, off)
    inputs = []
    for _ in range(input_count):
        outpoint_start = off
        if off + 36 > n:
            raise ValueError("truncated input outpoint")
        prev_txid = raw_tx[off:off + 32]
        prev_vout = struct.unpack_from("<I", raw_tx, off + 32)[0]
        off += 36
        script_len, off = _read_compact_size(raw_tx, off)
        if off + script_len > n:
            raise ValueError("truncated input scriptSig")
        script_sig = raw_tx[off:off + script_len]
        off += script_len
        if off + 4 > n:
            raise ValueError("truncated input sequence")
        sequence = raw_tx[off:off + 4]
        off += 4
        inputs.append({
            "start": outpoint_start,
            "prev_txid": prev_txid,
            "prev_vout": prev_vout,
            "script_sig": script_sig,
            "sequence": sequence,
        })

    inputs_end = off
    output_count_offset = off
    output_count, off = _read_compact_size(raw_tx, off)
    outputs = []
    for _ in range(output_count):
        out_start = off
        if off + 8 > n:
            raise ValueError("truncated output value")
        value = struct.unpack_from("<Q", raw_tx, off)[0]
        off += 8
        script_len, off = _read_compact_size(raw_tx, off)
        script_start = off
        if off + script_len > n:
            raise ValueError("truncated output script")
        script = raw_tx[off:off + script_len]
        off += script_len
        outputs.append({
            "start": out_start,
            "value": value,
            "script_start": script_start,
            "script": script,
        })

    locktime_offset = off
    if off + 4 > n:
        raise ValueError("truncated locktime")
    locktime = raw_tx[off:off + 4]
    off += 4
    if off != n:
        raise ValueError("trailing bytes after locktime")

    return {
        "version": version,
        "input_count": input_count,
        "inputs": inputs,
        "inputs_end": inputs_end,
        "output_count_offset": output_count_offset,
        "output_count": output_count,
        "outputs": outputs,
        "locktime_offset": locktime_offset,
        "locktime": locktime,
    }


def rebuild_outputs(raw_tx: bytes, outputs: list) -> bytes:
    """Rebuild a tx keeping version+inputs+locktime verbatim, new outputs.

    outputs is a list of pre-framed TxOut byte strings, concatenated verbatim.
    """
    sec = parse_tx_sections(raw_tx)
    prefix = raw_tx[0:sec["inputs_end"]]
    return (
        prefix
        + compact_size(len(outputs))
        + b"".join(outputs)
        + sec["locktime"]
    )


def self_test() -> None:
    import donor

    # CompactSize goldens.
    assert compact_size(252).hex() == "fc", compact_size(252).hex()
    assert compact_size(253).hex() == "fdfd00", compact_size(253).hex()
    assert compact_size(257).hex() == "fd0101", compact_size(257).hex()
    assert compact_size(65535).hex() == "fdffff", compact_size(65535).hex()
    assert compact_size(65536).hex() == "fe00000100", compact_size(65536).hex()

    # TxOut golden.
    assert txout(0, bytes.fromhex("6a01aa")).hex() == "0000000000000000036a01aa", \
        txout(0, bytes.fromhex("6a01aa")).hex()

    raw = bytes.fromhex(donor.DONOR_HEX)

    # Parse-and-rebuild with the donor's own outputs is byte-identical.
    sec = parse_tx_sections(raw)
    own_outputs = [
        raw[o["start"]:o["script_start"] + len(o["script"])]
        for o in sec["outputs"]
    ]
    rebuilt = rebuild_outputs(raw, own_outputs)
    assert rebuilt == raw, "donor rebuild not byte-identical"

    # Internal order is 1f9e123c...; only the reversal matches the display id.
    assert dsha256(raw).hex().startswith("1f9e123c"), dsha256(raw).hex()
    assert txid_display(raw) == donor.DONOR_TXID_DISPLAY, txid_display(raw)

    # BIP144 witness-form abort.
    segwit = bytes.fromhex("02000000") + b"\x00\x01" + b"\xde\xad\xbe\xef"
    try:
        parse_tx_sections(segwit)
    except UnsupportedSerializationError:
        pass
    else:
        raise AssertionError("BIP144 witness serialization was not rejected")

    print("txkit.self_test: OK")


if __name__ == "__main__":
    self_test()
