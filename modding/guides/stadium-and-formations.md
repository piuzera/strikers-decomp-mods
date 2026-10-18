# 5 · Stadiums and formations

[Creator kit](../README.md) · [Test/package →](testing-and-packaging.md)

## Change the Palace size

In WORK, edit `SCALE` in `tools/bigfield.py` and run:

```sh
python3 tools/bigfield.py check
python3 tools/combined_mod.py stage
python3 -B -m unittest discover -s tools -p test_bigfield.py -v
```

Start with a modest factor such as 1.5. `NEW_X`, `NEW_Y` and `DELTA_X` derive
from retail half-extents `(20.60211, 12.0825)`. The engine source patch reads
the stadium's FieldCorner helper, updates field boundaries/formation scaling,
and adjusts camera/goalkeeper placement. Other stadiums retain their own helpers.
[`templates/stadium/plan.json`](../templates/stadium/plan.json) documents the
transform contract; it is not read automatically by the scaler.

The WLD editor always starts from `orig/G4QE01/files/art/Environment/The_Palace/`.
It transforms existing geometry, not remodels/exports a new stadium mesh.
Altering a different stadium requires its own inventory and validation—names,
goal groups and physics-plane counts are Palace-specific.

## Do not reopen the seams

- Helpers: scale field/penalty/stadium markers appropriately; move NetCorner
  with the goal rather than widening the goal mouth.
- Physics: translate all 54 Palace goal-area planes outward, sign-aware.
- Goals: retain retail geometry size, translate X to the new goal line.
- Scenery, pitch, goal aprons, stands and stairs: share the **same horizontal
  world-space transform**, including position and geometry. Keep height.
- Matrix: multiply X/Y components of all four rows, not just two diagonal
  values. Rotated meshes otherwise scale incorrectly.
- Visibility: enlarge each geometry object's world-space bounding radius.
  The renderer's frustum check does not apply matrix scale to that radius.
- Lighting reference objects remain untouched.

Translating stands without growing their geometry creates black gaps. Scaling
the goal apron about a goal-relative pivot rather than world coordinates pushes
it onto the field. These were the final Palace defects corrected in this project.

## Ten-position formations

Edit `mods/expand-team/FormationSets.ini`. Every one of the 41 definitions must
provide finite `P0`…`P9` X/Y positions. They use native AI coordinates, not world
metres: current validation expects X in [0,4] and Y in [-1,1]. The first neutral
and advantage kickoff definitions need ten distinct positions.

Run from WORK:

```sh
python3 -c "import sys; sys.path.insert(0, 'tools'); from expanded_runtime import validate_formation_file; print(validate_formation_file())"
```

Then stage. Player-count changes are **not** a formation-file-only edit:
`include/Game/PlayerCounts.h` feeds AI, physics, events, stats, snapshots, replay
and rendering consumers. This kit's worked example remains 11-a-side.
