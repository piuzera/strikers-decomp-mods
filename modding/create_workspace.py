#!/usr/bin/env python3
"""Bootstrap an editable Strikers workspace. Original utility: MIT licensed."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys

KIT = Path(__file__).resolve().parent
PUBLIC = KIT.parent


def run(*args, cwd=None):
    subprocess.run([str(a) for a in args], cwd=cwd, check=True)


def recover(workspace, installed):
    """Decode editable PNGs and restore Daisy-identity export donors locally."""
    sys.path.insert(0, str(workspace / "tools"))
    import palmeiras_team as team
    import human_sidekick as human
    from export_human_player import verify_export
    from extract_native_references import decode_texture, png_bytes
    from palmeiras_texture import lower_hash

    export = workspace / "build/palmeiras/human-meshy-image-v1-export"
    export.mkdir(parents=True)
    for suffix in ("", "_blend"):
        data = (installed / f"files/art/characters/Palmeiras/Palmeiras{suffix}.glg").read_bytes()
        (export / f"Daisy{suffix}.glg").write_bytes(team.rename_model(data, f"daisy{suffix}"))
    shutil.copyfile(installed / "files/art/characters/Palmeiras/Palmeiras.glt", export / "Daisy.glt")
    verify_export(export)
    textures = {}
    for path in sorted((installed / "files/art/fe").iterdir()):
        if path.suffix.lower() in (".res", ".dmn"):
            for key, blob in team.unpack_bundle(path.read_bytes())[1]:
                textures.setdefault(key, blob)
    artwork = {
        team.ART["crest"]: "fe/palmeiras/crest",
        team.ART["icons"]: "fe/palmeiras/header_badge",
        team.ART["l"]: "fe/loadingscreens/palmeiras_l",
        team.ART["l_bg"]: "fe/loadingscreens/palmeiras_l_bg",
        team.ART["l_white"]: "fe/loadingscreens/palmeiras_l_white",
        team.ART["r"]: "fe/loadingscreens/palmeiras_r",
        team.ART["cup_l"]: "fe/cup_loadingscreens/palmeiras_l",
        human.ART["portrait"]: "fe/sidekick_icons/human",
        human.ART["l"]: "fe/cup_loadingscreenssidekicks/human_palmeiras_l",
        human.ART["bg"]: "fe/cup_loadingscreenssidekicks/human_palmeiras_l_bg",
    }
    for path, name in artwork.items():
        width, height, rows, _, _ = decode_texture(textures[lower_hash(name)])
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(png_bytes(width, height, rows))
    print(f"Recovered {len(artwork)} editable PNGs and validated the native Human export.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True, help="New folder, outside both game folders")
    parser.add_argument("--clean", type=Path, required=True, help="Clean USA Rev 0 extraction")
    parser.add_argument("--installed", type=Path, required=True, help="Verified installed v1.0.0 game")
    parser.add_argument("--upstream", help="Optional local Git mirror/URL instead of the pinned upstream URL")
    args = parser.parse_args()
    if sys.version_info < (3, 11):
        parser.error("Creator tools require Python 3.11+ (playing only requires 3.10+).")
    workspace, clean, installed = (p.resolve() for p in (args.workspace, args.clean, args.installed))
    if workspace.exists() or not workspace.parent.is_dir():
        parser.error("Choose a new workspace whose parent folder already exists.")
    if any(workspace.is_relative_to(root) for root in (clean, installed, PUBLIC)):
        parser.error("Workspace must be outside this public repository and both game folders.")
    meta = json.loads((KIT / "source/upstream.json").read_text())
    patch = KIT / "source/combined-mod.patch"
    if hashlib.sha256(patch.read_bytes()).hexdigest() != meta["patch_sha256"]:
        parser.error("Source patch checksum mismatch")
    for relative, digest in meta["overlay_sha256"].items():
        if hashlib.sha256((KIT / "overlay" / relative).read_bytes()).hexdigest() != digest:
            parser.error(f"Overlay checksum mismatch: {relative}")
    spec = importlib.util.spec_from_file_location("release_installer", PUBLIC / "install.py")
    installer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(installer)
    for entry in installer.load_manifest()["source_files"]:
        installer.check_file(clean, entry)
    installer.verify(installed)
    run("git", "clone", "--no-checkout", args.upstream or meta["url"], workspace)
    run("git", "checkout", "--detach", meta["commit"], cwd=workspace)
    run("git", "submodule", "update", "--init", "--recursive", cwd=workspace)
    run("git", "apply", "--check", patch, cwd=workspace)
    run("git", "apply", patch, cwd=workspace)
    for relative in meta["overlay_sha256"]:
        target = workspace / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(KIT / "overlay" / relative, target)
    for folder in ("sys", "files"):
        shutil.copytree(clean / folder, workspace / "orig/G4QE01" / folder, dirs_exist_ok=True)
    recover(workspace, installed)
    print(f"Workspace ready: {workspace}\nNext: follow modding/guides/getting-started.md to configure/build.")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as exc:
        raise SystemExit(f"Workspace error: {exc}\nA failed new workspace is retained for inspection; retry with a new folder.")
