#!/usr/bin/env python3
"""Export and verify the optimized, image-based Human shared by both roles.

Consumes Blender's local Daisy-bound intermediate and 512x256 RGB565 albedo.
The canonical staging tools use this one verified source for captain/sidekick.
"""

import argparse
import hashlib
import json
import shutil
import struct
import time
from pathlib import Path

from export_palmeiras import ROOT, FILES, export, one_chunk, validate
from palmeiras_texture import append_texture, lower_hash, parse_bundle
from strikers_mesh import Model, walk, payload

WORK = ROOT / "mods/palmeiras/assets/work/human-meshy-image-v1"
OUTPUT = ROOT / "build/palmeiras/human-meshy-image-v1-export"
TEXTURE_NAME = "human/meshy_v6_image_v1"
TEXTURE_HASH = lower_hash(TEXTURE_NAME)
REQUIRED = ("Daisy.glg", "Daisy_blend.glg", "Daisy.glt")


def skin_budget(data):
    model = Model(data)
    counts = [0] * len(model.software_positions)
    for chunk in walk(model.tree):
        if chunk["id"] == "0x0001b00e":
            begin, end = payload(chunk)
            for offset in range(begin, end, 4):
                index, weight = struct.unpack_from(">HH", data, offset)
                if index >= len(counts) or not weight:
                    raise ValueError("Invalid Human influence entry")
                counts[index] += 1
    if not counts:
        raise ValueError("Human must contain skinned vertices")
    pairs = sum(counts)
    return {"skin_pairs": pairs, "maximum_influences": max(counts),
            "mean_influences": pairs / len(counts)}


def validate_model(data):
    report = validate(data, TEXTURE_HASH, None)
    report.update(skin_budget(data))
    if report["software_vertices"] > 2000 or report["triangles"] > 2500:
        raise ValueError("Human model exceeds the vertex/triangle budget")
    if report["maximum_influences"] > 2 or report["mean_influences"] > 1.5:
        raise ValueError("Human model exceeds the CPU-skinning influence budget")
    if report["bytes"] >= 0x80000:
        raise ValueError("Human GLG exceeds the model loader window")
    return report


def verify_export(source=OUTPUT):
    source = Path(source)
    textures = dict(parse_bundle((source / "Daisy.glt").read_bytes()))
    if TEXTURE_HASH not in textures:
        raise ValueError("Optimized Human texture is missing")
    texture = textures[TEXTURE_HASH]
    if (len(texture) >= 0x40800 or struct.unpack_from(">HH", texture, 14) != (512, 256)
            or struct.unpack_from(">II", texture) != (1, 0)):
        raise ValueError("Human texture violates the native loader dimensions/size")
    retail = dict(parse_bundle((FILES / "art/characters/Daisy/Daisy.glt").read_bytes()))
    if any(textures.get(key) != value for key, value in retail.items()):
        raise ValueError("Human bundle modified a retained native texture")
    result = {"source": str(source), "revision": "meshy-v6-image-v1",
              "texture_hash": f"0x{TEXTURE_HASH:08x}", "models": {}}
    for name in REQUIRED[:2]:
        data = (source / name).read_bytes()
        stats = validate_model(data)
        template = Model((FILES / "art/characters/Daisy" / name).read_bytes())
        if one_chunk(Model(data), 0x1B00A) != one_chunk(template, 0x1B00A):
            raise ValueError("Human native Daisy bind matrices changed")
        result["models"][name] = stats
    return result


def generate(output=OUTPUT, replace=False):
    output = Path(output)
    if (output / "export-report.json").exists():
        if not replace:
            raise RuntimeError("Export already exists; preserve/version it before regenerating")
    document = json.loads((WORK / "human-game-intermediate.json").read_text())
    qa = json.loads((WORK / "human-game-validation.json").read_text())
    if not qa.get("synthetic_pose_checks"):
        raise ValueError("Blender deformation validation is missing")
    texture = (WORK / "human-game-rgb565.bin").read_bytes()
    original = (FILES / "art/characters/Daisy/Daisy.glt").read_bytes()
    bundle, texture_hash = append_texture(original, TEXTURE_NAME, texture)
    generated = {"Daisy.glt": bundle}
    report = {"revision": "meshy-v6-image-v1", "native_family": "Daisy", "voice": "Luigi",
              "roles": ["Palmeiras captain", "Human sidekick"], "runtime_verified": False,
              "texture_name": TEXTURE_NAME, "texture_hash": f"0x{texture_hash:08x}",
              "reference_sha256": hashlib.sha256((WORK / "Human_Vetted_Artwork.png").read_bytes()).hexdigest(),
              "blender_qa": qa, "models": {}}
    report["preparation"] = json.loads((WORK / "prepared-report.json").read_text())
    report["binding"] = json.loads((WORK / "binding-report.json").read_text())
    for name in REQUIRED[:2]:
        data, _ = export(document, (FILES / "art/characters/Daisy" / name).read_bytes(), texture_hash, None)
        report["models"][name] = validate_model(data)
        generated[name] = data
    previous = ROOT / "build/palmeiras/daisy-player-v2-textured-export/Daisy.glg"
    if previous.is_file():
        old = skin_budget(previous.read_bytes())
        new = report["models"]["Daisy.glg"]
        report["previous_skin_pairs_per_human"] = old["skin_pairs"]
        report["skin_pair_work_reduction_fraction"] = 1 - new["skin_pairs"] / old["skin_pairs"]
    if (output / "export-report.json").exists():
        shutil.move(str(output), str(output.with_name(output.name + f"-archive-{time.time_ns()}")))
    output.mkdir(parents=True, exist_ok=True)
    for name, data in generated.items():
        (output / name).write_bytes(data)
    (output / "export-report.json").write_text(json.dumps(report, indent=2) + "\n")
    verify_export(output)
    print(json.dumps(report, indent=2))
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--replace", action="store_true", help="Archive this generated export before regenerating")
    args = parser.parse_args()
    print(json.dumps(verify_export(), indent=2)) if args.verify else generate(replace=args.replace)
