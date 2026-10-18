#!/usr/bin/env python3
"""Decode native GLG geometry and make fixed-size mesh probes for round-trip QA.

Preserves packets, skinning, materials and unknown chunks. This is a native
position editor, not yet an arbitrary replacement-model exporter.
"""

import argparse
import hashlib
import json
import math
import struct
from pathlib import Path

from inspect_strikers_assets import chunks


def walk(tree):
    for chunk in tree:
        yield chunk
        yield from walk(chunk.get("children", []))


def payload(chunk):
    return chunk["data_offset"], chunk["offset"] + 8 + chunk["size"]


def read_within(data, fmt, offset, bounds):
    if offset < bounds[0] or offset + struct.calcsize(fmt) > bounds[1]:
        raise ValueError(f"Out-of-bounds {fmt} at {offset:#x}, bounds {bounds}")
    return struct.unpack_from(fmt, data, offset)


def skeleton(path):
    data = path.read_bytes()
    roots = chunks(data)
    if len(roots) != 1 or roots[0]["id"] != "0x80018000":
        raise ValueError("Expected a single hierarchy chunk")
    table = {c["id"]: c for c in roots[0]["children"]}
    header = payload(table["0x00018001"])
    count, = read_within(data, ">I", header[0] + 8, header)
    if not 0 < count <= 256:
        raise ValueError("Unexpected hierarchy node count")
    def values(chunk_id, fmt):
        bounds = payload(table[chunk_id])
        return read_within(data, fmt, bounds[0], bounds)
    bone_ids = values("0x00018003", f">{count}I")
    parents = values("0x00018009", f">{count}i")
    offsets = values("0x00018010", f">{count * 3}f")
    name_bounds = payload(table["0x00018002"])
    name = data[slice(*name_bounds)].split(b"\x00", 1)[0].decode("ascii")
    for i, parent in enumerate(parents):
        if parent < -1 or parent >= count or parent == i:
            raise ValueError(f"Invalid hierarchy parent {parent} for bone {i}")
    return {
        "name": name, "nodes": count,
        "bones": [{"index": i, "id": f"0x{bone_ids[i]:08x}", "parent": parents[i],
                   "translation_offset": offsets[i * 3:i * 3 + 3]} for i in range(count)],
    }


class Model:
    def __init__(self, data):
        self.data = data
        self.tree = chunks(data)
        self.packets = []
        self.positions = set()
        self.position_formats = {}
        self.software_positions = set()
        self.morph_deltas = set()
        for outer in walk(self.tree):
            if outer["id"] != "0x8001b000":
                continue
            children = outer["children"]
            table = {c["id"]: c for c in children}
            packet_bounds = payload(table["0x0001b004"])
            stream_bounds = payload(table["0x0001b005"])
            vertex_bounds = payload(table["0x0001b006"])
            index_bounds = payload(table["0x0001b007"])
            if (packet_bounds[1] - packet_bounds[0]) % 0x4A:
                raise ValueError("Packet chunk is not a multiple of 74 bytes")
            for pos in range(*packet_bounds, 0x4A):
                _, index_offset, count, primitive, num_streams, stream_offset = read_within(
                    data, ">IIHBBI", pos, packet_bounds)
                indices = read_within(data, f">{count}H", index_bounds[0] + index_offset, index_bounds)
                position_offsets = None
                stream_info = []
                for i in range(num_streams):
                    address, stream_id, stride = read_within(
                        data, ">IBB", stream_bounds[0] + stream_offset + i * 6, stream_bounds)
                    stream_info.append({"id": stream_id, "stride": stride, "address": address})
                    if stream_id not in (0, 14):
                        continue
                    if stream_id == 14 or stride not in (6, 12):
                        raise ValueError(f"Unexpected position stride {stride}")
                    fmt = ">3h" if stride == 6 else ">3f"
                    offsets = []
                    for index in range(max(indices, default=-1) + 1):
                        offset = vertex_bounds[0] + address + index * stride
                        vertex = read_within(data, fmt, offset, vertex_bounds)
                        if not all(math.isfinite(v) for v in vertex):
                            raise ValueError("Non-finite position")
                        offsets.append(offset)
                        if offset in self.position_formats and self.position_formats[offset] != fmt:
                            raise ValueError("Conflicting position encodings")
                        self.position_formats[offset] = fmt
                    position_offsets = offsets
                    self.positions.update(offsets)
                if position_offsets is None:
                    raise ValueError("Packet has no supported position stream")
                self.packets.append({
                    "primitive": primitive, "indices": indices,
                    "position_offsets": position_offsets, "streams": stream_info,
                })
            for chunk in walk(children):
                begin, end = payload(chunk)
                if chunk["id"] == "0x0001b00d":
                    if (end - begin) % 16:
                        raise ValueError("Software vertex chunk is not a multiple of 16 bytes")
                    self.software_positions.update(range(begin, end, 16))
                elif chunk["id"] == "0x0001b00c":
                    num_morphs, _ = read_within(data, ">II", begin, (begin, end))
                    count_offset = begin + 8 + num_morphs * 8
                    count, = read_within(data, ">I", count_offset, (begin, end))
                    for i in range(count):
                        offset = count_offset + 4 + i * 16
                        read_within(data, ">3fI", offset, (begin, end))
                        self.morph_deltas.add(offset)
        if not self.packets:
            raise ValueError("No supported native model chunks")

    def vertex(self, offset):
        fmt = self.position_formats.get(offset, ">3f")
        values = struct.unpack_from(fmt, self.data, offset)
        # glx_LoadStreams: GX_S16 positions have eight fractional bits.
        return tuple(v / 256.0 for v in values) if fmt == ">3h" else values

    def summary(self):
        vertices = [self.vertex(o) for o in sorted(self.positions)]
        return {
            "bytes": len(self.data), "sha256": hashlib.sha256(self.data).hexdigest(),
            "packets": len(self.packets), "position_records": len(self.positions),
            "software_position_records": len(self.software_positions),
            "morph_delta_records": len(self.morph_deltas),
            "bounds_min": [min(v[i] for v in vertices) for i in range(3)],
            "bounds_max": [max(v[i] for v in vertices) for i in range(3)],
            "packet_details": [
                {"primitive": p["primitive"], "index_count": len(p["indices"]),
                 "position_count": len(p["position_offsets"]), "streams": p["streams"]}
                for p in self.packets
            ],
        }

    def bind_matrices(self):
        matrices = {}
        for chunk in walk(self.tree):
            if chunk["id"] != "0x0001b00a":
                continue
            begin, end = payload(chunk)
            if (end - begin) % 68:
                raise ValueError("Bind-matrix chunk is not a multiple of 68 bytes")
            for offset in range(begin, end, 68):
                bone_id, *values = read_within(self.data, ">I16f", offset, (begin, end))
                # nlMatrix4 stores translation in e2[3][0..2]. Transpose for Blender.
                rows = [[values[column * 4 + row] for column in range(4)] for row in range(4)]
                if not all(math.isfinite(v) for row in rows for v in row):
                    raise ValueError("Non-finite bind matrix")
                matrices[f"0x{bone_id:08x}"] = rows
        return matrices

    def rewrite(self, scale):
        if not math.isfinite(scale) or not 0.5 <= scale <= 1.5:
            raise ValueError("Probe scale must be finite and between 0.5 and 1.5")
        output = bytearray(self.data)
        # Decode/re-encode only positions and morph vectors; all other bytes survive.
        for offset in self.positions | self.software_positions | self.morph_deltas:
            values = self.vertex(offset)
            if not all(math.isfinite(v) for v in values):
                raise ValueError("Non-finite geometry vector")
            fmt = self.position_formats.get(offset, ">3f")
            scaled = tuple(v * scale for v in values)
            if fmt == ">3h":
                scaled = tuple(round(v * 256.0) for v in scaled)
                if any(not -32768 <= v <= 32767 for v in scaled):
                    raise ValueError("Scaled fixed-point position overflows int16")
            struct.pack_into(fmt, output, offset, *scaled)
        Model(bytes(output))  # Read-back bounds and chunk validation.
        return bytes(output)

    def obj(self):
        lines = ["# Strikers native bind-space geometry; no textures or skinning applied"]
        for offset in sorted(self.positions):
            lines.append("v " + " ".join(format(v, ".9g") for v in self.vertex(offset)))
        lookup = {offset: i + 1 for i, offset in enumerate(sorted(self.positions))}
        for number, packet in enumerate(self.packets):
            lines.append(f"g packet_{number}")
            indices = [lookup[packet["position_offsets"][i]] for i in packet["indices"]]
            primitive = packet["primitive"]
            if primitive == 0:
                faces = [indices[i:i + 3] for i in range(0, len(indices) - 2, 3)]
            elif primitive == 1:
                faces = [(indices[i + (i % 2)], indices[i + 1 - (i % 2)], indices[i + 2])
                         for i in range(len(indices) - 2)]
            elif primitive == 2:
                faces = [(indices[0], indices[i], indices[i + 1]) for i in range(1, len(indices) - 1)]
            elif primitive == 3:
                faces = [indices[i:i + 4] for i in range(0, len(indices) - 3, 4)]
            else:
                raise ValueError(f"OBJ surface export does not support primitive {primitive}")
            for face in faces:
                if len(set(face)) >= 3:
                    lines.append("f " + " ".join(map(str, face)))
        return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("model", type=Path)
    parser.add_argument("--obj", type=Path, help="Export a bind-space inspection mesh")
    parser.add_argument("--output", type=Path, help="Write a fixed-size GLG round-trip/probe")
    parser.add_argument("--scale", type=float, default=1.0, help="Position/morph probe scale; 1 is identity")
    parser.add_argument("--brief", action="store_true", help="Omit per-packet stream details")
    parser.add_argument("--hierarchy", type=Path, help="Native .shier for a rig-reference JSON export")
    parser.add_argument("--rig-json", type=Path, help="Write hierarchy and Blender-convention bind matrices")
    args = parser.parse_args()
    try:
        model = Model(args.model.read_bytes())
        summary = model.summary()
        if args.brief:
            summary.pop("packet_details")
        print(json.dumps(summary, indent=2))
        if args.rig_json and not args.hierarchy:
            raise ValueError("--rig-json requires --hierarchy")
        sources = {args.model.resolve()}
        if args.hierarchy:
            sources.add(args.hierarchy.resolve())
        for destination in (args.obj, args.output, args.rig_json):
            if destination and destination.resolve() in sources:
                raise ValueError("Output cannot overwrite the source asset")
        if args.rig_json:
            args.rig_json.parent.mkdir(parents=True, exist_ok=True)
            args.rig_json.write_text(json.dumps({
                "hierarchy": skeleton(args.hierarchy),
                "bind_matrices": model.bind_matrices(),
                "matrix_convention": "row-major rows, column-vector multiplication, translation in last column",
            }, indent=2) + "\n")
        if args.obj:
            args.obj.parent.mkdir(parents=True, exist_ok=True)
            args.obj.write_text(model.obj())
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            result = model.rewrite(args.scale)
            args.output.write_bytes(result)
            print(f"Wrote {args.output}; identity={result == model.data}")
    except (OSError, ValueError, KeyError, struct.error) as exc:
        parser.exit(1, f"Error: {exc}\n")


if __name__ == "__main__":
    main()
