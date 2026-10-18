# 4 · Bring your own player model

[Creator kit](../README.md) · [Stadiums →](stadium-and-formations.md)

## Native rig first

Bootstrap recovers the working `.glg`/`.glt` exports for staging. It does not
recover an editable `.blend`, a high-resolution texture master or the model's
authoring scene. You can keep this model while editing names, art and stadiums.

For a new model, make your own mesh and fit/bind it to **Daisy's actual native
rest skeleton**. Vertex-group names must be the native hexadecimal bone IDs,
not arbitrary Blender bone names. Joint locations, bind coordinates, scale and
axes must agree with the native game; the kit does **not** automatically rig,
retarget or fit arbitrary GLBs. Do not assume a Mixamo/AI skeleton is compatible.

`tools/strikers_mesh.py` exposes `Model`, `one_chunk` (via `export_palmeiras`)
and native inspection helpers. Native model chunk `0x1B00A` contains records
of bone ID + 16 big-endian matrix floats, 0x44 bytes per record. Inspect those
IDs/matrices in your own retail Daisy model. Preserve its bind matrices in the
export; do not invent replacements to make an unbound mesh appear valid.

## Export workflow

1. In Blender, use rest-pose mesh coordinates; apply transforms/non-armature
   modifiers, supply UVs in [0,1], and give each vertex 1–2 native bone groups.
2. Open `modding/blender_export.py` in Blender's Text Editor. Change `OUTPUT`,
   select only the fitted meshes, and run the script. It reads unevaluated mesh
   data so a posed armature is not baked into the rest geometry. Verify your
   native bind/rest setup first.
3. Paint/save a **512×256 PNG** albedo using those UVs. Transparency is discarded
   by the RGB565 player texture. No facial morphs/blinking are created.
4. In a terminal at the public repo:

   ```sh
   python3 modding/export_model.py --workspace "/path/to/strikers-work" --intermediate "/path/to/player.json" --texture "/path/to/albedo.png" --replace
   ```

5. Inside WORK: `python3 tools/combined_mod.py stage`. The same exported source
   is assigned separate captain/sidekick native identities. Use the creator
   launcher and verify actual gameplay animations, kicks, falls, goals and replays.

The helper validates the generated files before archiving the previous export.
It retains the example's internal texture identity so existing staging/validation
continues to work. Change those mappings together if you introduce another model.
The older `export_human_player.py generate` entry point expects private historical
preparation records; use **this public export helper**, not that entry point.

## Intermediate and working budgets

[`intermediate.example.json`](../templates/model/intermediate.example.json)
illustrates the schema only; its placeholder triangle/bone ID is not a playable
model. The real exporter expects per-mesh positions and weights, triangles with
per-corner UVs/normals, and the `palmeiras-player-intermediate-v1` format tag.
Blender UV Y is flipped when encoded for the native texture path.

The example validates **≤2,000 exported seam-split vertices**, **≤2,500 triangles**,
**≤2 influences per vertex**, **≤1.5 mean influences**. Also keep each GLG below
`0x80000` bytes and the native diffuse below `0x40800` bytes. These are working
prototype limits, not universal hardware limits. UV seams increase export
vertices. Twenty human outfielders multiply CPU-skinning work—test full teams,
not just a single player. Synthetic deformation and valid weights alone do not
prove real animation compatibility.
