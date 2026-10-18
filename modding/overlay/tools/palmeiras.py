#!/usr/bin/env python3
"""Local USA build, extraction and Dolphin staging for the Palmeiras mod."""

import argparse
import hashlib
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION = "G4QE01"
RETAIL_SHA1 = "376d699c99b6b0949abe1b4ceccefdef7828d2b5"
ORIG = ROOT / "orig" / VERSION
BUILD = ROOT / "build"
MOD_BUILD = BUILD / "palmeiras"
STAGE = MOD_BUILD / "disc"
PROBE_STAGE = MOD_BUILD / "mesh-probe-disc"
PLAYER_STAGE = MOD_BUILD / "player-disc"
DTK = BUILD / "tools" / "dtk"


def run(*args):
    print("+", " ".join(map(str, args)), flush=True)
    subprocess.run(list(map(str, args)), cwd=ROOT, check=True)


def require_file(path):
    if not path.is_file():
        raise RuntimeError(f"Missing {path}")
    return path


def sha1(path):
    with require_file(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha1").hexdigest()


def verify_original():
    dol = ORIG / "sys" / "main.dol"
    if sha1(dol) != RETAIL_SHA1:
        raise RuntimeError("Original executable is not the supported USA Rev 0 main.dol")
    boot = require_file(ORIG / "sys" / "boot.bin").read_bytes()
    if len(boot) < 8 or boot[:6] != VERSION.encode() or boot[7] != 0:
        raise RuntimeError("Disc header is not USA G4QE01 Rev 0")


def dolphin():
    for name in ("dolphin-emu", "dolphin"):
        if executable := shutil.which(name):
            return executable
    raise RuntimeError("Dolphin missing. Install with: sudo pacman -S --needed dolphin-emu")


def doctor():
    for name in ("git", "python", "ninja", "dolphin-emu"):
        print(f"{name}: {shutil.which(name) or 'not installed'}")
    for path in (DTK, BUILD / "tools/wibo", BUILD / "compilers", BUILD / "binutils"):
        print(f"{path.relative_to(ROOT)}: {'present' if path.exists() else 'missing'}")
    print(f"Disc image directory: {ORIG}")
    print(f"Original main.dol: {'present' if (ORIG / 'sys/main.dol').is_file() else 'waiting for extraction'}")
    print(f"Baseline output: {BUILD / VERSION / 'main.dol'}")
    print(f"Mod output: {MOD_BUILD / VERSION / 'main.dol'}")


def extract(image):
    image = require_file(image.expanduser().resolve())
    # Do not partially overwrite an existing extraction on a retry.
    if (ORIG / "sys").exists() or any((ORIG / "files").glob("*.ini")):
        raise RuntimeError("An extraction already exists; inspect it before extracting again")
    run(require_file(DTK), "disc", "info", image)
    run(DTK, "disc", "extract", image, ORIG)
    verify_original()
    print("Verified USA Rev 0 executable and disc header.")


def build(mod):
    verify_original()
    args = [sys.executable, "configure.py", "--version", VERSION, "--map"]
    if mod:
        baseline = BUILD / VERSION / "main.dol"
        if sha1(baseline) != RETAIL_SHA1:
            raise RuntimeError("Build and verify the retail baseline before building the mod")
        args += ["--non-matching", "--build-dir", str(MOD_BUILD.relative_to(ROOT))]
        # Reuse baseline tool downloads instead of fetching a second compiler archive.
        args += [
            "--dtk", str(DTK),
            "--compilers", str(BUILD / "compilers"),
            "--binutils", str(BUILD / "binutils"),
            "--objdiff", str(BUILD / "tools/objdiff-cli"),
            "--sjiswrap", str(BUILD / "tools/sjiswrap.exe"),
            "--wrapper", str(BUILD / "tools/wibo"),
        ]
    run(*args)
    run("ninja")
    if not mod:
        if sha1(BUILD / VERSION / "main.dol") != RETAIL_SHA1:
            raise RuntimeError("Built executable does not match retail SHA-1")
        print("Retail baseline verified.")


def stage():
    verify_original()
    mod_dol = require_file(MOD_BUILD / VERSION / "main.dol")
    if STAGE.exists():
        raise RuntimeError(f"Stage already exists at {STAGE}; move or remove it before restaging")
    # Real copies keep later model edits from modifying the original extraction.
    shutil.copytree(ORIG / "sys", STAGE / "sys")
    shutil.copytree(ORIG / "files", STAGE / "files")
    shutil.copy2(mod_dol, STAGE / "sys/main.dol")
    user_ini = STAGE / "files/user.ini"
    original = user_ini.read_bytes() if user_ini.exists() else b""
    overlay = (ROOT / "mods/palmeiras/config/development.ini").read_bytes()
    # [] resets Config::Parser's section, even if the retail file ends in one.
    user_ini.write_bytes(original + b"\n" + overlay)
    print(f"Dolphin boot target: {STAGE / 'sys/main.dol'}")
    print("Development unlock override applied to staged user.ini.")


def mesh_probe():
    from strikers_mesh import Model

    verify_original()
    require_file(STAGE / "sys/main.dol")
    if PROBE_STAGE.exists():
        raise RuntimeError(f"Probe disc already exists at {PROBE_STAGE}")
    generated = {}
    for name in ("Mario.glg", "Mario_blend.glg"):
        relative = Path("art/characters/Mario") / name
        model = Model((ORIG / "files" / relative).read_bytes())
        if model.rewrite(1.0) != model.data:
            raise RuntimeError(f"Identity round-trip failed for {name}")
        generated[relative] = model.rewrite(1.15)
    shutil.copytree(STAGE, PROBE_STAGE)
    for relative, data in generated.items():
        (PROBE_STAGE / "files" / relative).write_bytes(data)
    print(f"Prepared 1.15x geometry probe: {PROBE_STAGE / 'sys/main.dol'}")
    print("The normal staged disc and original assets were not modified.")


def player_stage():
    from export_palmeiras import OUT, generate

    verify_original()
    require_file(STAGE / "sys/main.dol")
    if PLAYER_STAGE.exists():
        raise RuntimeError(f"Player disc already exists at {PLAYER_STAGE}")
    reports = generate()
    shutil.copytree(STAGE, PLAYER_STAGE)
    target = PLAYER_STAGE / "files/art/characters/Mario"
    for name in ("Mario.glg", "Mario_blend.glg", "Mario.glt"):
        shutil.copy2(OUT / name, target / name)
    print(f"Prepared footballer replacement: {PLAYER_STAGE / 'sys/main.dol'}")
    print(f"Diffuse texture: {reports['texture']['name']} ({reports['texture']['hash']})")


def launch(background, probe=False, player=False):
    disc = PLAYER_STAGE if player else PROBE_STAGE if probe else STAGE
    target = require_file(disc / "sys/main.dol")
    profile = MOD_BUILD / "dolphin-user"
    profile.mkdir(parents=True, exist_ok=True)
    args = [
        dolphin(), "--user", str(profile), "--exec", str(target),
        "--config", "Dolphin.Input.BackgroundInput=True",
    ]
    if background:
        log_path = MOD_BUILD / "dolphin-console.log"
        with log_path.open("ab") as log:
            process = subprocess.Popen(args, cwd=ROOT, stdout=log, stderr=log, start_new_session=True)
        print(f"Started Dolphin PID {process.pid}; console log: {log_path}")
    else:
        run(*args)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("doctor", help="Show dependencies and local paths")
    extraction = commands.add_parser("extract", help="Extract and verify your USA Rev 0 disc")
    extraction.add_argument("image", type=Path)
    building = commands.add_parser("build", help="Build retail baseline or mod")
    building.add_argument("--mod", action="store_true")
    commands.add_parser("stage", help="Copy extracted disc and apply development config")
    commands.add_parser("mesh-probe", help="Create an independent disc with edited Mario geometry")
    commands.add_parser("player-stage", help="Export the footballer and create its independent test disc")
    launching = commands.add_parser("run", help="Launch with an isolated Dolphin profile")
    launching.add_argument("--background", action="store_true", help="Leave Dolphin running and log console output")
    variants = launching.add_mutually_exclusive_group()
    variants.add_argument("--mesh-probe", action="store_true", help="Launch the separate geometry probe disc")
    variants.add_argument("--footballer", action="store_true", help="Launch the footballer replacement test disc")
    args = parser.parse_args()
    try:
        if args.command == "doctor":
            doctor()
        elif args.command == "extract":
            extract(args.image)
        elif args.command == "build":
            build(args.mod)
        elif args.command == "stage":
            stage()
        elif args.command == "mesh-probe":
            mesh_probe()
        elif args.command == "player-stage":
            player_stage()
        elif args.command == "run":
            launch(args.background, args.mesh_probe, args.footballer)
    except (RuntimeError, OSError, subprocess.CalledProcessError) as exc:
        parser.exit(1, f"Error: {exc}\n")


if __name__ == "__main__":
    main()
