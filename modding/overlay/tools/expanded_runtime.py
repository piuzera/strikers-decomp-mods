"""Shared runtime/asset requirements for expanded-team and Palmeiras builds.

This module never launches Dolphin. Keeping the formation override and RAM
profile together prevents a 10-fielder executable from using retail 4-slot data.
"""

import configparser
import hashlib
import math
import re
import shutil
from pathlib import Path

from expand_formation_sets import NUM_POSITIONS

ROOT = Path(__file__).resolve().parents[1]
MEM1_BYTES = 48 * 1024 * 1024
FORMATION_FILE = ROOT / "mods/expand-team/FormationSets.ini"


def validate_formation_file(path=FORMATION_FILE):
    player_counts = (ROOT / "include/Game/PlayerCounts.h").read_text()
    match = re.search(r"NUM_FIELDERS_PER_TEAM\s*=\s*(\d+)", player_counts)
    if not match or int(match.group(1)) != NUM_POSITIONS:
        raise ValueError("Formation position count does not match the executable's player-count header")
    sections = {"": {}}
    current = sections[""]
    for raw in path.read_text().splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        if line.startswith("[") and line.endswith("]"):
            current = sections.setdefault(line[1:-1].strip().lower(), {})
        elif "=" in line:
            key, value = line.split("=", 1)
            current[" ".join(key.lower().split())] = value.strip()
    count = int(sections[""].get("number of formation sets", "0"))
    if count <= 0:
        raise ValueError("No formation sets declared")
    formations = 0
    kickoff_positions = {}
    for index in range(count):
        section = sections.get(f"formation_set{index}", {})
        formation = 0
        while f"f{formation}_name" in section:
            if formation >= 42:
                raise ValueError("Formation set exceeds the native 42-spec scratch array")
            coordinates = []
            for player in range(NUM_POSITIONS):
                xy = []
                for axis in ("x", "y"):
                    key = f"f{formation}_p{player}_{axis}"
                    if key not in section:
                        raise ValueError(f"{path.name}: FORMATION_SET{index}/{key.upper()} missing (retail formation data is incompatible)")
                    value = float(section[key])
                    if not math.isfinite(value):
                        raise ValueError(f"Non-finite formation coordinate: {key}")
                    xy.append(value)
                if not 0 <= xy[0] <= 4 or not -1 <= xy[1] <= 1:
                    raise ValueError(f"Formation coordinate outside native AI-space bounds: {xy}")
                coordinates.append(tuple(xy))
            if index == 0 and formation in (0, 1):
                if len(set(coordinates)) != NUM_POSITIONS:
                    raise ValueError("Kickoff formation places multiple fielders at the same point")
                kickoff_positions[section[f"f{formation}_name"]] = coordinates
            formation += 1
        if formation == 0:
            raise ValueError(f"FORMATION_SET{index} has no formation definitions")
        formations += formation
    return {"source": str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "sets": count, "formations": formations, "positions_per_formation": NUM_POSITIONS,
            "kickoff_positions": kickoff_positions}


def stage_runtime_assets(files_directory):
    report = validate_formation_file()
    shutil.copy2(FORMATION_FILE, files_directory / "FormationSets.ini")
    return report


def configure_runtime_profile(profile):
    path = profile / "Config/Dolphin.ini"
    config = configparser.ConfigParser(interpolation=None, strict=False)
    config.optionxform = str
    if path.exists():
        config.read(path)
    if not config.has_section("Core"):
        config.add_section("Core")
    config.set("Core", "RAMOverrideEnable", "True")
    config.set("Core", "MEM1Size", str(MEM1_BYTES))
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as stream:
        config.write(stream)
