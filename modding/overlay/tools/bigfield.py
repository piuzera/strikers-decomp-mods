#!/usr/bin/env python3
"""big-field: enlarge The Palace's playing field and stadium (playable prototype).

Edits The_Palace.wld in place of the extracted disc copy, and provides a
non-matching build + Dolphin stage/run flow.

Field-size convention: the engine reads the pitch half-extents from the
"FieldCorner" helper object (BasicStadium::DoInitialize passes its position to
cField::SetFieldDimensions, which now honours it). The physical boundary is
code-built from cField (4 sidelines + 4 rounded corners), so it scales
automatically. This tool also moves the Palace's goal-area physics planes and the
penalty/net helper markers outward to match.

The pitch and stadium share one horizontal world-space enlargement, including
geometry and visibility bounds. Goals retain their retail size and move to the
new goal lines. combined_mod.py is the canonical merged-main workflow.
"""

import argparse
import hashlib
import shutil
import struct
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION = "G4QE01"
ORIG = ROOT / "orig" / VERSION
BUILD = ROOT / "build"
MOD_BUILD = BUILD / "bigfield"
STAGE = MOD_BUILD / "disc"
DTK = BUILD / "tools" / "dtk"

WLD_REL = Path("art/Environment/The_Palace/The_Palace.wld")

# Retail field half-extents (code defaults, all stadiums) and the enlargement.
OLD_X, OLD_Y = 20.60211, 12.0825
SCALE = 2.0
NEW_X, NEW_Y = OLD_X * SCALE, OLD_Y * SCALE
DELTA_X = NEW_X - OLD_X


def chunks(data, start=0, end=None):
    end = len(data) if end is None else end
    out, o = [], start
    while o < end:
        raw_id, size = struct.unpack_from(">II", data, o)
        nxt = o + 8 + size
        if nxt > end:
            raise ValueError(f"chunk at {o:#x} overruns parent")
        align = 1 << ((raw_id >> 24) & 0x7F)
        payload = (o + 8 + align - 1) & -align
        if payload > nxt:
            raise ValueError(f"alignment overruns chunk at {o:#x}")
        item = {"id": raw_id & 0x80FFFFFF, "size": size, "off": o, "data": payload}
        if raw_id & 0x80000000:
            item["children"] = chunks(data, o + 8, nxt)
        out.append(item)
        o = nxt
    return out


def walk(tree):
    for c in tree:
        yield c
        yield from walk(c.get("children", []))


def helper_records(data, chunk):
    base, end = chunk["data"], chunk["off"] + 8 + chunk["size"]
    while base + 0x80 <= end:
        yield base
        base += 0x80


# World-object names that make up the visual goal structure and sit on the old
# goal line. These move outward with the enlarged pitch. (Rebar_* are the
# Hyper-Strike model helpers listed in BasicStadium.cpp.)
GOAL_OBJECTS = {"goal01", "goal05", "posts_02", "posts_03", "posts_shadow",
                "posts_shadowed_02", "netmesh", "netmesh01"}


def is_goal_object(short):
    return short in GOAL_OBJECTS or short.startswith("rebar_")


LIGHTING_OBJECTS = {"lightramp", "playerlightramp"}


def scale_world_object(out, data, base):
    """Apply (x, y, z) -> (SCALE*x, SCALE*y, z), including rotated bases.

    nlMatrix4 transforms a point using rows 0/1/2 and translation row 3.
    Scaling each row's X/Y components therefore scales world coordinates,
    rather than scaling along the object's possibly rotated local axes.
    """
    for row in range(4):
        for axis in (0, 1):
            offset = base + 0xA0 + (row * 4 + axis) * 4
            struct.pack_into(">f", out, offset, struct.unpack_from(">f", data, offset)[0] * SCALE)
    # World_IsSphereInFrustumInline uses this radius directly, without applying
    # the matrix scale. The largest axis scale gives a conservative world bound.
    radius = struct.unpack_from(">f", data, base + 0x98)[0]
    struct.pack_into(">f", out, base + 0x98, radius * max(1.0, abs(SCALE)))


def world_object_records(data, chunk):
    base, end = chunk["data"], chunk["off"] + 8 + chunk["size"]
    while base + 0xE0 <= end:
        yield base
        base += 0xE0


def edit_wld(data):
    out = bytearray(data)
    helpers = {"fieldcorner01": 0, "fieldcorner": 0, "penaltycorner": 0, "netcorner": 0}
    planes = 0
    pitch = 0
    goals = 0
    rebar = 0
    scaled = 0
    for c in walk(chunks(data)):
        if c["id"] == 0x19201:
            for base in helper_records(data, c):
                name = bytes(out[base:base + 60]).split(b"\0", 1)[0].decode("ascii", "replace")
                mx, my, mz = base + 0x70, base + 0x74, base + 0x78
                if name.endswith("fieldcorner01"):
                    struct.pack_into(">f", out, mx, NEW_X)
                    struct.pack_into(">f", out, my, -NEW_Y)
                    helpers["fieldcorner01"] += 1
                elif name.endswith("fieldcorner"):
                    struct.pack_into(">f", out, mx, NEW_X)
                    struct.pack_into(">f", out, my, NEW_Y)
                    helpers["fieldcorner"] += 1
                elif name.endswith("penaltycorner"):
                    struct.pack_into(">f", out, mx, struct.unpack_from(">f", data, mx)[0] * SCALE)
                    struct.pack_into(">f", out, my, struct.unpack_from(">f", data, my)[0] * SCALE)
                    helpers["penaltycorner"] += 1
                elif name.endswith("netcorner"):
                    struct.pack_into(">f", out, mx, struct.unpack_from(">f", data, mx)[0] + DELTA_X)
                    helpers["netcorner"] += 1
                else:
                    # Scale every other helper marker (camera flashes, flares,
                    # benches, group/plane refs) outward with the stadium.
                    struct.pack_into(">f", out, mx, struct.unpack_from(">f", data, mx)[0] * SCALE)
                    struct.pack_into(">f", out, my, struct.unpack_from(">f", data, my)[0] * SCALE)
        elif c["id"] == 0x1D002:
            for base in range(c["data"], c["off"] + 8 + c["size"], 0xA0):
                x = struct.unpack_from(">f", data, base + 0x30)[0]
                if x != 0.0:
                    struct.pack_into(">f", out, base + 0x30, x + (DELTA_X if x > 0 else -DELTA_X))
                planes += 1
        elif c["id"] == 0x19003:
            for base in world_object_records(data, c):
                name = bytes(out[base:base + 64]).split(b"\0", 1)[0].decode("ascii", "replace")
                short = name.split("/")[-1]
                tx = base + 0xD0  # m[12] translation X
                if is_goal_object(short):
                    x = struct.unpack_from(">f", data, tx)[0]
                    struct.pack_into(">f", out, tx, x + (DELTA_X if x > 0 else -DELTA_X))
                    if short.startswith("rebar_"):
                        rebar += 1
                    else:
                        goals += 1
                elif short in LIGHTING_OBJECTS:
                    continue  # lighting reference textures: keep in place
                else:
                    # A common world-space transform preserves every shared
                    # terrain/stand edge. Translating only opens seams; scaling
                    # outer_pitch around a goal-relative pivot pushes it infield.
                    scale_world_object(out, data, base)
                    if short == "pitch":
                        pitch += 1
                    scaled += 1
    if helpers != {"fieldcorner01": 1, "fieldcorner": 1, "penaltycorner": 1, "netcorner": 1}:
        raise ValueError(f"Unexpected helper markers found: {helpers}")
    if planes != 54:
        raise ValueError(f"Expected 54 physics planes, found {planes}")
    if pitch != 1:
        raise ValueError(f"Expected exactly one pitch object, found {pitch}")
    if goals != len(GOAL_OBJECTS):
        raise ValueError(f"Expected {len(GOAL_OBJECTS)} goal objects, found {goals}")
    if rebar == 0:
        raise ValueError("No rebar goal objects found")
    if scaled == 0:
        raise ValueError("No stadium objects were scaled")
    edited = bytes(out)
    verify_wld(edited, original=data)
    return edited


def verify_wld(data, original=None):
    seen = {}
    for c in walk(chunks(data)):
        if c["id"] == 0x19201:
            for base in helper_records(data, c):
                name = bytes(data[base:base + 60]).split(b"\0", 1)[0].decode("ascii", "replace")
                if name.endswith(("fieldcorner", "fieldcorner01", "penaltycorner", "netcorner")):
                    seen[name] = struct.unpack_from(">3f", data, base + 0x70)
        elif c["id"] == 0x1D002:
            xs = [struct.unpack_from(">f", data, b + 0x30)[0] for b in range(c["data"], c["off"] + 8 + c["size"], 0xA0)]
            min_x, max_x = min(xs), max(xs)
        elif c["id"] == 0x19003:
            for base in world_object_records(data, c):
                name = bytes(data[base:base + 64]).split(b"\0", 1)[0].decode("ascii", "replace")
                short = name.split("/")[-1]
                if short == "pitch":
                    sx = struct.unpack_from(">f", data, base + 0xA0)[0]
                    sy = struct.unpack_from(">f", data, base + 0xB4)[0]
                elif short in ("goal01", "netmesh"):
                    seen["goal " + short] = struct.unpack_from(">f", data, base + 0xD0)[0]
    fc = seen["the_palace/fieldcorner"]
    if abs(fc[0] - NEW_X) > 1e-3 or abs(fc[1] - NEW_Y) > 1e-3:
        raise ValueError(f"fieldcorner not at target: {fc}")
    if min_x > -OLD_X or max_x < OLD_X:
        raise ValueError(f"physics planes did not move outward: [{min_x:.2f}, {max_x:.2f}]")
    if abs(sx - SCALE) > 1e-3 or abs(sy - SCALE) > 1e-3:
        raise ValueError(f"pitch not scaled: ({sx}, {sy})")
    if original is not None:
        verify_object_transforms(original, data)
    return {"fieldcorner": fc, "planes_min_x": min_x, "planes_max_x": max_x,
            "netcorner": seen["the_palace/netcorner"], "pitch_scale": (sx, sy),
            "goal01_x": seen["goal goal01"], "netmesh_x": seen["goal netmesh"]}


def verify_object_transforms(original, edited):
    """Check every visual transform and visibility radius against its source."""
    if len(original) != len(edited):
        raise ValueError("World size changed")
    for chunk in walk(chunks(original)):
        if chunk["id"] != 0x19003:
            continue
        for base in world_object_records(original, chunk):
            name = original[base:base + 64].split(b"\0", 1)[0].decode("ascii")
            short = name.split("/")[-1]
            expected = list(struct.unpack_from(">16f", original, base + 0xA0))
            radius = struct.unpack_from(">f", original, base + 0x98)[0]
            if is_goal_object(short):
                expected[12] += DELTA_X if expected[12] > 0 else -DELTA_X
            elif short not in LIGHTING_OBJECTS:
                expected = [v * SCALE if i % 4 in (0, 1) else v
                            for i, v in enumerate(expected)]
                radius *= max(1.0, abs(SCALE))
            actual = struct.unpack_from(">16f", edited, base + 0xA0)
            actual_radius = struct.unpack_from(">f", edited, base + 0x98)[0]
            if any(not abs(a - e) <= 1e-4 for a, e in zip(actual, expected)):
                raise ValueError(f"Incorrect stadium transform: {name}")
            if not abs(actual_radius - radius) <= 1e-4:
                raise ValueError(f"Incorrect visibility radius: {name}")


def run(*args):
    print("+", " ".join(map(str, args)), flush=True)
    subprocess.run(list(map(str, args)), cwd=ROOT, check=True)


def sha1(path):
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha1").hexdigest()


def build():
    baseline = BUILD / VERSION / "main.dol"
    if baseline.is_file() and sha1(baseline) != "376d699c99b6b0949abe1b4ceccefdef7828d2b5":
        raise RuntimeError("retail baseline does not match; rebuild it first")
    run(sys.executable, "configure.py", "--version", VERSION, "--map", "--non-matching",
        "--build-dir", str(MOD_BUILD.relative_to(ROOT)),
        "--dtk", str(DTK), "--compilers", str(BUILD / "compilers"),
        "--binutils", str(BUILD / "binutils"), "--objdiff", str(BUILD / "tools/objdiff-cli"),
        "--sjiswrap", str(BUILD / "tools/sjiswrap.exe"), "--wrapper", str(BUILD / "tools/wibo"))
    run("ninja")


def stage():
    mod_dol = MOD_BUILD / VERSION / "main.dol"
    if not mod_dol.is_file():
        raise RuntimeError("build the mod first (python tools/bigfield.py build)")
    source_wld = ORIG / "files" / WLD_REL
    edited = edit_wld(source_wld.read_bytes())
    report = verify_wld(edited)
    if STAGE.exists():
        raise RuntimeError(f"stage already exists at {STAGE}; remove it before restaging")
    shutil.copytree(ORIG / "sys", STAGE / "sys")
    shutil.copytree(ORIG / "files", STAGE / "files")
    shutil.copy2(mod_dol, STAGE / "sys/main.dol")
    (STAGE / "files" / WLD_REL).write_bytes(edited)
    print(f"Staged disc: {STAGE / 'sys/main.dol'}")
    print(f"  fieldcorner -> {tuple(round(v, 3) for v in report['fieldcorner'])}")
    print(f"  physics X range -> [{report['planes_min_x']:.2f}, {report['planes_max_x']:.2f}]")
    print("Only The_Palace.wld and the rebuilt DOL are modified; original extraction untouched.")


def run_dolphin(background):
    target = STAGE / "sys/main.dol"
    if not target.is_file():
        raise RuntimeError("stage the disc first (python tools/bigfield.py stage)")
    dolphin = shutil.which("dolphin-emu") or shutil.which("dolphin")
    if not dolphin:
        raise RuntimeError("dolphin-emu not found")
    profile = MOD_BUILD / "dolphin-user"
    profile.mkdir(parents=True, exist_ok=True)
    args = [dolphin, "--user", str(profile), "--exec", str(target),
            "--config", "Dolphin.Input.BackgroundInput=True"]
    if background:
        log = MOD_BUILD / "dolphin-console.log"
        with log.open("ab") as f:
            proc = subprocess.Popen(args, cwd=ROOT, stdout=f, stderr=f, start_new_session=True)
        print(f"Started Dolphin PID {proc.pid}; console log: {log}")
    else:
        run(*args)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("build", help="non-matching build with the Field.cpp change")
    sub.add_parser("stage", help="edit The_Palace.wld and stage a test disc")
    runp = sub.add_parser("run", help="launch the staged disc in Dolphin")
    runp.add_argument("--background", action="store_true")
    sub.add_parser("check", help="decode the edited wld and print the result")
    args = parser.parse_args()
    try:
        if args.cmd == "build":
            build()
        elif args.cmd == "stage":
            stage()
        elif args.cmd == "run":
            run_dolphin(args.background)
        elif args.cmd == "check":
            data = (ORIG / "files" / WLD_REL).read_bytes()
            edited = edit_wld(data)
            print("edited == original:", edited == data)
            print(verify_wld(edited))
    except (OSError, ValueError, subprocess.CalledProcessError, struct.error) as exc:
        parser.exit(1, f"Error: {exc}\n")


if __name__ == "__main__":
    main()
