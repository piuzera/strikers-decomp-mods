#!/usr/bin/env python3
"""Canonical main-branch build: enlarged Palace + 11-a-side + Palmeiras slot.

build/stage/prepare never start Dolphin. Only the explicit run command launches
the normal user-controlled profile; no controller inputs are synthesized.
"""

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

import palmeiras_team
import human_sidekick
from bigfield import WLD_REL
from expanded_runtime import configure_runtime_profile
from palmeiras import require_file, verify_original

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "build/combined"
DISC = BUILD / "disc"
PROFILE = BUILD / "dolphin-user"
ORIG = ROOT / "orig/G4QE01"


def build():
    verify_original()
    subprocess.run([
        sys.executable, "configure.py", "--version", "G4QE01", "--map", "--non-matching",
        "--build-dir", str(BUILD.relative_to(ROOT)), "--dtk", "build/tools/dtk",
        "--compilers", "build/compilers", "--binutils", "build/binutils",
        "--objdiff", "build/tools/objdiff-cli", "--sjiswrap", "build/tools/sjiswrap.exe",
        "--wrapper", "build/tools/wibo",
    ], cwd=ROOT, check=True)
    subprocess.run(["ninja", "build/combined/G4QE01/main.dol"], cwd=ROOT, check=True)


def prepare_profile(profile=PROFILE, sources=None):
    """Copy normal controls/saves on first use; preserve all later user edits."""
    sources = sources if sources is not None else (
        ROOT / "build/palmeiras/dolphin-user", ROOT / "build/expand-team/dolphin-user")
    copied = []
    for directory in ("Config", "GC"):
        target = profile / directory
        if not target.exists():
            for source in sources:
                if (source / directory).is_dir():
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copytree(source / directory, target)
                    copied.append(str(source / directory))
                    break
    configure_runtime_profile(profile)
    return copied


def archive_disc(disc=DISC):
    if not disc.exists():
        return None
    if (disc / "combined-manifest.json").is_file():
        # Keep failed-run evidence with the exact old executable/symbols before
        # a subsequent user launch can replace the external console log.
        sources = (disc.parent / "dolphin-user/Logs/dolphin.log",
                   disc.parent / "team-dolphin-console.log")
        evidence = disc / "debug/runtime-evidence"
        for source in sources:
            if source.is_file():
                evidence.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, evidence / source.name)
    archive = disc.parent / "archive" / f"disc-{time.time_ns()}"
    archive.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(disc), str(archive))
    return archive


def stage():
    verify_original()
    executable = require_file(BUILD / "G4QE01/main.dol")
    # Preflight all local, ignored captain inputs before archiving a good stage.
    for name in ("Daisy.glg", "Daisy_blend.glg", "Daisy.glt"):
        require_file(palmeiras_team.PLAYER_EXPORT / name)
    palmeiras_team.verify_export(palmeiras_team.PLAYER_EXPORT)
    require_file(human_sidekick.PORTRAIT)
    palmeiras_team.load_ui_arts()
    human_sidekick.load_ui_arts()
    require_file(ORIG / "files" / WLD_REL)
    previous = archive_disc()
    copied_profile = prepare_profile()
    report = palmeiras_team.stage(disc=DISC, executable=executable, base=ORIG,
                                  profile=PROFILE, enlarge_palace=True)
    human = report["human_sidekick"]
    targets = {Path("sys/main.dol"), Path("files/user.ini"), Path("files/FormationSets.ini"),
               Path("files") / WLD_REL}
    targets.update(Path("files/art/characters/Palmeiras") / name
                   for name in ("Palmeiras.glg", "Palmeiras_blend.glg", "Palmeiras.glt"))
    targets.update(Path("files/art/fe") / name for name in report["grid_packages"])
    targets.update(Path("files/art/fe") / name for name in report["logo_packages"])
    targets.update(Path("files/art/fe") / name for name in report["bundles"])
    targets.update(Path("files/art/characters/Human") / name
                   for name in ("Human.glg", "Human_blend.glg", "Human.glt"))
    for category in ("grid_packages", "slide_packages", "bundles"):
        targets.update(Path("files/art/fe") / name for name in human[category])
    targets.update(path.relative_to(DISC) for path in (DISC / "files/art/fe").glob("*.loc"))
    hashes = {str(path): hashlib.sha256((DISC / path).read_bytes()).hexdigest() for path in sorted(targets)}
    if hashes["sys/main.dol"] != hashlib.sha256(executable.read_bytes()).hexdigest():
        raise RuntimeError("Staged executable differs from the combined build")
    symbols = BUILD / "G4QE01/main.elf"
    if symbols.exists():
        debug = DISC / "debug"
        debug.mkdir()
        shutil.copy2(symbols, debug / "main.elf")
    manifest = {
        "version": "G4QE01", "mods": ["big-field", "expand-team", "palmeiras", "human-sidekick"],
        "ram_mib": 48, "players_per_team": 11, "captain_team": "Palmeiras",
        "captain_team_id": 9, "stadium": "The Palace", "world": report["big_field"]["world"],
        "formations": report["runtime"]["formations"], "profile": str(PROFILE),
        "profile_copied_from": copied_profile, "previous_disc": str(previous) if previous else None,
        "human_sidekick_implemented": True, "human_sidekick": human,
        "player_model": report["player_model"],
        "ui_art": {"palmeiras": report["ui_art"], "human": human["ui_art"]},
        "runtime_verified": False, "sha256": hashes,
    }
    (BUILD / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    (DISC / "combined-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"Combined main-branch disc: {DISC / 'sys/main.dol'}")
    print(f"All mods staged; normal controls in {PROFILE}; Dolphin has not been launched.")
    return manifest


def prepare():
    build()
    return stage()


def run():
    require_file(DISC / "sys/main.dol")
    prepare_profile()
    palmeiras_team.launch(disc=DISC, profile=PROFILE)


def update_badge():
    path = require_file(BUILD / "manifest.json")
    manifest = json.loads(path.read_text())
    palmeiras_team.update_badge(disc=DISC)
    for name in ("BootUI.Res", "InGameUI.Res", "MainUI.Dmn", "CaptainIconsUI.Res"):
        relative = Path("files/art/fe") / name
        manifest["sha256"][str(relative)] = hashlib.sha256((DISC / relative).read_bytes()).hexdigest()
    if "ui_art" in manifest:
        source = manifest["ui_art"]["palmeiras"]["sources"]["icons"]
        source["sha256"] = hashlib.sha256(palmeiras_team.HEADER_PNG.read_bytes()).hexdigest()
    manifest["runtime_verified"] = False
    encoded = json.dumps(manifest, indent=2) + "\n"
    path.write_text(encoded)
    (DISC / "combined-manifest.json").write_text(encoded)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("build", "stage", "prepare", "run", "update-badge"))
    args = parser.parse_args(argv)
    actions = {"build": build, "stage": stage, "prepare": prepare,
               "run": run, "update-badge": update_badge}
    try:
        actions[args.command]()
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as exc:
        parser.exit(1, f"Error: {exc}\n")


if __name__ == "__main__":
    main()
