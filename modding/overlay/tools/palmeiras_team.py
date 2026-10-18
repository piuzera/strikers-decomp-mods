#!/usr/bin/env python3
"""Stage the independent tenth team, native FE crest assets and cloned Daisy kit.

FEN packages are relocated object graphs: append owned objects and extend their
pointer table rather than allocating unowned UI objects at runtime. Existing
retail assets remain present. Original disc extraction is never changed.
"""

import argparse
import configparser
import hashlib
import json
import shutil
import struct
import subprocess
from pathlib import Path

from export_palmeiras import FILES, ROOT, one_chunk
from export_human_player import OUTPUT as PLAYER_EXPORT, verify_export
from palmeiras import MOD_BUILD, STAGE, dolphin, require_file, verify_original
from palmeiras_texture import lower_hash
from native_ui_art import encode_rgb5a3, load_art, read_rgba, source_manifest
from strikers_mesh import Model, payload, walk
from expanded_runtime import MEM1_BYTES, configure_runtime_profile, stage_runtime_assets, validate_formation_file

DISC = MOD_BUILD / "team-disc-r5"
USER_PROFILE = MOD_BUILD / "dolphin-user"
WORK = ROOT / "mods/palmeiras/assets/work"
NULL = 0xFFFFFFFF
CREST_NAME = "fe/palmeiras/crest"
CREST_HASH = lower_hash(CREST_NAME)
HEADER_NAME = "fe/palmeiras/header_badge"
HEADER_HASH = lower_hash(HEADER_NAME)
# User-authored UI art (edited from the decoded native references).
REFERENCE = WORK / "native-reference"
ART = {
    "crest": REFERENCE / "grid_captain_PALMEIRAS_128x128.png",
    "icons": REFERENCE / "captain_icons_PALMEIRAS_256x64.png",
    "l": REFERENCE / "loadingscreen_PALMEIRAS_l_256x256.png",
    "l_bg": REFERENCE / "loadingscreen_PALMEIRAS_l_bg_256x256.png",
    "l_white": REFERENCE / "loadingscreen_PALMEIRAS_l_white_256x256.png",
    "r": REFERENCE / "loadingscreen_PALMEIRAS_r_256x256.png",
    "cup_l": REFERENCE / "cup_loadingscreen_PALMEIRAS_l_256x256.png",
}
HEADER_PNG = ART["icons"]
ICON_NAMES = ["choose_capt_mario", "choose_capt_daisy", "choose_capt_dk", "choose_capt_luigi",
              "choose_capt_super", "choose_capt_peach", "choose_capt_wario", "choose_capt_waluigi",
              "choose_capt_yoshi", "choose_capt_palmeiras"]


class Fen:
    def __init__(self, blob):
        self.magic, self.version, size, table_size = struct.unpack_from(">4I", blob)
        if self.magic != 0x46454E4C or len(blob) != 16 + size + table_size:
            raise ValueError("Invalid FEN header/length")
        self.data = bytearray(blob[16:16 + size])
        self.pointers = set(struct.unpack_from(f">{table_size // 4}I", blob, 16 + size))
        self.original_size = size
        # The edited PNG uses the native portrait canvas/padding, so retain its
        # authored size instead of the old full-bleed crest's half-size override.
        self.crest_scale_ratio = 1.0
        self.validate()
        self.resources = {}
        self.images = {}

    def u32(self, offset):
        return struct.unpack_from(">I", self.data, offset)[0]

    def put(self, offset, value):
        struct.pack_into(">I", self.data, offset, value)

    def pointer(self, offset, value):
        self.put(offset, value)
        self.pointers.add(offset)

    def floats(self, offset):
        return struct.unpack_from(">3f", self.data, offset)

    def name(self, offset):
        return bytes(self.data[offset:offset + 32]).split(b"\0", 1)[0].decode("ascii", "replace").lower()

    def set_name(self, offset, name):
        encoded = name.encode("ascii")
        if len(encoded) >= 32:
            raise ValueError("FEN name exceeds native field")
        self.data[offset:offset + 32] = encoded + bytes(32 - len(encoded))

    def clone(self, offset, size):
        source = bytes(self.data[offset:offset + size])
        if len(source) != size:
            raise ValueError("FEN clone outside package")
        fields = [p - offset for p in self.pointers if offset <= p < offset + size]
        self.data += bytes((-len(self.data)) % 4)
        new = len(self.data)
        self.data += source
        self.pointers.update(new + p for p in fields)
        return new

    def ring(self, head, next_offset=0):
        if head == NULL:
            return []
        result, current = [], self.u32(head + next_offset)
        while True:
            if current in result or current >= len(self.data):
                raise ValueError("Malformed FEN ring")
            result.append(current)
            if current == head:
                return result
            current = self.u32(current + next_offset)

    def insert_after(self, previous, new, doubly=True):
        following = self.u32(previous)
        self.pointer(new, following)
        self.pointer(previous, new)
        if doubly:
            self.pointer(new + 4, previous)
            self.pointer(following + 4, new)

    def crest_resource(self, source, role="grid"):
        if role not in self.resources:
            new = self.clone(source, 0x18)
            self.put(new + 8, 0)  # FERT_TEXTURE
            self.put(new + 12, HEADER_HASH if role == "header" else CREST_HASH)
            self.data[new + 16] = 0
            self.put(new + 20, 0)
            tail = self.u32(8)
            self.insert_after(tail, new)
            self.pointer(8, new)
            self.put(20, self.u32(20) + 1)
            self.resources[role] = new
        return self.resources[role]

    def crest_image(self, source, role="grid"):
        key = (source, role)
        if key in self.images:
            return self.images[key]
        if self.u32(source + 0x64) != 1:
            raise ValueError("Expected FEImage")
        resource = self.crest_resource(self.u32(source + 0x68), role)
        new = self.clone(source, 0x6C)
        self.pointer(new, NULL)
        self.pointer(new + 4, NULL)
        self.pointer(new + 0x68, resource)
        self.put(new + 0x40, lower_hash(f"palmeiras_{role}_{source:x}"))
        self.set_name(new + 0x44, "palmeiras_" + role)
        # FE quads are normalized 100x100; preserve height but make logos square.
        if role != "header":
            sx, sy, sz = self.floats(new + 8 + 0x18)
            struct.pack_into(">3f", self.data, new + 8 + 0x18, abs(sy) * (-1 if sx < 0 else 1), sy, sz)
        self.images[key] = new
        return new

    def clone_image_instance(self, source, role="grid"):
        if self.u32(source + 0x78) != 2:
            raise ValueError("Daisy logo slide is not a flat image")
        # Serialized image instances also carry the direct resource pointer at
        # +0x80 (used by AsyncImage), in addition to FEImage's pointer at +0x68.
        new = self.clone(source, 0x84)
        image = self.crest_image(self.u32(source + 0x0C), role)
        self.pointer(new + 0x0C, image)
        self.pointer(new + 0x80, self.u32(image + 0x68))
        self.pointer(new + 8, NULL)
        if role != "header" and self.u32(new + 0x74) & 4:
            sx, sy, sz = self.floats(new + 0x3C + 0x18)
            struct.pack_into(">3f", self.data, new + 0x3C + 0x18, abs(sy) * (-1 if sx < 0 else 1), sy, sz)
        return new

    def alias_daisy_slides(self):
        candidates = []
        for offset in range(0, self.original_size - 0x44, 4):
            if self.u32(offset + 0x40) == lower_hash("daisy") and self.name(offset + 0x20) == "daisy":
                candidates.append(offset)
        for old in candidates:
            instances = self.ring(self.u32(old + 8))
            new_instances = [self.clone_image_instance(i, "header" if "captain_icons" in self.name(self.u32(i + 12) + 0x44) else "grid") for i in instances]
            for index, instance in enumerate(new_instances):
                self.pointer(instance, new_instances[(index + 1) % len(new_instances)])
                self.pointer(instance + 4, new_instances[(index - 1) % len(new_instances)])
            new = self.clone(old, 0x44)
            self.set_name(new + 0x20, "palmeiras")
            self.put(new + 0x40, lower_hash("palmeiras"))
            self.pointer(new + 8, new_instances[-1] if new_instances else NULL)
            self.pointer(new + 12, NULL)  # static logo; don't animate Daisy's nodes
            self.insert_after(old, new, old + 4 in self.pointers)
        return len(candidates)

    def add_grid_icons(self):
        target = lower_hash("choose_capt_daisy")
        candidates = []
        for offset in range(0, self.original_size - 0x80, 4):
            if self.u32(offset + 0x38) == target and self.u32(offset + 0x78) == 2 and offset + 12 in self.pointers:
                candidates.append(offset)
        count = 0
        canonical = None
        for source in candidates:
            icons = {self.u32(i + 0x38): i for i in self.ring(source)}
            if all(lower_hash(name) in icons for name in ICON_NAMES[:-1]):
                positions = {name: self.instance_position(icons[lower_hash(name)]) for name in ICON_NAMES[:-1]}
                xs = [p[0] for p in positions.values()]
                if max(xs) - min(xs) > 1:
                    canonical = positions
                    break
        for source in candidates:
            ring = self.ring(source)
            icons = {self.u32(i + 0x38): i for i in ring}
            if not all(lower_hash(name) in icons for name in ICON_NAMES[:-1]):
                continue  # a logo slide can reuse the Daisy portrait's name
            count += 1
            if canonical is None:
                raise ValueError("No stable captain-grid layout to anchor transition offsets")
            new = self.clone_image_instance(source)
            self.set_name(new + 0x18, "choose_capt_palmeiras")
            self.put(new + 0x38, lower_hash("choose_capt_palmeiras"))
            self.insert_after(source, new)
            icons[lower_hash("choose_capt_palmeiras")] = new
            positions = list(canonical.values())
            xs = [p[0] for p in positions]
            ys = [p[1] for p in positions]
            for index, name in enumerate(ICON_NAMES):
                instance = icons[lower_hash(name)]
                row = index // 4
                col = index % 4 + (1 if index >= 8 else 0)
                old_pos = self.instance_position(instance)
                old_anchor = canonical["choose_capt_daisy" if instance == new else name]
                target = (min(xs) + col * (max(xs) - min(xs)) / 3,
                          max(ys) - row * (max(ys) - min(ys)) / 2, old_anchor[2])
                delta = tuple(a - b for a, b in zip(target, old_anchor))
                # Player 2's entrance stores every icon initially at x=-500.
                # Those collapsed coordinates are not its visible grid bounds.
                position = tuple(a + b for a, b in zip(old_pos, delta))
                self.put(instance + 0x74, self.u32(instance + 0x74) | 1 | 4)
                struct.pack_into(">3f", self.data, instance + 0x3C, *position)
                library = self.u32(instance + 12)
                scale = self.floats(library + 8 + 0x18)
                icon_scale = 0.72 * (self.crest_scale_ratio if instance == new else 1.0)
                struct.pack_into(">3f", self.data, instance + 0x3C + 0x18, scale[0] * icon_scale, scale[1] * icon_scale, scale[2])
                self.reposition_animation(instance, tuple(a - b for a, b in zip(position, old_pos)))
            delta = tuple(a - b for a, b in zip(self.instance_position(new), self.instance_position(source)))
            self.clone_instance_animations(source, new, delta, scale=self.crest_scale_ratio)
        return count

    def instance_position(self, offset):
        return self.floats(offset + 0x3C if self.u32(offset + 0x74) & 1 else self.u32(offset + 12) + 8)

    def reposition_animation(self, instance, translation, scale=0.72):
        # Serialized FEAnimation targets and v3 Bezier keys share the FEN pointer
        # relocation table. Preserve transition motion around the new cell center.
        for location in list(self.pointers):
            if location < 12 or location >= self.original_size or self.u32(location) != instance:
                continue
            animation = location - 12
            kind = self.u32(animation + 20)
            cast = struct.unpack_from(">H", self.data, animation + 16)[0]
            if kind not in (1, 3) or cast != 1 or animation + 24 not in self.pointers:
                continue
            # Native packages deduplicate animation keys between instances and
            # between player panels. Editing a shared key in place applies the
            # offset repeatedly, moving Player 2's Waluigi onto Super Team.
            old_keys = self.ring(self.u32(animation + 24), 0x30)
            keys = [self.clone(key, 0x38) for key in old_keys]
            for i, key in enumerate(keys):
                self.pointer(key + 0x30, keys[(i + 1) % len(keys)])
                self.pointer(key + 0x34, keys[(i - 1) % len(keys)])
            self.pointer(animation + 24, keys[-1] if keys else NULL)
            for key in keys:
                for axis in range(3):
                    for field in range(3):
                        offset = key + axis * 16 + field * 4
                        value = struct.unpack_from(">f", self.data, offset)[0]
                        if field != 0 and value == -1.0:
                            continue  # native "no Bezier control" sentinel
                        value = value + translation[axis] if kind == 1 else value * (scale if axis < 2 else 1)
                        struct.pack_into(">f", self.data, offset, value)

    def clone_instance_animations(self, source, new_instance, translation, scale=0.5):
        for location in list(self.pointers):
            if location < 12 or location >= self.original_size or self.u32(location) != source:
                continue
            animation = location - 12
            kind = self.u32(animation + 20)
            cast = struct.unpack_from(">H", self.data, animation + 16)[0]
            if kind not in range(1, 7) or cast not in (0, 1) or animation + 24 not in self.pointers:
                continue
            next_offset = 0x30 if cast == 1 else 0x10
            old_keys = self.ring(self.u32(animation + 24), next_offset)
            new_keys = [self.clone(k, next_offset + 8) for k in old_keys]
            for i, key in enumerate(new_keys):
                self.pointer(key + next_offset, new_keys[(i + 1) % len(new_keys)])
                self.pointer(key + next_offset + 4, new_keys[(i - 1) % len(new_keys)])
                if cast == 1 and kind == 1:
                    for axis in range(3):
                        for field in range(3):
                            offset = key + axis * 16 + field * 4
                            value = struct.unpack_from(">f", self.data, offset)[0]
                            if field == 0 or value != -1.0:
                                struct.pack_into(">f", self.data, offset, value + translation[axis])
                elif cast == 1 and kind == 3:
                    # The crest fills its texture canvas; character portraits
                    # have much more transparent padding. Match visible size.
                    for axis in range(2):
                        for field in range(3):
                            offset = key + axis * 16 + field * 4
                            value = struct.unpack_from(">f", self.data, offset)[0]
                            if field == 0 or value != -1.0:
                                struct.pack_into(">f", self.data, offset, value * scale)
            new = self.clone(animation, 0x1C)
            self.pointer(new + 12, new_instance)
            self.pointer(new + 24, new_keys[-1] if new_keys else NULL)
            following = self.u32(animation + 4)
            self.pointer(new + 4, following)
            self.pointer(new + 8, animation)
            self.pointer(animation + 4, new)
            self.pointer(following + 8, new)

    def validate(self):
        for location in self.pointers:
            if location % 4 or location + 4 > len(self.data):
                raise ValueError("Invalid FEN pointer-table location")
            value = self.u32(location)
            if value != NULL and value >= len(self.data):
                raise ValueError("FEN pointer target outside data")

    def encode(self):
        self.validate()
        table = sorted(self.pointers)
        return struct.pack(">4I", self.magic, self.version, len(self.data), len(table) * 4) + self.data + struct.pack(f">{len(table)}I", *table)


def unpack_bundle(data):
    sector, count, directory, start = struct.unpack_from(">4I", data)
    entries = []
    for i in range(count):
        hash_value, block, length = struct.unpack_from(">3I", data, directory * sector + i * 12)
        if block * sector + length > len(data):
            raise ValueError("Resource bundle entry out of range")
        entries.append((hash_value, data[block * sector:block * sector + length]))
    return sector, entries


def pack_bundle(sector, entries):
    directory = sector
    start = (directory + len(entries) * 12 + sector - 1) // sector * sector
    output = bytearray(start)
    struct.pack_into(">4I", output, 0, sector, len(entries), 1, start // sector)
    for index, (key, data) in enumerate(entries):
        output += bytes((-len(output)) % sector)
        struct.pack_into(">3I", output, directory + index * 12, key, len(output) // sector, len(data))
        output += data
    return bytes(output)


def add_localization(blob):
    if blob[:4] != b"NLOC":
        return blob
    count = struct.unpack_from(">I", blob, 12)[0]
    table = [struct.unpack_from(">II", blob, 20 + i * 8) for i in range(count)]
    strings = blob[20 + count * 8:]
    key = lower_hash("PALMEIRAS")
    if key in {k for k, _ in table}:
        raise ValueError("Localization entry already exists")
    table.append((key, len(strings) // 2))
    header = bytearray(blob[:20])
    struct.pack_into(">I", header, 12, count + 1)
    return bytes(header) + b"".join(struct.pack(">II", *entry) for entry in sorted(table)) + strings + "PALMEIRAS\0".encode("utf-16-be")


def crest_texture():
    """Selection-grid crest encoded directly from the user's edited PNG art."""
    rows = read_rgba(ART["crest"])
    if (len(rows[0]), len(rows)) != (128, 128):
        raise ValueError("Palmeiras grid art must be 128x128")
    return encode_rgb5a3(rows)


def header_badge_texture():
    """Use the authored captain-icons banner for the permanent nameplate too."""
    rows = read_rgba(HEADER_PNG)
    if (len(rows[0]), len(rows)) != (256, 64):
        raise ValueError("Palmeiras banner art must be 256x64")
    return encode_rgb5a3(rows)


def resource_aliases():
    """Each replaced Daisy resource now maps to a named user-art variant."""
    aliases = {lower_hash("fe/captain_icons/captain_icons_daisy"):
               (lower_hash("fe/captain_icons/captain_icons_palmeiras"), "icons")}
    for folder in ("loadingscreens", "cup_loadingscreens", "supercup_loadingscreens"):
        for side in ("l", "r"):
            for suffix in ("", "_bg", "_white"):
                art = ("" if folder == "loadingscreens" else "cup_") + side + suffix
                aliases[lower_hash(f"fe/{folder}/daisy_{side}{suffix}")] = (
                    lower_hash(f"fe/{folder}/palmeiras_{side}{suffix}"), art)
    for suffix, art in (("", "l"), ("_outline", "l_bg"), ("_white", "l_white")):
        aliases[lower_hash("fe/winners/daisy_action" + suffix)] = (
            lower_hash("fe/winners/palmeiras_action" + suffix), art)
    # Keep the four native sidekick choices available with the new captain.
    for folder in ("cup_loadingscreenssidekicks", "supercup_loadingscreenssidekicks"):
        for kick in ("toad", "koopa", "hammerbro", "birdo"):
            for side in ("l", "r"):
                for suffix in ("", "_bg"):
                    aliases[lower_hash(f"fe/{folder}/{kick}_daisy_{side}{suffix}")] = (
                        lower_hash(f"fe/{folder}/{kick}_palmeiras_{side}{suffix}"), None)
    return aliases


def load_ui_arts():
    """Validate every authored source; share supplied masks across UI families."""
    expected = {key: (256, 256) for key in ART}
    expected.update(crest=(128, 128), icons=(256, 64))
    rows = load_art(ART, expected)
    # Logos contain lettering. Reuse their authored orientation rather than
    # mirroring text when a right-side mask was not supplied.
    rows["r_bg"], rows["r_white"] = rows["l_bg"], rows["l_white"]
    rows["cup_r"] = rows["r"]
    for side in ("l", "r"):
        for suffix in ("_bg", "_white"):
            rows["cup_" + side + suffix] = rows[side + suffix]
    return rows


def compatible_crest_texture(template, rows):
    """Match the original AsyncImage allocation/format, including all mipmaps.

    glplatTextureReplace copies into the existing PlatTexture without changing
    its dimensions, format or mip count. The user's art is therefore re-encoded
    into each template's exact CI8 palette/mip allocation.
    """
    from native_ui_art import encode_ci8
    return encode_ci8(template, rows)


def rename_model(data, name):
    model = Model(data)
    result = bytearray(data)
    model_id = lower_hash(name)
    for chunk in walk(model.tree):
        begin, _ = payload(chunk)
        if chunk["id"] == "0x0001b003":
            struct.pack_into(">I", result, begin + 4, model_id)
        elif chunk["id"] == "0x0001b012":
            struct.pack_into(">I", result, begin, model_id)
    assert one_chunk(Model(bytes(result)), 0x1B00A) == one_chunk(model, 0x1B00A)
    return bytes(result)


def stage(disc=DISC, executable=None, base=STAGE, profile=USER_PROFILE, enlarge_palace=False):
    verify_original()
    validate_formation_file()
    executable = require_file(executable or MOD_BUILD / "G4QE01/main.dol")
    require_file(base / "sys/main.dol")
    if disc.exists():
        raise RuntimeError("Independent team disc exists; preserve it before restaging")
    source = PLAYER_EXPORT
    for name in ("Daisy.glg", "Daisy_blend.glg", "Daisy.glt"):
        require_file(source / name)
    model_export = verify_export(source)
    ui_arts = load_ui_arts()
    crest = crest_texture()
    header_badge = header_badge_texture()
    report = {"team_id": 9, "character_base": "Daisy", "voice": "Luigi", "grid_packages": {}, "logo_packages": {}, "bundles": {}}
    report["player_model"] = model_export
    report["ui_art"] = {"sources": source_manifest(ART), "grid_scale_ratio": 1.0,
                        "derived": {"r_bg": "l_bg", "r_white": "l_white",
                                    "cup_masks": "friendly masks", "supercup": "cup artwork",
                                    "winners": "friendly main/background/white artwork"}}
    shutil.copytree(base, disc)
    # Public combined staging retains retail progression. Palmeiras, Human and
    # The Palace do not require the historical givealltrophies development flag.
    formations = stage_runtime_assets(disc / "files")
    shutil.copy2(executable, disc / "sys/main.dol")
    report["executable_sha256"] = hashlib.sha256(executable.read_bytes()).hexdigest()
    if enlarge_palace:
        from bigfield import WLD_REL, edit_wld, verify_wld
        world = edit_wld((FILES / WLD_REL).read_bytes())
        report["big_field"] = {"stadium": "The Palace", "world": verify_wld(world),
                               "sha256": hashlib.sha256(world).hexdigest()}
        (disc / "files" / WLD_REL).write_bytes(world)
    else:
        report["big_field"] = None
    # Restore all earlier replacement slots and keep the new captain isolated.
    for character in ("Mario", "SuperTeam", "Daisy", "Peach"):
        for name in (f"{character}.glg", f"{character}_blend.glg", f"{character}.glt"):
            relative = Path("art/characters") / character / name
            shutil.copy2(FILES / relative, disc / "files" / relative)
    target = disc / "files/art/characters/Palmeiras"
    target.mkdir()
    for suffix in ("", "_blend"):
        data = rename_model((source / f"Daisy{suffix}.glg").read_bytes(), f"palmeiras{suffix}")
        (target / f"Palmeiras{suffix}.glg").write_bytes(data)
    shutil.copy2(source / "Daisy.glt", target / "Palmeiras.glt")
    for path in (FILES / "art/fe").glob("*.fen"):
        fen = Fen(path.read_bytes())
        logos = fen.alias_daisy_slides()
        grids = fen.add_grid_icons()
        if logos or grids:
            (disc / "files/art/fe" / path.name).write_bytes(fen.encode())
        if logos:
            report["logo_packages"][path.name] = logos
        if grids:
            report["grid_packages"][path.name] = grids
    aliases = resource_aliases()
    permanent = {"mainui.dmn", "ingameui.res", "bootui.res"}
    for path in (FILES / "art/fe").iterdir():
        if path.suffix.lower() not in (".res", ".dmn"):
            continue
        sector, entries = unpack_bundle(path.read_bytes())
        additions = []
        for key, blob in entries:
            if key in aliases:
                new_key, art_key = aliases[key]
                additions.append((new_key, compatible_crest_texture(blob, ui_arts[art_key]) if art_key else blob))
        if path.name.lower() in permanent:
            additions.append((CREST_HASH, crest))
            additions.append((HEADER_HASH, header_badge))
        if additions:
            existing = {key for key, _ in entries}
            assert not any(key in existing for key, _ in additions)
            (disc / "files/art/fe" / path.name).write_bytes(pack_bundle(sector, entries + additions))
            report["bundles"][path.name] = len(additions)
    for path in (FILES / "art/fe").glob("*.loc"):
        (disc / "files/art/fe" / path.name).write_bytes(add_localization(path.read_bytes()))
    # The current executable exposes five sidekick choices in every selector.
    # Stage the matching overlay for both canonical and standalone team builds.
    from human_sidekick import stage as stage_human
    report["human_sidekick"] = stage_human(disc)
    report["crest_sha256"] = hashlib.sha256(crest).hexdigest()
    report["header_badge_png"] = str(HEADER_PNG.relative_to(ROOT))
    report["disc"] = str(disc)
    report["runtime_verified"] = False
    report["runtime"] = {"profile": str(profile), "mem1_bytes": MEM1_BYTES,
                         "reason": "Existing expanded-team executable requires the 48 MiB Dolphin/PC runtime",
                         "formations": formations}
    (disc / "palmeiras-team-report.json").write_text(json.dumps(report, indent=2) + "\n")
    (disc.parent / "team-export-report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    return report


def launch_arguments(target, profile=USER_PROFILE):
    return [dolphin(), "--user", str(profile), "--exec", str(target),
            "--config", "Dolphin.Core.RAMOverrideEnable=True",
            "--config", f"Dolphin.Core.MEM1Size={MEM1_BYTES}",
            "--config", "Dolphin.Input.BackgroundInput=True"]


def update_badge(disc=DISC):
    require_file(disc / "sys/main.dol")
    require_file(HEADER_PNG)
    texture = header_badge_texture()
    for name in ("BootUI.Res", "InGameUI.Res", "MainUI.Dmn"):
        path = disc / "files/art/fe" / name
        sector, entries = unpack_bundle(path.read_bytes())
        if HEADER_HASH not in dict(entries):
            raise ValueError(f"Separate header badge resource missing from {name}")
        revised = [(key, texture if key == HEADER_HASH else blob) for key, blob in entries]
        path.write_bytes(pack_bundle(sector, revised))
    # This authored banner feeds both permanent nameplates and the async strip.
    path = disc / "files/art/fe/CaptainIconsUI.Res"
    sector, entries = unpack_bundle(path.read_bytes())
    target = lower_hash("fe/captain_icons/captain_icons_palmeiras")
    if target not in dict(entries):
        raise ValueError("Palmeiras asynchronous captain banner is missing")
    rows = read_rgba(HEADER_PNG)
    revised = [(key, compatible_crest_texture(blob, rows) if key == target else blob) for key, blob in entries]
    path.write_bytes(pack_bundle(sector, revised))
    print(f"Updated nameplate and async banner from {HEADER_PNG}; restart the game to see the edit.")


def launch(disc=DISC, profile=USER_PROFILE):
    target = require_file(disc / "sys/main.dol")
    # Use the user's normal keyboard/controller profile, never the QA pipe pad.
    # Enable evidence for a user-driven load attempt without suppressing alerts.
    configure_runtime_profile(profile)
    logger_path = profile / "Config/Logger.ini"
    logger = configparser.ConfigParser()
    logger.optionxform = str
    if logger_path.exists():
        logger.read(logger_path)
    for section in ("Logs", "Options"):
        if not logger.has_section(section):
            logger.add_section(section)
    for channel in ("OSREPORT", "OSREPORT_HLE", "COMMON", "PowerPC", "CORE", "DVD", "HLE", "Video"):
        logger.set("Logs", channel, "True")
    logger.set("Options", "WriteToFile", "True")
    logger.set("Options", "Verbosity", "4")
    logger_path.parent.mkdir(parents=True, exist_ok=True)
    with logger_path.open("w") as stream:
        logger.write(stream)
    with (disc.parent / "team-dolphin-console.log").open("ab") as log:
        process = subprocess.Popen(launch_arguments(target, profile), stdout=log, stderr=log, start_new_session=True)
    print(f"Started independent Palmeiras team disc: PID {process.pid}")
    print(f"Expanded-team Dolphin RAM: {MEM1_BYTES // (1024 * 1024)} MiB; user controls unchanged")
    print(f"Normal controller profile; runtime log: {profile / 'Logs/dolphin.log'}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("stage", "run", "update-badge"))
    args = parser.parse_args()
    try:
        if args.command == "stage":
            stage()
        elif args.command == "update-badge":
            update_badge()
        else:
            launch()
    except (OSError, ValueError, RuntimeError) as exc:
        parser.exit(1, f"Error: {exc}\n")
