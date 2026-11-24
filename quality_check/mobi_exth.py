# Ported from kiwidude68/calibre_plugins quality_check's mobi6.py EXTH
# reading (GPL-3, upstream author kiwidude/Grant Drake; the record walk is
# upstream's, minus calibre's MetadataUpdater dependency), for the
# CalibreQuarry plugin host per docs/crosswalk.md.

"""A minimal MOBI EXTH header reader (stdlib): the four records the
MOBI/AZW check family reads (113 asin, 401 clipping, 501 cdetype, 504
asin2). Rejects Topaz (TPZ) files like upstream."""

from __future__ import annotations

import struct
from pathlib import Path


class NotMobiError(ValueError):
    """The file is not a MOBI/AZW the reader can parse."""


def read_exth(path: Path) -> dict[int, bytes]:
    """The EXTH records as {type: first value}."""
    data = Path(path).read_bytes()
    if data[60:64] != b"BOOK" and data[60:64] != b"TEXt":
        raise NotMobiError(f"bad PalmDB type: {data[60:64]!r}")
    num_records = struct.unpack(">H", data[76:78])[0]
    if num_records == 0:
        raise NotMobiError("no records")
    record0_offset = struct.unpack(">I", data[78:82])[0]
    if data[record0_offset + 60 : record0_offset + 64] == b"TPZ":
        raise NotMobiError("Topaz MOBI is not supported")
    if data[record0_offset + 16 : record0_offset + 20] != b"MOBI":
        raise NotMobiError("no MOBI header")
    header_length = struct.unpack(
        ">I", data[record0_offset + 20 : record0_offset + 24]
    )[0]
    exth_flags = struct.unpack(">I", data[record0_offset + 128 : record0_offset + 132])[
        0
    ]
    if not exth_flags & 0x40:
        return {}
    exth_start = record0_offset + 16 + header_length
    if data[exth_start : exth_start + 4] != b"EXTH":
        return {}
    count = struct.unpack(">I", data[exth_start + 8 : exth_start + 12])[0]
    pos = exth_start + 12
    out: dict[int, bytes] = {}
    for _ in range(count):
        rec_type, rec_len = struct.unpack(">II", data[pos : pos + 8])
        value = data[pos + 8 : pos + rec_len]
        if rec_type not in out:
            out[rec_type] = value
        pos += rec_len
    return out


def get_exth_field(path: Path, rec_type: int) -> str | None:
    records = read_exth(path)
    value = records.get(rec_type)
    return value.decode("utf-8", "replace") if value else None
