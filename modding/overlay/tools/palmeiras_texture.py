#!/usr/bin/env python3
"""Author a native diffuse texture and append it to a retail PTLG bundle.

Texture format: RGB565, one mip level, GameCube 4x4-tile swizzled, big-endian.
The runtime path is glplatTextureAdd -> glx_MakeTexture, which reads the
0x20-byte GXTextureHeader and copies GCTextureSize bytes from +0x20.
"""

import struct

TEXTURE_NAME = "palmeiras/player"
ATLAS_SIZE = 128
BLOCK = 32
MAX_BLOCKS = (ATLAS_SIZE // BLOCK) ** 2


def lower_hash(name):
    value = 0xFFFFFFFF
    for byte in name.lower().encode("ascii"):
        value = (value * 33 + byte) & 0xFFFFFFFF
    return value


def rgb565(rgb):
    if len(rgb) != 3 or any(not 0 <= c <= 1 for c in rgb):
        raise ValueError("Colour must be RGB in [0,1]")

    def scale(value, bits):
        return round(value * ((1 << bits) - 1))

    return (scale(rgb[0], 5) << 11) | (scale(rgb[1], 6) << 5) | scale(rgb[2], 5)


def swizzle_16bpp(width, height, pixels):
    """Port of GCSwizzle's 16bpp branch: 4x4 tiles of big-endian u16s."""
    if width % 4 or height % 4:
        raise ValueError("Dimensions must be multiples of 4")
    if len(pixels) != width * height:
        raise ValueError("Pixel count mismatch")
    out = bytearray(width * height * 2)
    dest = 0
    for ty in range(0, height, 4):
        for tx in range(0, width, 4):
            for yy in range(4):
                for xx in range(4):
                    struct.pack_into(">H", out, dest, pixels[(ty + yy) * width + tx + xx])
                    dest += 2
    return bytes(out)


def unswizzle_16bpp(width, height, data):
    if len(data) != width * height * 2:
        raise ValueError("Swizzled size mismatch")
    pixels = [0] * (width * height)
    src = 0
    for ty in range(0, height, 4):
        for tx in range(0, width, 4):
            for yy in range(4):
                for xx in range(4):
                    pixels[(ty + yy) * width + tx + xx] = struct.unpack_from(">H", data, src)[0]
                    src += 2
    return pixels


def encode_texture(width, height, pixels):
    """GXTextureHeader (0x20 bytes, big-endian) followed by swizzled data."""
    header = struct.pack(">II5BxHH2xIII",
                         1,           # numLevels
                         0,           # format: GXTex_RGB565
                         5, 6, 5, 0,  # numBits
                         0,           # missingTexture (+1 pad byte)
                         width, height,
                         0,           # numEntries (no palette)
                         0, 0)        # pad[2]
    if len(header) != 0x20:
        raise AssertionError("Unexpected texture header layout")
    return header + swizzle_16bpp(width, height, pixels)


def color_bytes(color):
    """Shared sRGB byte encoding so atlas keys and vertex colours agree."""

    def srgb(value):
        return 12.92 * value if value <= 0.0031308 else 1.055 * value ** (1 / 2.4) - 0.055

    if len(color) != 4 or any(not 0 <= c <= 1 for c in color):
        raise ValueError("Material colour must be four values in [0, 1]")
    return tuple(round(srgb(c) * 255) for c in color[:3]) + (round(color[3] * 255),)


def build_atlas(colors):
    """Map each distinct material colour to a uniform block; return pixels and centres."""
    distinct = sorted({color_bytes(color)[:3] for color in colors})
    if len(distinct) > MAX_BLOCKS:
        raise ValueError(f"Atlas needs {len(distinct)} colours; capacity is {MAX_BLOCKS}")
    blocks = {}
    pixels = [0] * (ATLAS_SIZE * ATLAS_SIZE)
    for index, rgb in enumerate(distinct):
        bx, by = index % (ATLAS_SIZE // BLOCK), index // (ATLAS_SIZE // BLOCK)
        value = rgb565(tuple(c / 255 for c in rgb))
        for y in range(by * BLOCK, (by + 1) * BLOCK):
            for x in range(bx * BLOCK, (bx + 1) * BLOCK):
                pixels[y * ATLAS_SIZE + x] = value
        # UV stream is s16 with ten fractional bits; centre of the block in [0,1).
        blocks[rgb] = (round((bx * BLOCK + BLOCK / 2) / ATLAS_SIZE * 1024),
                       round((by * BLOCK + BLOCK / 2) / ATLAS_SIZE * 1024))
    return pixels, blocks


def parse_bundle(data):
    if data[:4] != b"PTLG":
        raise ValueError("Not a PTLG texture bundle")
    count = struct.unpack_from(">I", data, 4)[0]
    base = 0x20 + count * 0x10
    entries = []
    for i in range(count):
        tex_hash, offset, size = struct.unpack_from(">III", data, 0x20 + i * 0x10)
        if base + offset + size > len(data):
            raise ValueError("Bundle entry extends past end of file")
        entries.append((tex_hash, data[base + offset:base + offset + size]))
    return entries


def append_texture(data, name, texture):
    entries = parse_bundle(data)
    new_hash = lower_hash(name)
    if any(existing == new_hash for existing, _ in entries):
        raise ValueError(f"Texture name collision: {name}")
    entries.append((new_hash, texture))
    count = len(entries)
    header = struct.pack(">4sI", b"PTLG", count) + bytes(0x18)
    offset = 0
    dictionary = b""
    blobs = b""
    for tex_hash, blob in sorted(entries, key=lambda entry: entry[0]):
        if offset % 0x20:
            pad = 0x20 - (offset % 0x20)
            blobs += bytes(pad)
            offset += pad
        dictionary += struct.pack(">IIII", tex_hash, offset, len(blob), 0)
        blobs += blob
        offset += len(blob)
    return header + dictionary + blobs, new_hash


def validate_bundle(data, original):
    """Every original payload must be intact and exactly one new entry present."""
    entries = parse_bundle(data)
    originals = dict(original)
    if len(entries) != len(originals) + 1:
        raise ValueError("Appended bundle entry count mismatch")
    new = [entry for entry in entries if entry[0] not in originals]
    if len(new) != 1:
        raise ValueError("Expected exactly one new bundle entry")
    for tex_hash, blob in entries:
        if tex_hash in originals and originals[tex_hash] != blob:
            raise ValueError("Original texture payload modified")
    return new[0]
