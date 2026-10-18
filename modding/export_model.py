#!/usr/bin/env python3
"""Export a native-Daisy-bound intermediate and PNG into the example slot. MIT."""
import argparse
import json
from pathlib import Path
import shutil
import sys
import tempfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--intermediate", type=Path, required=True)
    parser.add_argument("--texture", type=Path, required=True, help="512x256 PNG")
    parser.add_argument("--replace", action="store_true", help="Archive the previous recovered/native export")
    args = parser.parse_args()
    workspace = args.workspace.resolve()
    sys.path.insert(0, str(workspace / "tools"))
    from export_palmeiras import export, one_chunk
    from export_human_player import TEXTURE_HASH, TEXTURE_NAME, verify_export
    from native_ui_art import read_rgba
    from palmeiras_texture import append_texture, encode_texture
    from strikers_mesh import Model
    document = json.loads(args.intermediate.read_text())
    rows = read_rgba(args.texture)
    if (len(rows), len(rows[0])) != (256, 512):
        raise ValueError("Texture must be 512x256")
    pixels = [(round(r * 31 / 255) << 11) | (round(g * 63 / 255) << 5) | round(b * 31 / 255)
              for row in rows for r, g, b, _ in row]
    original = workspace / "orig/G4QE01/files/art/characters/Daisy"
    # Bone keys must name real native bone IDs; the exporter does not retarget.
    import struct
    matrices = one_chunk(Model((original / "Daisy.glg").read_bytes()), 0x1B00A)
    allowed = {struct.unpack_from(">I", matrices, i)[0] for i in range(0, len(matrices), 0x44)}
    for mesh in document["meshes"]:
        for weights in mesh["weights"]:
            if any(int(key, 16) not in allowed for key in weights):
                raise ValueError("Weight references a bone outside the native Daisy rig")
    output = workspace / "build/palmeiras/human-meshy-image-v1-export"
    if output.exists() and not args.replace:
        raise ValueError("Export exists. Use --replace to archive it after successful validation.")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".creator-model-", dir=output.parent) as directory:
        temporary = Path(directory)
        texture, key = append_texture((original / "Daisy.glt").read_bytes(), TEXTURE_NAME, encode_texture(512, 256, pixels))
        assert key == TEXTURE_HASH
        (temporary / "Daisy.glt").write_bytes(texture)
        for name in ("Daisy.glg", "Daisy_blend.glg"):
            native, _ = export(document, (original / name).read_bytes(), key, None)
            (temporary / name).write_bytes(native)
        report = verify_export(temporary)
        (temporary / "creator-export-report.json").write_text(json.dumps(report, indent=2) + "\n")
        if output.exists():
            import time
            output.rename(output.with_name(output.name + f"-archive-{time.time_ns()}"))
        shutil.copytree(temporary, output)
    print(f"Validated custom export: {output}\nStage with tools/combined_mod.py stage; check real animations in Dolphin.")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, ImportError) as exc:
        raise SystemExit(f"Model export error: {exc}")
