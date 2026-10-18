#!/usr/bin/env python3
"""Install the combined Strikers mod or launch it with its required Dolphin RAM.

Copyright (c) 2026 piuzera. Licensed under the MIT License.
Uses only the Python standard library; Python 3.10 or later is required.
"""

import argparse
import bz2
import configparser
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import struct
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parent
RETAIL_DOL_SHA1 = "376d699c99b6b0949abe1b4ceccefdef7828d2b5"
MEM1_BYTES = 48 * 1024 * 1024


def digest(path, algorithm="sha256"):
    result = hashlib.new(algorithm)
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def safe_path(root, relative):
    part = PurePosixPath(relative)
    if (not part.parts or part.is_absolute() or ".." in part.parts
            or "\\" in relative or ":" in relative):
        raise ValueError(f"Unsafe package path: {relative!r}")
    path = root.joinpath(*part.parts)
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError(f"Path escapes its folder: {relative}")
    return path


def signed_offset(data):
    """BSDIFF40 uses little-endian sign-magnitude integers, not two's complement."""
    value = int.from_bytes(data, "little")
    magnitude = value & ((1 << 63) - 1)
    return -magnitude if value >> 63 else magnitude


def apply_bsdiff(source, patch, expected_size):
    """Decode standard BSDIFF40 patches without a native dependency."""
    if len(patch) < 32 or patch[:8] != b"BSDIFF40":
        raise ValueError("Not a BSDIFF40 patch")
    control_size, difference_size, target_size = (
        signed_offset(patch[i:i + 8]) for i in (8, 16, 24))
    if min(control_size, difference_size, target_size) < 0 or target_size != expected_size:
        raise ValueError("Invalid BSDIFF40 sizes")
    difference_start = 32 + control_size
    extra_start = difference_start + difference_size
    if extra_start > len(patch):
        raise ValueError("Truncated BSDIFF40 blocks")
    control = bz2.decompress(patch[32:difference_start])
    difference = bz2.decompress(patch[difference_start:extra_start])
    extra = bz2.decompress(patch[extra_start:])
    output = bytearray(target_size)
    old_position = new_position = control_position = diff_position = extra_position = 0
    while new_position < target_size:
        if control_position + 24 > len(control):
            raise ValueError("Truncated BSDIFF40 control data")
        add, copy, seek = (signed_offset(control[i:i + 8])
                           for i in range(control_position, control_position + 24, 8))
        control_position += 24
        if add < 0 or copy < 0 or new_position + add + copy > target_size:
            raise ValueError("Invalid BSDIFF40 output range")
        if diff_position + add > len(difference) or extra_position + copy > len(extra):
            raise ValueError("Truncated BSDIFF40 payload")
        for i in range(add):
            old_index = old_position + i
            previous = source[old_index] if 0 <= old_index < len(source) else 0
            output[new_position + i] = (difference[diff_position + i] + previous) & 255
        new_position += add
        old_position += add
        diff_position += add
        output[new_position:new_position + copy] = extra[extra_position:extra_position + copy]
        new_position += copy
        extra_position += copy
        old_position += seek
    if control_position != len(control) or diff_position != len(difference) or extra_position != len(extra):
        raise ValueError("Unexpected trailing BSDIFF40 data")
    return bytes(output)


def load_manifest(package=ROOT):
    manifest = json.loads((package / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("format") != 1 or manifest.get("patch_format") != "BSDIFF40":
        raise ValueError("Unsupported release manifest")
    return manifest


def check_file(root, entry):
    path = safe_path(root, entry["path"])
    if (not path.is_file() or path.is_symlink() or path.stat().st_size != entry["size"]
            or digest(path) != entry["sha256"]):
        raise ValueError(f"Missing or different file: {entry['path']}")


def verify(game, package=ROOT):
    game = game.resolve()
    manifest = load_manifest(package)
    for entry in manifest["output_files"]:
        check_file(game, entry)
    print(f"Verified {len(manifest['output_files'])} installed game files ({manifest['release']}).")


def install(source, output, package=ROOT):
    source, output = source.resolve(), output.resolve()
    manifest = load_manifest(package)
    if output.exists():
        raise ValueError("Output already exists. Choose a new output folder.")
    if output.is_relative_to(source):
        raise ValueError("Output must be outside the source extraction.")
    if not output.parent.is_dir():
        raise ValueError("The output's parent folder must already exist.")
    dol = source / "sys/main.dol"
    if not dol.is_file() or digest(dol, "sha1") != RETAIL_DOL_SHA1:
        raise ValueError("Expected an unmodified USA Rev 0 (G4QE01) extraction. main.dol does not match.")
    for folder in ("sys", "files"):
        if not (source / folder).is_dir():
            raise ValueError(f"Missing {folder}/ folder in the extraction.")
        if (source / folder).is_symlink() or any(p.is_symlink() for p in (source / folder).rglob("*")):
            raise ValueError("Source game folders must not contain symbolic links.")
    # Validate every clean input and every patch before creating output.
    for entry in manifest["source_files"]:
        check_file(source, entry)
    for entry in manifest["patches"]:
        check_file(package, {"path": entry["patch"], "size": entry["patch_size"],
                             "sha256": entry["patch_sha256"]})
        safe_path(output, entry["target"])
        safe_path(source, entry["source"])
    temporary = Path(tempfile.mkdtemp(prefix=f".{output.name}-install-", dir=output.parent))
    try:
        # Copy only inventoried game files; never copy unrelated archives, saves,
        # logs or debug symbols sitting beside an extracted disc.
        for entry in manifest["source_files"]:
            target = safe_path(temporary, entry["path"])
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(safe_path(source, entry["path"]), target)
        for entry in manifest["patches"]:
            old = safe_path(source, entry["source"]).read_bytes()
            patch = safe_path(package, entry["patch"]).read_bytes()
            new = apply_bsdiff(old, patch, entry["target_size"])
            if hashlib.sha256(new).hexdigest() != entry["target_sha256"]:
                raise ValueError(f"Patched output hash mismatch: {entry['target']}")
            target = safe_path(temporary, entry["target"])
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(new)
        verify(temporary, package)
        if output.exists():
            raise ValueError("Output appeared during installation; refusing to overwrite it.")
        temporary.rename(output)
    except BaseException:
        shutil.rmtree(temporary)
        raise
    print(f"Installed: {output}")
    print("Use this script's run command to launch with the required 48 MiB Dolphin memory.")


def find_dolphin(explicit=None):
    if explicit:
        executable = shutil.which(explicit) or explicit
        if Path(executable).is_file():
            return str(executable)
        raise ValueError(f"Dolphin executable not found: {explicit}")
    for name in ("dolphin-emu", "Dolphin.exe", "Dolphin"):
        executable = shutil.which(name)
        if executable:
            return executable
    mac = Path("/Applications/Dolphin.app/Contents/MacOS/Dolphin")
    if mac.is_file():
        return str(mac)
    raise ValueError("Dolphin not found. Pass --dolphin with the full executable path.")


def launch(game, executable=None):
    game = game.resolve()
    verify(game)
    dolphin = find_dolphin(executable)
    profile = game.parent / f"{game.name}-dolphin-user"
    config_path = profile / "Config/Dolphin.ini"
    config = configparser.ConfigParser(interpolation=None, strict=False)
    config.optionxform = str
    if config_path.exists():
        config.read(config_path, encoding="utf-8")
    if not config.has_section("Core"):
        config.add_section("Core")
    config.set("Core", "RAMOverrideEnable", "True")
    config.set("Core", "MEM1Size", str(MEM1_BYTES))
    config_path.parent.mkdir(parents=True, exist_ok=True)
    with config_path.open("w", encoding="utf-8") as stream:
        config.write(stream)
    print(f"Dolphin profile: {profile}\nRequired MEM1: 48 MiB", flush=True)
    subprocess.run([dolphin, "--user", str(profile), "--exec", str(game / "sys/main.dol"),
                    "--config", "Dolphin.Core.RAMOverrideEnable=True",
                    "--config", f"Dolphin.Core.MEM1Size={MEM1_BYTES}"], check=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    apply = commands.add_parser("install", help="Patch a clean Dolphin extraction into a new folder")
    apply.add_argument("--source", type=Path, required=True)
    apply.add_argument("--output", type=Path, required=True)
    check = commands.add_parser("verify", help="Verify all installed game files")
    check.add_argument("--game", type=Path, required=True)
    run = commands.add_parser("run", help="Launch Dolphin with the required memory override")
    run.add_argument("--game", type=Path, required=True)
    run.add_argument("--dolphin", help="Full path to Dolphin.exe / dolphin-emu / Dolphin")
    args = parser.parse_args(argv)
    try:
        if args.command == "install":
            install(args.source, args.output)
        elif args.command == "verify":
            verify(args.game)
        else:
            launch(args.game, args.dolphin)
    except (OSError, ValueError, KeyError, EOFError, struct.error, subprocess.SubprocessError) as exc:
        parser.exit(1, f"Error: {exc}\n")


if __name__ == "__main__":
    main()
