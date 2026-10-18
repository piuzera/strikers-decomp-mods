#!/usr/bin/env python3
"""Encode user-authored UI PNG art into native Strikers texture payloads.

Reads RGBA via ImageMagick (no Python imaging dependency), quantizes to the
engine's RGB5A3 / CI8 forms and reproduces each native template's exact mip
chain, tile swizzle, palette and allocation size. The staging tools consume
this for the Palmeiras crest/screens and Human sidekick portraits.
"""

import struct
import subprocess
from collections import Counter
from functools import lru_cache
from pathlib import Path

from palmeiras_texture import swizzle_16bpp


def read_rgba(path, width=None, height=None):
    """Decode a PNG to rows of (r, g, b, a) tuples via ImageMagick."""
    path = Path(path)
    with path.open("rb") as stream:
        header = stream.read(24)
    if len(header) != 24 or header[:8] != b"\x89PNG\r\n\x1a\n" or header[12:16] != b"IHDR":
        raise ValueError(f"Expected a PNG image: {path}")
    original_width, original_height = struct.unpack_from(">II", header, 16)
    if (width is None) != (height is None):
        raise ValueError("Pass both requested dimensions or neither")
    width = original_width if width is None else width
    height = original_height if height is None else height
    stat = path.stat()
    raw = _read_rgba_cached(str(path.resolve()), stat.st_mtime_ns, stat.st_size, width, height)
    pixels = list(zip(raw[0::4], raw[1::4], raw[2::4], raw[3::4]))
    return [pixels[row * width:(row + 1) * width] for row in range(height)]


@lru_cache(maxsize=48)
def _read_rgba_cached(path, modified_ns, file_size, width, height):
    command = ["magick", str(path)]
    command += ["-resize", f"{width}x{height}!"]
    command += ["-depth", "8", "rgba:-"]
    raw = subprocess.run(command, check=True, stdout=subprocess.PIPE).stdout
    if len(raw) != width * height * 4:
        raise ValueError(f"Invalid RGBA payload from {path}; expected {width}x{height}")
    return raw


def mirror(rows):
    return [row[::-1] for row in rows]


def dimensions(rows):
    return len(rows[0]), len(rows)


def quantize(pixel):
    r, g, b, a = pixel
    if a < 19:
        return 0  # One canonical fully transparent entry, without hidden RGB.
    if a >= 248:
        return 0x8000 | (round(r * 31 / 255) << 10) | (round(g * 31 / 255) << 5) | round(b * 31 / 255)
    return ((round(a * 7 / 255) << 12) | (round(r * 15 / 255) << 8)
            | (round(g * 15 / 255) << 4) | round(b * 15 / 255))


def expand(value):
    if value & 0x8000:
        r, g, b = (value >> 10) & 31, (value >> 5) & 31, value & 31
        return ((r << 3) | (r >> 2), (g << 3) | (g >> 2), (b << 3) | (b >> 2), 255)
    a, r, g, b = (value >> 12) & 7, (value >> 8) & 15, (value >> 4) & 15, value & 15
    return ((r << 4) | r, (g << 4) | g, (b << 4) | b, a * 255 // 7)


def encode_rgb5a3(rows):
    """Direct RGB5A3 texture (the crest/portrait standalone format)."""
    width, height = dimensions(rows)
    values = [quantize(pixel) for row in rows for pixel in row]
    header = struct.pack(">II5BxHH2xIII", 1, 1, 5, 5, 5, 3, 0, width, height, 0, 0, 0)
    return header + swizzle_16bpp(width, height, values)


def _halve(rows):
    height, width = len(rows), len(rows[0])
    if width == 1 and height == 1:
        return rows
    out = []
    for y in range(0, height, 2):
        line = []
        for x in range(0, width, 2):
            block = [rows[yy][xx] for yy in (y, min(y + 1, height - 1))
                     for xx in (x, min(x + 1, width - 1))]
            alpha_sum = sum(c[3] for c in block)
            rgb = tuple(round(sum(c[i] * c[3] for c in block) / alpha_sum) for i in range(3)) if alpha_sum else (0, 0, 0)
            line.append(rgb + (round(alpha_sum / len(block)),))
        out.append(line)
    return out


def _median_cut(weighted, target):
    """Weighted median-cut over expanded RGBA space; returns quantized u16 values."""
    boxes = [weighted]
    while len(boxes) < target:
        boxes.sort(key=lambda box: sum(n for _, n in box) * _box_extent(box) ** 2, reverse=True)
        box = boxes.pop(0)
        if len(box) < 2:
            boxes.append(box)
            break
        channel = max(range(4), key=lambda i: _box_extent(box, i))
        box.sort(key=lambda entry: expand(entry[0])[channel])
        half_weight = sum(n for _, n in box) / 2
        accumulated, middle = 0, 1
        for index, (_, count) in enumerate(box):
            accumulated += count
            if accumulated >= half_weight:
                middle = max(1, min(len(box) - 1, index + 1))
                break
        boxes += [box[:middle], box[middle:]]
    palette = []
    for box in boxes:
        total = sum(n for _, n in box)
        average = [round(sum(expand(v)[i] * n for v, n in box) / total) for i in range(4)]
        palette.append(quantize(tuple(average)))
    return sorted(set(palette))


def _box_extent(box, channel=None):
    channels = range(4) if channel is None else (channel,)
    widest = 0
    for i in channels:
        values = [expand(v)[i] for v, _ in box]
        widest = max(widest, max(values) - min(values))
    return widest


def build_palette(rows):
    counts = Counter(quantize(pixel) for row in rows for pixel in row)
    transparent = counts.pop(0, 0)
    distinct = sorted(counts, key=lambda value: (-counts[value], value))
    limit = 255 if transparent else 256
    colors = distinct if len(distinct) <= limit else _median_cut(list(counts.items()), limit)
    return ([0] if transparent else []) + colors


def encode_ci8(template, rows):
    """Re-encode art into a native CI8 texture, preserving the template contract."""
    if len(template) < 32:
        raise ValueError("Truncated native texture header")
    levels, fmt = struct.unpack_from(">II", template)
    width, height = struct.unpack_from(">HH", template, 14)
    if fmt != 8 or struct.unpack_from(">I", template, 20)[0] != 256:
        raise ValueError("Only 256-entry CI8 templates are supported")
    if not levels or not width or not height:
        raise ValueError("Native texture has empty dimensions/mips")
    if dimensions(rows) != (width, height):
        raise ValueError(f"Art is {dimensions(rows)}, template needs {width}x{height}")
    rgba = bytes(channel for row in rows for pixel in row for channel in pixel)
    return _encode_ci8_cached(template[:32], len(template), rgba)


@lru_cache(maxsize=48)
def _encode_ci8_cached(header, allocation_size, rgba):
    levels, _ = struct.unpack_from(">II", header)
    width, height = struct.unpack_from(">HH", header, 14)
    pixels = list(zip(rgba[0::4], rgba[1::4], rgba[2::4], rgba[3::4]))
    rows = [pixels[y * width:(y + 1) * width] for y in range(height)]
    mips = [rows]
    for _ in range(1, levels):
        mips.append(_halve(mips[-1]))
    palette = build_palette([row for mip in mips for row in mip])
    lookup = {value: index for index, value in enumerate(palette)}
    expanded = [expand(value) for value in palette]
    nearest = {}
    packed = bytearray()
    for level in range(levels):
        level_w, level_h = max(1, width >> level), max(1, height >> level)
        current = mips[level]
        if (len(current), len(current[0])) != (level_h, level_w):
            raise ValueError(f"Mip {level} produced {len(current[0])}x{len(current)}, expected {level_w}x{level_h}")
        if level_w % 8 or level_h % 4:
            raise ValueError(f"CI8 mip {level_w}x{level_h} is not 8x4-tile aligned")
        indices = bytearray(level_w * level_h)
        position = 0
        for row in current:
            for pixel in row:
                value = quantize(pixel)
                index = lookup.get(value)
                if index is None:
                    index = nearest.get(value)
                    if index is None:
                        color = expand(value)
                        index = min(range(len(expanded)),
                                    key=lambda i: sum((a - b) ** 2 for a, b in zip(color, expanded[i])))
                        nearest[value] = index
                indices[position] = index
                position += 1
        for ty in range(0, level_h, 4):
            for tx in range(0, level_w, 8):
                for row in range(4):
                    base = (ty + row) * level_w + tx
                    packed += indices[base:base + 8]
    filler = palette[-1] if palette else 0
    padded = palette + [filler] * (256 - len(palette))
    result = header + packed + struct.pack(">256H", *padded)
    if len(result) != allocation_size:
        raise ValueError(f"Encoded CI8 texture is {len(result)} bytes, template allocates {allocation_size}")
    return result


def load_art(paths, expected):
    """Read all authored inputs before a stage is archived or mutated."""
    result = {}
    for key, path in paths.items():
        result[key] = read_rgba(path)
        if dimensions(result[key]) != expected[key]:
            raise ValueError(f"{path} must be {expected[key]}, got {dimensions(result[key])}")
    return result


def source_manifest(paths):
    import hashlib
    return {key: {"path": str(path), "sha256": hashlib.sha256(Path(path).read_bytes()).hexdigest()}
            for key, path in paths.items()}


def visible_extent(rows):
    """Largest transparent-padded content fraction, for grid-icon scaling."""
    width, height = dimensions(rows)
    xs = [x for row in rows for x, pixel in enumerate(row) if pixel[3] >= 8]
    ys = [y for y, row in enumerate(rows) if any(pixel[3] >= 8 for pixel in row)]
    if not xs:
        raise ValueError("Art is fully transparent")
    return max((max(xs) - min(xs) + 1) / width, (max(ys) - min(ys) + 1) / height)
