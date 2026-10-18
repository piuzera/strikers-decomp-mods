#!/usr/bin/env python3
"""Inventory Mario assets and validate native nlChunk trees, without modifying them."""

import argparse
import hashlib
import json
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def chunks(data, start=0, end=None, depth=0):
    end = len(data) if end is None else end
    if depth > 32:
        raise ValueError("Chunk nesting exceeds 32 levels")
    result = []
    offset = start
    while offset < end:
        if offset + 8 > end:
            raise ValueError(f"Truncated header at {offset:#x}")
        raw_id, size = struct.unpack_from(">II", data, offset)
        next_offset = offset + 8 + size
        if next_offset > end:
            raise ValueError(f"Chunk at {offset:#x} extends beyond parent")
        alignment_bits = (raw_id >> 24) & 0x7F
        if alignment_bits > 16:
            raise ValueError(f"Unreasonable alignment at {offset:#x}")
        alignment = 1 << alignment_bits
        payload = (offset + 8 + alignment - 1) & -alignment
        if payload > next_offset:
            raise ValueError(f"Alignment exceeds chunk at {offset:#x}")
        item = {
            "offset": offset, "id": f"0x{raw_id & 0x80FFFFFF:08x}",
            "size": size, "data_offset": payload, "alignment": alignment,
        }
        if raw_id & 0x80000000:
            item["children"] = chunks(data, offset + 8, next_offset, depth + 1)
        result.append(item)
        offset = next_offset
    return result


def inventory(files):
    wanted = set((files / "art/characters/Mario").rglob("*"))
    for path in (files / "art/animation").iterdir():
        if path.name.lower().startswith("mario.") or path.name.lower() == "mario_triggers.txt":
            wanted.add(path)
    wanted.add(files / "mario.ini")
    result = []
    for path in sorted(p for p in wanted if p.is_file()):
        data = path.read_bytes()
        item = {
            "path": str(path.relative_to(files)), "bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
        }
        if path.suffix.lower() in {".glg", ".glt", ".shier", ".cph", ".bin"}:
            try:
                item["chunks"] = chunks(data)
            except (ValueError, struct.error) as exc:
                item["chunk_parse_error"] = str(exc)
        result.append(item)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--files", type=Path, default=ROOT / "orig/G4QE01/files")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = inventory(args.files)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + "\n")
    for item in report:
        status = item.get("chunk_parse_error", "chunk tree valid" if "chunks" in item else "inventory only")
        print(f"{item['bytes']:>10,}  {item['path']}  [{status}]")
