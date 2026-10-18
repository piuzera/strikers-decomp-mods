#!/usr/bin/env python3
"""Export the fitted generic player to native GLG using Strikers' CPU skinning.

Both model variants retain their retail model IDs and original bind matrices.
Colour comes from a generated RGB565 atlas appended to the retail PTLG texture
bundle; the engine's character TEV path (texconfig 0x21) computes
diffuse texture x light ramp. Facial morphs and blinking stay omitted.
"""

import argparse
import hashlib
import json
import math
import struct
from pathlib import Path

from palmeiras_texture import (ATLAS_SIZE, TEXTURE_NAME, append_texture,
                               build_atlas, color_bytes, encode_texture,
                               lower_hash)
from strikers_mesh import Model, payload, read_within, walk

ROOT = Path(__file__).resolve().parents[1]
FILES = ROOT / "orig/G4QE01/files"
SOURCE = ROOT / "mods/palmeiras/assets/work/player-intermediate.json"
OUT = ROOT / "build/palmeiras/player-export"


def native_hash(text):
    value = 0xFFFFFFFF
    for byte in text.encode("ascii"):
        value = (value * 33 + byte) & 0xFFFFFFFF
    return value


def chunk(identifier, data):
    return struct.pack(">II", identifier, len(data)) + data


def quantize_weights(weights):
    if not weights or any(not math.isfinite(w) or w <= 0 for w in weights.values()):
        raise ValueError("Weights must be finite and positive")
    ordered = sorted((int(name, 16), weight) for name, weight in weights.items())
    total = sum(w for _, w in ordered)
    scaled = [w / total * 65535 for _, w in ordered]
    result = [math.floor(w) for w in scaled]
    remainder = 65535 - sum(result)
    for index in sorted(range(len(result)), key=lambda i: (scaled[i] - result[i], -i), reverse=True)[:remainder]:
        result[index] += 1
    return tuple((bone, weight) for (bone, _), weight in zip(ordered, result) if weight)


def geometry(document, uv_blocks):
    if document.get("format") != "palmeiras-player-intermediate-v1":
        raise ValueError("Unsupported intermediate format")
    vertices, packets, lookup, source_uvs = [], [], {}, []
    mesh_uvs = uv_blocks is None
    for mesh in document["meshes"]:
        positions, weights, materials = mesh["positions"], mesh["weights"], mesh["materials"]
        if len(positions) != len(weights):
            raise ValueError("Position and weight counts differ")
        indices = []
        for triangle in mesh["triangles"]:
            if len(triangle["vertices"]) != 3:
                raise ValueError("Expected triangles")
            normal = triangle["normal"]
            length = math.sqrt(sum(v * v for v in normal))
            if not math.isfinite(length) or length <= 1e-8:
                raise ValueError("Degenerate or non-finite normal")
            packed_normal = tuple(max(-64, min(64, round(v / length * 64))) for v in normal)
            rgba = (255, 255, 255, 255) if mesh_uvs else color_bytes(materials[triangle["material"]]["base_color"])
            if mesh_uvs and ("uvs" not in triangle or len(triangle["uvs"]) != 3):
                raise ValueError("Textured triangles require three per-corner UV coordinates")
            for corner, index in enumerate(triangle["vertices"]):
                if index < 0 or index >= len(positions):
                    raise ValueError("Triangle references a missing vertex")
                position = positions[index]
                if len(position) != 3 or any(not math.isfinite(v) or abs(v) > 10 for v in position):
                    raise ValueError("Position is invalid or outside prototype bounds")
                pos_bytes = struct.pack(">3f", *position)
                membership = quantize_weights(weights[index])
                # Weld duplicate source corners and average their normals. Flat
                # per-triangle normals otherwise multiply CPU-skinned vertices.
                uv = None
                if mesh_uvs:
                    source_uv = triangle["uvs"][corner]
                    if len(source_uv) != 2 or any(not math.isfinite(v) or not 0 <= v <= 1 for v in source_uv):
                        raise ValueError("Mesh UV coordinates must be finite and in [0, 1]")
                    # Blender's UV origin is bottom-left; native texture rows
                    # are top-down. GX UVs have ten fractional bits.
                    uv = (round(source_uv[0] * 1024), round((1 - source_uv[1]) * 1024))
                key = (pos_bytes, rgba[:3], membership, uv)
                if key not in lookup:
                    lookup[key] = len(vertices)
                    vertices.append([pos_bytes, [0.0, 0.0, 0.0], rgba, membership, packed_normal])
                    source_uvs.append(uv)
                entry = vertices[lookup[key]]
                for axis in range(3):
                    entry[1][axis] += normal[axis] / length
                indices.append(lookup[key])
        if not indices or len(indices) > 65535:
            raise ValueError("Empty packet or packet exceeds uint16 index-count limit")
        packets.append({"name": mesh["name"], "indices": indices})
    if not vertices or len(vertices) > 65535:
        raise ValueError("Software vertex count exceeds uint16 skin-pair capacity")
    for vertex_index, entry in enumerate(vertices):
        length = math.sqrt(sum(v * v for v in entry[1]))
        # Slot 5: final packed normal (averaged, flat fallback); slot 6: atlas UV.
        entry.append(tuple(max(-64, min(64, round(v / length * 64))) for v in entry[1])
                     if length > 1e-8 else entry[4])
        if mesh_uvs:
            entry.append(source_uvs[vertex_index])
        elif entry[2][:3] not in uv_blocks:
            raise ValueError("Vertex colour missing from the UV atlas")
        else:
            entry.append(uv_blocks[entry[2][:3]])
    return vertices, packets


def one_chunk(model, identifier):
    found = [c for c in walk(model.tree) if c["id"] == f"0x{identifier:08x}"]
    if len(found) != 1:
        raise ValueError(f"Expected exactly one {identifier:#x} chunk")
    begin, end = payload(found[0])
    return model.data[begin:end]


def packet_state():
    """Hand-rolled state already validated in-game for this 4-stream, texconfig-1
    packet (the retail packet's state was authored for 5 streams / texconfig 3)."""
    texture_state = (63 << 18) | (63 << 30) | (63 << 36) | (63 << 42) | (63 << 48)
    raster = 1 | (1 << 1) | (1 << 2) | (3 << 18)
    return texture_state, 0, raster


def export(document, template, diffuse_hash, uv_blocks):
    vertices, geometry_packets = geometry(document, uv_blocks)
    native = Model(template)
    header = one_chunk(native, 0x1B003)
    _, model_id, model_pad, _ = struct.unpack(">4I", header)
    bind_data = one_chunk(native, 0x1B00A)
    bind_ids = {struct.unpack_from(">I", bind_data, i)[0] for i in range(0, len(bind_data), 68)}
    bones = sorted({bone for vertex in vertices for bone, _ in vertex[3]})
    if not set(bones) <= bind_ids:
        raise ValueError(f"Missing native bind matrices: {set(bones) - bind_ids}")

    position_data = b"".join(vertex[0] for vertex in vertices)
    # Native GX supports S8 normals with six fractional bits. The CPU skin
    # path replaces this bind-normal stream with its F32 output at draw time;
    # compact bind storage preserves precision while leaving room for UV seams.
    packed_bind_normals = uv_blocks is None
    normal_data = (b"".join(struct.pack(">3b", *vertex[5]) for vertex in vertices)
                   if packed_bind_normals else
                   b"".join(struct.pack(">3f", *(v / 64 for v in vertex[5])) for vertex in vertices))
    colour_data = b"".join(struct.pack(">4B", *vertex[2]) for vertex in vertices)
    uv_data = b"".join(struct.pack(">2h", *vertex[6]) for vertex in vertices)
    # Every stream shares one global vertex index, as dlMakeDisplayList expects.
    addresses = [0, len(position_data), len(position_data) + len(normal_data),
                 len(position_data) + len(normal_data) + len(colour_data)]
    stream_ids = [(0, 12), (1, 3 if packed_bind_normals else 12), (2, 4), (3, 4)]
    streams = b"".join(struct.pack(">IBB", address, identifier, stride)
                       for address, (identifier, stride) in zip(addresses, stream_ids))
    render_data = position_data + normal_data + colour_data + uv_data

    texstate, matstate, raster = packet_state()
    state = struct.pack(">QIIII6IBBI", texstate, matstate, native_hash("3d pointlit"),
                        raster, 0, diffuse_hash, *([0xFFFFFFFF] * 5), 1, 0, 0)
    if len(state) != 54:
        raise AssertionError("Unexpected state layout")
    indices, packets = bytearray(), bytearray()
    for packet in geometry_packets:
        packets += struct.pack(">IIHBBI", 0, len(indices), len(packet["indices"]), 0, 4, 0)
        packets += state + struct.pack(">I", 0)
        indices += struct.pack(f">{len(packet['indices'])}H", *packet["indices"])
    if len(packets) != len(geometry_packets) * 74:
        raise AssertionError("Unexpected packet layout")

    software = b"".join(vertex[0] + struct.pack(">4b", *vertex[5], 0) for vertex in vertices)
    cpu_map = b"".join(struct.pack(">II", bone, i) for i, bone in enumerate(bones))
    pair_lists = {bone: [] for bone in bones}
    for index, vertex in enumerate(vertices):
        for bone, weight in vertex[3]:
            pair_lists[bone].append(struct.pack(">HH", index, weight))
    skin = chunk(0x1B009, struct.pack(">I", 0)) + chunk(0x1B00A, bind_data)
    skin += chunk(0x1B00B, cpu_map)
    skin += b"".join(chunk(0x1B00B, b"") for _ in geometry_packets)
    skin += b"".join(chunk(0x1B00E, b"".join(pair_lists[bone])) for bone in bones)
    skin += chunk(0x1B00D, software)
    # No morph chunk: CPU vertices bypass sharedMorphBuffer[4096] entirely.
    body = chunk(0x1B001, one_chunk(native, 0x1B001))
    body += chunk(0x1B002, one_chunk(native, 0x1B002))
    body += chunk(0x1B003, struct.pack(">4I", len(geometry_packets), model_id, model_pad, 0))
    body += chunk(0x1B004, bytes(packets)) + chunk(0x1B005, streams)
    body += chunk(0x1B006, render_data) + chunk(0x1B007, bytes(indices))
    body += chunk(0x8001B008, skin)
    # A valid empty list lets Blinker::Blinker safely find no eye-swap material.
    body += chunk(0x1B012, struct.pack(">II", model_id, 0))
    result = chunk(0x8001B000, body)
    report = validate(result, diffuse_hash, uv_blocks)
    report.update({"model_id": f"0x{model_id:08x}", "diffuse_texture": f"0x{diffuse_hash:08x}",
                   "mesh_packets": [p["name"] for p in geometry_packets]})
    return result, report


def validate(data, diffuse_hash, uv_blocks):
    model = Model(data)
    maps = [c for c in walk(model.tree) if c["id"] == "0x0001b00b"]
    pair_lists = [c for c in walk(model.tree) if c["id"] == "0x0001b00e"]
    begin, end = payload(maps[0])
    entries = [struct.unpack_from(">II", data, i) for i in range(begin, end, 8)]
    count = len(model.software_positions)
    if not count or len(maps) != len(model.packets) + 1 or len(pair_lists) != len(entries):
        raise ValueError("CPU bone-map/packet/skin-pair ring contract mismatch")
    if sorted(value for _, value in entries) != list(range(len(entries))):
        raise ValueError("CPU matrix indices are not contiguous")
    if any(payload(c)[0] != payload(c)[1] for c in maps[1:]):
        raise ValueError("CPU packets must have empty per-packet GPU bone maps")
    bind_ids = {int(name, 16) for name in model.bind_matrices()}
    if not {bone for bone, _ in entries} <= bind_ids:
        raise ValueError("Unresolved CPU skinning bone")
    totals = [0] * count
    for c in pair_lists:
        begin, end = payload(c)
        for offset in range(begin, end, 4):
            index, weight = struct.unpack_from(">HH", data, offset)
            if index >= count or not weight:
                raise ValueError("Invalid skin pair")
            totals[index] += weight
    if any(total != 65535 for total in totals):
        raise ValueError("Quantized vertex weights do not sum to 65535")
    if model.morph_deltas or any(c["id"] == "0x0001b00c" for c in walk(model.tree)):
        raise ValueError("Prototype must not use the fixed-capacity morph buffer")
    allowed_uvs = set(uv_blocks.values()) if uv_blocks is not None else None
    packet_data = one_chunk(model, 0x1B004)
    render_begin, render_end = payload(next(c for c in walk(model.tree) if c["id"] == "0x0001b006"))
    for offset in range(0, len(packet_data), 74):
        raster, = struct.unpack_from(">I", packet_data, offset + 0x20)
        texture, = struct.unpack_from(">I", packet_data, offset + 0x28)
        texconfig = packet_data[offset + 0x40]
        # GLS_SolidOffset is bit 12; set would route packets through the GPU path.
        if raster & (1 << 12) or texconfig != 1 or texture != diffuse_hash:
            raise ValueError("Packet does not use expected CPU path/diffuse texture")
        num_streams = packet_data[offset + 0x0B]
        stream_offset, = struct.unpack_from(">I", packet_data, offset + 0x0C)
        stream_data = one_chunk(model, 0x1B005)
        for s in range(num_streams):
            address, stream_id, _stride = struct.unpack_from(">IBB", stream_data, stream_offset + s * 6)
            if stream_id == 3:
                for index in range(count):
                    pair = struct.unpack_from(">2h", data, render_begin + address + index * 4)
                    if allowed_uvs is not None and pair not in allowed_uvs:
                        raise ValueError(f"UV {pair} outside authored atlas blocks")
                    if allowed_uvs is None and any(not 0 <= value <= 1024 for value in pair):
                        raise ValueError(f"UV {pair} outside texture bounds")
    for packet in model.packets:
        if max(packet["indices"]) >= count or packet["primitive"] != 0:
            raise ValueError("Invalid triangle indices")
        layout = [(s["id"], s["stride"]) for s in packet["streams"]]
        if layout not in ([(0, 12), (1, 12), (2, 4), (3, 4)],
                           [(0, 12), (1, 3), (2, 4), (3, 4)]):
            raise ValueError("Unexpected CPU packet streams")
    if len(model.positions) != count:
        raise ValueError("Render and software vertex counts differ")
    for rendered, software in zip(sorted(model.positions), sorted(model.software_positions)):
        if data[rendered:rendered + 12] != data[software:software + 12]:
            raise ValueError("Render and software bind positions differ")
    return {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(),
            "packets": len(model.packets), "software_vertices": count,
            "triangles": sum(len(p["indices"]) // 3 for p in model.packets),
            "weighted_bones": len(entries), "weight_totals_valid": True,
            "morph_buffer_used": False, "skinning": "native CPU linear blend",
            "diffuse_texture": f"0x{diffuse_hash:08x}", "runtime_verified": False,
            "texture_mapping": "mesh UV" if uv_blocks is None else "colour atlas"}


def generate(source=SOURCE, output=OUT):
    document = json.loads(source.read_text())
    colors = [material["base_color"] for mesh in document["meshes"] for material in mesh["materials"]]
    pixels, blocks = build_atlas(colors)
    texture = encode_texture(ATLAS_SIZE, ATLAS_SIZE, pixels)
    bundle_path = FILES / "art/characters/Mario/Mario.glt"
    bundle, tex_hash = append_texture(bundle_path.read_bytes(), TEXTURE_NAME, texture)
    output.mkdir(parents=True, exist_ok=True)
    (output / "Mario.glt").write_bytes(bundle)
    results = {"texture": {"name": TEXTURE_NAME, "hash": f"0x{tex_hash:08x}",
                           "atlas": f"{ATLAS_SIZE}x{ATLAS_SIZE} RGB565",
                           "colour_blocks": len(blocks)}}
    for name in ("Mario.glg", "Mario_blend.glg"):
        template = (FILES / "art/characters/Mario" / name).read_bytes()
        data, report = export(document, template, tex_hash, blocks)
        (output / name).write_bytes(data)
        validate(data, tex_hash, blocks)
        results[name] = report
    (output / "export-report.json").write_text(json.dumps(results, indent=2) + "\n")
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=SOURCE)
    parser.add_argument("--output", type=Path, default=OUT)
    args = parser.parse_args()
    try:
        print(json.dumps(generate(args.source, args.output), indent=2))
    except (OSError, ValueError, KeyError, struct.error) as exc:
        parser.exit(1, f"Error: {exc}\n")
