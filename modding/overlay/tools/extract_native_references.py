#!/usr/bin/env python3
"""Extract native Mario/Toad UI textures as PNG references for polish edits.

Read-only over the retail extraction; writes PNGs plus an INDEX.json/README
into an ignored work folder. Covers only front-end UI art (grid portraits,
captain icon strips, loading screens) — never character model textures.
"""

import argparse
import json
import struct
import sys
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from palmeiras_team import Fen, FILES, ROOT, unpack_bundle
from palmeiras_texture import lower_hash, unswizzle_16bpp

WORK = ROOT / "mods/palmeiras/assets/work/native-reference"

FEN_PORTRAITS = {
    "grid_captain_mario": "choose_capt_mario",
    "grid_captain_daisy": "choose_capt_daisy",
    "grid_sidekick_toad": "choose_sidek_toad",
}
FEN_FILES = ("choose_captains_v3.fen", "cup_choose_captains_v3.fen", "custom_tournament_capt_chooser.fen")
BUNDLE_NAMES = {
    "captain_icons_mario": "fe/captain_icons/captain_icons_mario",
    "captain_icons_daisy": "fe/captain_icons/captain_icons_daisy",
    "loadingscreen_mario_l": "fe/loadingscreens/mario_l",
    "loadingscreen_mario_l_bg": "fe/loadingscreens/mario_l_bg",
    "loadingscreen_mario_l_white": "fe/loadingscreens/mario_l_white",
    "loadingscreen_mario_r": "fe/loadingscreens/mario_r",
    "cup_loadingscreen_mario_l": "fe/cup_loadingscreens/mario_l",
    "cup_sidekick_toad_mario_l": "fe/cup_loadingscreenssidekicks/toad_mario_l",
    "cup_sidekick_toad_mario_l_bg": "fe/cup_loadingscreenssidekicks/toad_mario_l_bg",
}


def png_bytes(width, height, rgba):
    """Minimal dependency-free PNG encoder (8-bit RGBA, one IDAT)."""

    def chunk(tag, data):
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))

    raw = b"".join(b"\x00" + bytes(v for pixel in row for v in pixel) for row in rgba)
    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


def expand_rgb5a3(value):
    if value & 0x8000:
        r, g, b = (value >> 10) & 31, (value >> 5) & 31, value & 31
        return ((r << 3) | (r >> 2), (g << 3) | (g >> 2), (b << 3) | (b >> 2), 255)
    a, r, g, b = (value >> 12) & 7, (value >> 8) & 15, (value >> 4) & 15, value & 15
    return ((r << 4) | r, (g << 4) | g, (b << 4) | b, a * 255 // 7)


def expand_rgb565(value):
    r, g, b = (value >> 11) & 31, (value >> 5) & 63, value & 31
    return ((r << 3) | (r >> 2), (g << 2) | (g >> 4), (b << 3) | (b >> 2), 255)


def unswizzle_ci8(width, height, data):
    out = bytearray(width * height)
    source = 0
    for ty in range(0, height, 4):
        for tx in range(0, width, 8):
            for row in range(4):
                base = (ty + row) * width + tx
                out[base:base + 8] = data[source:source + 8]
                source += 8
    return out


def decode_texture(blob):
    """Decode GXTexture level 0 to (width, height, rgba rows, format name)."""
    levels, fmt = struct.unpack_from(">II", blob)
    width, height = struct.unpack_from(">HH", blob, 14)
    palette_entries = struct.unpack_from(">I", blob, 20)[0]
    if fmt == 8 and palette_entries == 256:
        level_dims = [(max(1, width >> i), max(1, height >> i)) for i in range(levels)]
        for level_w, level_h in level_dims:
            if level_w % 8 or level_h % 4:
                raise ValueError(f"CI8 mip {level_w}x{level_h} is not 8x4-tile aligned")
        data_offset = 0x20
        palette_offset = data_offset + sum(w * h for w, h in level_dims)
        palette = [expand_rgb5a3(value) for value in
                   struct.unpack_from(f">256H", blob, palette_offset)]
        indices = unswizzle_ci8(width, height, blob[data_offset:data_offset + width * height])
        pixels = [palette[index] for index in indices]
        name = "CI8 + RGB5A3 palette"
    elif fmt in (0, 1) and palette_entries == 0:
        values = unswizzle_16bpp(width, height, blob[0x20:0x20 + width * height * 2])
        pixels = [expand_rgb565(v) if fmt == 0 else expand_rgb5a3(v) for v in values]
        name = "RGB565" if fmt == 0 else "RGB5A3"
    else:
        raise ValueError(f"Unsupported UI texture format {fmt} (palette={palette_entries})")
    rows = [pixels[row * width:(row + 1) * width] for row in range(height)]
    return width, height, rows, name, levels


def fen_portrait_hashes():
    """Texture hashes the FEN grid images actually reference, per package."""
    wanted = {lower_hash(name): label for label, name in FEN_PORTRAITS.items()}
    found = {}
    for filename in FEN_FILES:
        fen = Fen((FILES / "art/fe" / filename).read_bytes())
        for offset in range(0, fen.original_size - 0x84, 4):
            label = wanted.get(fen.u32(offset + 0x38))
            if label is None or fen.u32(offset + 0x78) != 2 or offset + 12 not in fen.pointers:
                continue
            image = fen.u32(offset + 12)
            if fen.u32(image + 0x64) != 1:
                raise ValueError(f"{filename}: expected FEImage for {label}")
            texture = fen.u32(fen.u32(image + 0x68) + 12)
            found.setdefault(label, {"texture_hash": f"0x{texture:08x}", "packages": set()})
            if found[label]["texture_hash"] != f"0x{texture:08x}":
                raise ValueError(f"{label} uses multiple texture hashes across packages")
            found[label]["packages"].add(filename)
    missing = set(FEN_PORTRAITS) - set(found)
    if missing:
        raise ValueError(f"FEN portraits not found: {sorted(missing)}")
    for label in found:
        found[label]["packages"] = sorted(found[label]["packages"])
    return found


def bundle_textures():
    """hash -> (bundle filename, blob) across the retail FE resource bundles."""
    textures = {}
    for path in sorted((FILES / "art/fe").iterdir()):
        if path.suffix.lower() not in (".res", ".dmn"):
            continue
        for key, blob in unpack_bundle(path.read_bytes())[1]:
            textures.setdefault(key, (path.name, blob))
    return textures


def extract(output=WORK):
    portraits = fen_portrait_hashes()
    textures = bundle_textures()
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    index = {}

    def save(label, blob, source):
        width, height, rows, fmt_name, levels = decode_texture(blob)
        path = output / f"{label}_{width}x{height}.png"
        path.write_bytes(png_bytes(width, height, rows))
        index[label] = {"png": path.name, "native_size": [width, height],
                        "format": fmt_name, "mip_levels": levels, "bytes": len(blob),
                        "source": source}
        print(f"{label:32s} {width}x{height:<4d} {fmt_name:22s} levels={levels} <- {source}")

    by_hash = {f"0x{key:08x}": (name, blob) for key, (name, blob) in textures.items()}
    for label, record in sorted(portraits.items()):
        name, blob = by_hash[record["texture_hash"]]
        save(label, blob, f"{name} (hash {record['texture_hash']}, from {', '.join(record['packages'])})")
        index[label]["fen_packages"] = record["packages"]
    for label, key_name in sorted(BUNDLE_NAMES.items()):
        key = lower_hash(key_name)
        if key not in textures:
            raise ValueError(f"Bundle texture missing: {key_name}")
        name, blob = textures[key]
        save(label, blob, f"{name} ({key_name})")
    (output / "INDEX.json").write_text(json.dumps(index, indent=2) + "\n")
    return index


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=WORK)
    args = parser.parse_args()
    extract(args.output.resolve())
