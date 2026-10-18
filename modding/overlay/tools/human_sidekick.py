#!/usr/bin/env python3
"""Native Human sidekick assets; operates on a staged combined disc only."""

import hashlib
import json
import struct
from pathlib import Path

from export_palmeiras import ROOT, one_chunk
from export_human_player import OUTPUT as SOURCE, skin_budget, verify_export
from palmeiras_team import Fen, NULL, pack_bundle, rename_model, unpack_bundle
from palmeiras_texture import lower_hash
from native_ui_art import encode_ci8, encode_rgb5a3, load_art, mirror, read_rgba, source_manifest
from strikers_mesh import Model

REFERENCE = ROOT / "mods/palmeiras/assets/work/native-reference"
PORTRAIT = REFERENCE / "grid_sidekick_Human_128x128.png"
ART = {"portrait": PORTRAIT,
       "l": REFERENCE / "cup_sidekick_HUMAN_PALMEIRAS_l_256x256.png",
       "bg": REFERENCE / "cup_sidekick_HUMAN_PALMEIRAS_l_bg_128x128.png"}
ICON_HASH = lower_hash("fe/sidekick_icons/human")
ICON_NAMES = ("choose_sidek_toad", "choose_sidek_hammer", "choose_sidek_birdo", "choose_sidek_koopa")
HUMAN_ICON = "choose_sidek_human"


class HumanFen(Fen):
    def human_image(self, source):
        if source in self.images:
            return self.images[source]
        if self.u32(source + 0x64) != 1:
            raise ValueError("Human portrait donor must be an FEImage")
        if "human" not in self.resources:
            resource = self.clone(self.u32(source + 0x68), 0x18)
            self.put(resource + 8, 0)
            self.put(resource + 12, ICON_HASH)
            self.data[resource + 16] = 0
            self.put(resource + 20, 0)
            tail = self.u32(8)
            self.insert_after(tail, resource)
            self.pointer(8, resource)
            self.put(20, self.u32(20) + 1)
            self.resources["human"] = resource
        image = self.clone(source, 0x6C)
        self.pointer(image, NULL)
        self.pointer(image + 4, NULL)
        self.pointer(image + 0x68, self.resources["human"])
        self.set_name(image + 0x44, HUMAN_ICON)
        self.put(image + 0x40, lower_hash(HUMAN_ICON))
        self.images[source] = image
        return image

    def human_instance(self, source):
        if self.u32(source + 0x78) != 2:
            raise ValueError("Human portrait instance must be a flat image")
        new = self.clone(source, 0x84)
        image = self.human_image(self.u32(source + 12))
        self.pointer(new + 12, image)
        self.pointer(new + 0x80, self.u32(image + 0x68))
        self.pointer(new + 8, NULL)
        self.set_name(new + 0x18, HUMAN_ICON)
        self.put(new + 0x38, lower_hash(HUMAN_ICON))
        return new

    def grids(self):
        wanted = {lower_hash(name) for name in ICON_NAMES}
        result = []
        for offset in range(0, self.original_size - 0x84, 4):
            if self.u32(offset + 0x38) != lower_hash(ICON_NAMES[0]) or offset + 12 not in self.pointers:
                continue
            if self.u32(offset + 0x78) != 2:
                continue
            icons = {self.u32(i + 0x38): i for i in self.ring(offset)}
            if wanted <= icons.keys():
                result.append(icons)
        return result

    def add_human_grids(self):
        grids = self.grids()
        if not grids:
            return 0
        canonical = None
        for icons in grids:
            positions = {name: self.instance_position(icons[lower_hash(name)]) for name in ICON_NAMES}
            xs = [p[0] for p in positions.values()]
            if max(xs) - min(xs) > 1:
                canonical = positions
                break
        if canonical is None:
            raise ValueError("No stable sidekick grid for Human transition anchors")
        xs, ys = ([p[axis] for p in canonical.values()] for axis in (0, 1))
        center_y = (min(ys) + max(ys)) / 2
        step = (max(ys) - min(ys)) * 0.8
        for icons in grids:
            source = icons[lower_hash(ICON_NAMES[0])]
            new = self.human_instance(source)
            self.insert_after(source, new)
            for index, name in enumerate((*ICON_NAMES, HUMAN_ICON)):
                instance = new if index == 4 else icons[lower_hash(name)]
                anchor = canonical[ICON_NAMES[0] if index == 4 else name]
                old = self.instance_position(instance)
                target = ((min(xs) + max(xs)) / 2 if index == 4 else anchor[0],
                          center_y + (1 - index // 2) * step, anchor[2])
                position = tuple(a + b - c for a, b, c in zip(old, target, anchor))
                self.put(instance + 0x74, self.u32(instance + 0x74) | 1 | 4)
                struct.pack_into(">3f", self.data, instance + 0x3C, *position)
                library = self.u32(instance + 12)
                scale = self.floats(library + 0x20)
                struct.pack_into(">3f", self.data, instance + 0x54, scale[0] * 0.65, scale[1] * 0.65, scale[2])
                if instance != new:
                    self.reposition_animation(instance, tuple(a - b for a, b in zip(position, old)), scale=0.65)
            delta = tuple(a - b for a, b in zip(self.instance_position(new), self.instance_position(source)))
            self.clone_instance_animations(source, new, delta, scale=1)
        return len(grids)

    def alias_toad_slides(self):
        sources = [o for o in range(0, self.original_size - 0x44, 4)
                   if self.u32(o + 0x40) == lower_hash("toad") and self.name(o + 0x20) == "toad"]
        for source in sources:
            instances = [self.human_instance(i) for i in self.ring(self.u32(source + 8))]
            for index, instance in enumerate(instances):
                self.pointer(instance, instances[(index + 1) % len(instances)])
                self.pointer(instance + 4, instances[(index - 1) % len(instances)])
            new = self.clone(source, 0x44)
            self.set_name(new + 0x20, "human")
            self.put(new + 0x40, lower_hash("human"))
            self.pointer(new + 8, instances[-1] if instances else NULL)
            self.pointer(new + 12, NULL)
            self.insert_after(source, new, source + 4 in self.pointers)
        return len(sources)


def load_ui_arts():
    rows = load_art(ART, {"portrait": (128, 128), "l": (256, 256), "bg": (128, 128)})
    rows["r"] = mirror(rows["l"])
    rows["r_bg"] = mirror(rows["bg"])
    return rows


def icon_texture():
    rows = read_rgba(PORTRAIT)
    if (len(rows[0]), len(rows)) != (128, 128):
        raise ValueError("HUMAN grid art must be 128x128")
    return encode_rgb5a3(rows)


def compatible_portrait(template, rows=None):
    """Keep every native AsyncImage dimension, mip, palette and allocation size."""
    width, height = struct.unpack_from(">HH", template, 14)
    if rows is None:
        key = "bg" if (width, height) == (128, 128) else "l"
        rows = read_rgba(ART[key], width, height)
    return encode_ci8(template, rows)


def resource_aliases():
    aliases = {}
    for side in ("l", "r"):
        for suffix in ("", "_bg"):
            art = ("r_bg" if side == "r" else "bg") if suffix else side
            aliases[lower_hash(f"fe/loadingscreens/toad_{side}{suffix}")] = (lower_hash(f"fe/loadingscreens/human_{side}{suffix}"), art)
    captains = ("daisy", "donkeykong", "luigi", "mario", "peach", "waluigi", "wario", "yoshi", "mystery", "palmeiras")
    for folder in ("cup_loadingscreenssidekicks", "supercup_loadingscreenssidekicks"):
        for captain in captains:
            for side in ("l", "r"):
                for suffix in ("", "_bg"):
                    art = ("r_bg" if side == "r" else "bg") if suffix else side
                    aliases[lower_hash(f"fe/{folder}/toad_{captain}_{side}{suffix}")] = (lower_hash(f"fe/{folder}/human_{captain}_{side}{suffix}"), art)
    return aliases


def add_localization(blob):
    if blob[:4] != b"NLOC":
        return blob
    count = struct.unpack_from(">I", blob, 12)[0]
    table = [struct.unpack_from(">II", blob, 20 + i * 8) for i in range(count)]
    key = lower_hash("HUMAN")
    if key in {k for k, _ in table}:
        raise ValueError("Human localization already staged")
    strings = blob[20 + count * 8:]
    table.append((key, len(strings) // 2))
    header = bytearray(blob[:20])
    struct.pack_into(">I", header, 12, count + 1)
    return bytes(header) + b"".join(struct.pack(">II", *e) for e in sorted(table)) + strings + "HUMAN\0".encode("utf-16-be")


def stage(disc):
    disc = Path(disc)
    model_export = verify_export(SOURCE)
    ui_arts = load_ui_arts()
    target = disc / "files/art/characters/Human"
    target.mkdir()
    for suffix in ("", "_blend"):
        (target / f"Human{suffix}.glg").write_bytes(rename_model((SOURCE / f"Daisy{suffix}.glg").read_bytes(), f"human{suffix}"))
    (target / "Human.glt").write_bytes((SOURCE / "Daisy.glt").read_bytes())
    report = {"sidekick_id": 4, "character_class": 23, "native_family": "Daisy", "voice": "Luigi", "kit": "fixed green",
              "grid_packages": {}, "slide_packages": {}, "bundles": {}, "runtime_verified": False}
    report["player_model"] = model_export
    report["ui_art"] = {"sources": source_manifest(ART), "display_name": "HUMAN",
                        "derived": "Fixed green-kit artwork reused for every captain and supercup; right variants mirrored"}
    fe = disc / "files/art/fe"
    for path in fe.glob("*.fen"):
        fen = HumanFen(path.read_bytes())
        grids = fen.add_human_grids()
        slides = fen.alias_toad_slides()
        if grids or slides:
            path.write_bytes(fen.encode())
        if grids:
            report["grid_packages"][path.name] = grids
        if slides:
            report["slide_packages"][path.name] = slides
    texture = icon_texture()
    aliases = resource_aliases()
    for path in fe.iterdir():
        if path.suffix.lower() not in (".res", ".dmn"):
            continue
        sector, entries = unpack_bundle(path.read_bytes())
        additions = []
        for key, blob in entries:
            if key in aliases:
                new_key, art_key = aliases[key]
                additions.append((new_key, compatible_portrait(blob, ui_arts[art_key])))
        if path.name.lower() in ("mainui.dmn", "ingameui.res", "bootui.res"):
            additions.append((ICON_HASH, texture))
        if additions:
            if {k for k, _ in entries} & {k for k, _ in additions}:
                raise ValueError("Human resource already staged")
            path.write_bytes(pack_bundle(sector, entries + additions))
            report["bundles"][path.name] = len(additions)
    for path in fe.glob("*.loc"):
        path.write_bytes(add_localization(path.read_bytes()))
    model = Model((target / "Human.glg").read_bytes())
    verts = len(one_chunk(model, 0x1B00D)) // 16
    report["render_budget"] = {"software_vertices_per_human": verts, "human_outfielders_max": 20,
                               "position_normal_bytes_20_humans": 20 * verts * 24,
                               "resource_arena_minimum_bytes": 16 * 1024 * 1024,
                               "vertex_arena_bytes_per_frame": 4 * 1024 * 1024}
    report["render_budget"].update(skin_budget((target / "Human.glg").read_bytes()))
    report["portrait_sha256"] = hashlib.sha256(texture).hexdigest()
    (disc / "human-sidekick-report.json").write_text(json.dumps(report, indent=2) + "\n")
    return report
