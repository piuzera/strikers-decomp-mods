#!/usr/bin/env python3
"""Expand FormationSets.ini from 4 to 10 positions per formation.

The retail file defines 4 outfield positions (P0-P3) per formation. This tool
adds six defensive positions (P4-P9) behind the rearmost existing position so a
10-outfield-player team has a full formation. The output is a drop-in
FormationSets.ini.
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "orig/G4QE01/files/FormationSets.ini"
OUTPUT = ROOT / "mods/expand-team/FormationSets.ini"

NUM_POSITIONS = 10


def expand(text):
    lines = text.splitlines(keepends=True)
    out = []
    # Per-formation position accumulator: key "F<N>" -> dict(pos -> (x, y)).
    positions = {}
    for line in lines:
        stripped = line.strip()
        match = re.match(r"^(\w+)_P(\d+)_(X|Y)\s*=\s*([-0-9.]+)", stripped)
        name_match = re.match(r"^(\w+)_NAME\s*=", stripped)
        if name_match:
            # Flush the previous formation's extra positions before its NAME.
            formation = name_match.group(1)
            out.append(line)
            continue
        if match:
            formation = match.group(1)
            pos = int(match.group(2))
            axis = match.group(3)
            value = float(match.group(4))
            positions.setdefault(formation, {})
            positions[formation].setdefault(pos, {})[axis] = value
            out.append(line)
            if axis == "Y" and pos == 3:
                # Last of the retail positions: append P4..P9 now.
                out.extend(_extra_position_lines(line, positions[formation]))
            continue
        out.append(line)
    return "".join(out)


def _extra_position_lines(reference_line, formation_positions):
    indent = reference_line[: len(reference_line) - len(reference_line.lstrip())]
    min_x = min(v["X"] for v in formation_positions.values())
    new_positions = [
        (min_x - 0.45, 0.00),
        (min_x - 0.45, 0.45),
        (min_x - 0.45, -0.45),
        (min_x - 0.95, 0.55),
        (min_x - 0.95, -0.55),
        (min_x - 0.95, 0.00),
    ]
    lines = []
    for i, (x, y) in enumerate(new_positions, start=4):
        x = max(0.0, x)
        y = max(-1.0, min(1.0, y))
        lines.append(f"{indent}{_name_for(formation_positions, reference_line)}_P{i}_X={x:.6g}\n")
        lines.append(f"{indent}{_name_for(formation_positions, reference_line)}_P{i}_Y={y:.6g}\n")
    return lines


def _name_for(formation_positions, reference_line):
    stripped = reference_line.strip()
    return stripped.split("_P")[0]


def main():
    text = SOURCE.read_text()
    expanded = expand(text)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(expanded)
    # Verify every formation now has 10 positions.
    for line in expanded.splitlines():
        m = re.match(r"^(\w+)_P(\d+)_(X|Y)", line.strip())
        if m:
            assert int(m.group(2)) < NUM_POSITIONS, line
    count = len(re.findall(r"_P9_Y", expanded))
    print(f"Expanded {count} formations; wrote {OUTPUT}")


if __name__ == "__main__":
    main()
