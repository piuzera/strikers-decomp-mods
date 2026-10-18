#!/usr/bin/env python3
"""Small repeatable edits and patch packaging for creator workspaces. MIT."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import struct
import subprocess
import sys

KIT = Path(__file__).resolve().parent


def load_tools(workspace):
    sys.path.insert(0, str(workspace.resolve() / "tools"))


def edit_name(game, key, text):
    """Replace a display value; retain the binary identity/hash and string offsets."""
    from palmeiras_texture import lower_hash
    modified = 0
    for path in (game / "files/art/fe").glob("*.loc"):
        blob = path.read_bytes()
        if blob[:4] != b"NLOC":
            continue
        count = struct.unpack_from(">I", blob, 12)[0]
        table = [list(struct.unpack_from(">II", blob, 20 + i * 8)) for i in range(count)]
        found = next((entry for entry in table if entry[0] == lower_hash(key)), None)
        if found is None:
            continue
        strings = blob[20 + count * 8:]
        found[1] = len(strings) // 2
        path.write_bytes(blob[:20] + b"".join(struct.pack(">II", *e) for e in table)
                         + strings + (text + "\0").encode("utf-16-be"))
        modified += 1
    if not modified:
        raise ValueError(f"Localization key not found: {key}")
    print(f"Changed {key}'s displayed value in {modified} localization files; identity unchanged.")


def badge(workspace, png):
    import palmeiras_team as team
    png = png.resolve()
    team.HEADER_PNG = png
    team.ART["icons"] = png
    team.update_badge(disc=workspace / "build/combined/disc")


def package(workspace, output, release):
    import bsdiff4  # Packaging only: uv run --with bsdiff4==1.2.6 ...
    clean = workspace / "orig/G4QE01"
    game = workspace / "build/combined/disc"
    if output.exists():
        raise ValueError("Package output already exists; choose a new folder.")
    if not clean.is_dir() or not game.is_dir():
        raise ValueError("Workspace must have a clean extraction and staged build/combined/disc.")
    if output.is_relative_to(workspace):
        raise ValueError("Keep distributable packages outside the development workspace.")
    base = KIT.parent
    spec = importlib.util.spec_from_file_location("release_installer", base / "install.py")
    installer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(installer)
    manifest = installer.load_manifest()
    source_paths = {e["path"] for e in manifest["source_files"]}
    for entry in manifest["source_files"]:
        installer.check_file(clean, entry)
    paths = sorted(p.relative_to(game).as_posix() for folder in ("sys", "files")
                   for p in (game / folder).rglob("*") if p.is_file())
    if not source_paths <= set(paths):
        raise ValueError("Deleting original game files is not supported by this package format.")
    for relative in paths:
        if (game / relative).is_symlink():
            raise ValueError("Staged game must not contain symlinks")
    result = {k: v for k, v in manifest.items() if k not in ("patches", "output_files", "release", "project_status")}
    result.update(release=release, patches=[], output_files=[])
    output.mkdir(parents=True)
    (output / "patches").mkdir()
    for relative in paths:
        new = (game / relative).read_bytes()
        result["output_files"].append({"path": relative, "size": len(new), "sha256": hashlib.sha256(new).hexdigest()})
        source = relative
        if relative not in source_paths:
            # New native files need an explicit donor in package-donors.json.
            mapping_file = workspace / "package-donors.json"
            mapping = json.loads(mapping_file.read_text()) if mapping_file.exists() else {}
            default = next((p["source"] for p in manifest["patches"] if p["target"] == relative), None)
            source = mapping.get(relative, default)
            if source not in source_paths:
                raise ValueError(f"Declare a clean retail donor for {relative} in package-donors.json")
        old = (clean / source).read_bytes()
        if relative in source_paths and old == new:
            continue
        patch = bsdiff4.diff(old, new)
        if installer.apply_bsdiff(old, patch, len(new)) != new:
            raise ValueError(f"Patch round-trip failed: {relative}")
        name = f"patches/{len(result['patches']):03d}.bsdiff"
        (output / name).write_bytes(patch)
        result["patches"].append({"source": source, "target": relative, "patch": name,
                                  "patch_size": len(patch), "patch_sha256": hashlib.sha256(patch).hexdigest(),
                                  "target_size": len(new), "target_sha256": hashlib.sha256(new).hexdigest()})
    (output / "manifest.json").write_text(json.dumps(result, indent=2) + "\n")
    for name in ("install.py", "LICENSE", "THIRD_PARTY_NOTICES.md"):
        shutil.copyfile(base / name, output / name)
    shutil.copytree(base / "licenses", output / "licenses")
    (output / "README.md").write_text(f"# {release}\n\nCustom patch package. Supply your own clean USA Rev 0 game.\n\n"
                                      "Install: `python install.py install --source CLEAN --output GAME`\n\n"
                                      "Run: `python install.py run --game GAME --dolphin DOLPHIN_EXECUTABLE`\n\n"
                                      "Requires Dolphin with 48 MiB MEM1; GameCube hardware is unsupported.\n"
                                      "See THIRD_PARTY_NOTICES.md. Add your own credits, mod description and testing notes before sharing.\n")
    print(f"Created {len(result['patches'])} verified patches at {output}. Test a clean install before sharing.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    commands = parser.add_subparsers(dest="command", required=True)
    name = commands.add_parser("name", help="Change an existing display name, not a roster ID")
    name.add_argument("--key", choices=("PALMEIRAS", "HUMAN"), required=True)
    name.add_argument("--text", required=True)
    art = commands.add_parser("badge", help="Repack a 256x64 PNG into the captain badge/banner resources")
    art.add_argument("--png", type=Path, required=True)
    run = commands.add_parser("run", help="Launch the custom stage using its workspace profile")
    run.add_argument("--dolphin", required=True)
    pack = commands.add_parser("package", help="Build clean-input patches for the current custom stage")
    pack.add_argument("--output", type=Path, required=True)
    pack.add_argument("--release", required=True)
    args = parser.parse_args()
    workspace = args.workspace.resolve()
    if not (workspace / "tools/palmeiras_team.py").is_file():
        parser.error("Not a bootstrapped creator workspace")
    load_tools(workspace)
    if args.command == "name":
        if not args.text.strip() or "\0" in args.text:
            parser.error("Display text must be nonempty and contain no NUL")
        edit_name(workspace / "build/combined/disc", args.key, args.text)
    elif args.command == "badge":
        badge(workspace, args.png)
    elif args.command == "package":
        package(workspace, args.output.resolve(), args.release)
    else:
        from expanded_runtime import configure_runtime_profile
        profile = workspace / "build/combined/dolphin-user"
        configure_runtime_profile(profile)
        subprocess.run([args.dolphin, "--user", str(profile), "--exec", str(workspace / "build/combined/disc/sys/main.dol"),
                        "--config", "Dolphin.Core.RAMOverrideEnable=True", "--config", "Dolphin.Core.MEM1Size=50331648"], check=True)


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, ImportError, KeyError, subprocess.SubprocessError) as exc:
        raise SystemExit(f"Creator error: {exc}")
