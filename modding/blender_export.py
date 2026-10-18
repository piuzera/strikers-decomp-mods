"""Blender 4.x/5.x: export selected meshes bound to native hexadecimal bone groups.

Set OUTPUT below, then run in Blender's Text Editor. MIT licensed.
This exports rest coordinates, not evaluated/animated geometry; it does not retarget.
"""
import json
from pathlib import Path

import bpy

OUTPUT = Path.home() / "strikers-player-intermediate.json"


def export_selected(output=OUTPUT):
    meshes = []
    for obj in bpy.context.selected_objects:
        if obj.type != "MESH":
            continue
        mesh = obj.data
        mesh.calc_loop_triangles()
        if mesh.uv_layers.active is None:
            raise ValueError(f"{obj.name}: UV map missing")
        if any(mod.type != "ARMATURE" and mod.show_viewport for mod in obj.modifiers):
            raise ValueError(f"{obj.name}: apply non-armature modifiers first")
        if any(abs(obj.matrix_world[i][j] - (1 if i == j else 0)) > 1e-5 for i in range(4) for j in range(4)):
            raise ValueError(f"{obj.name}: apply object transforms, preserving the native bind coordinates")
        weights = []
        for vertex in mesh.vertices:
            membership = {obj.vertex_groups[g.group].name: g.weight for g in vertex.groups if g.weight > 1e-6}
            if not membership or len(membership) > 2:
                raise ValueError(f"{obj.name}: vertex {vertex.index} needs 1–2 native bone groups")
            for name in membership:
                int(name, 16)  # Names are native hexadecimal bone IDs, not Blender labels.
            total = sum(membership.values())
            weights.append({name: value / total for name, value in membership.items()})
        uv = mesh.uv_layers.active.data
        triangles = [{"vertices": list(t.vertices), "normal": list(t.normal), "material": 0,
                      "uvs": [list(uv[i].uv) for i in t.loops]} for t in mesh.loop_triangles]
        meshes.append({"name": obj.name, "positions": [list(v.co) for v in mesh.vertices],
                       "weights": weights, "materials": [{"base_color": [1, 1, 1, 1]}], "triangles": triangles})
    if not meshes:
        raise ValueError("Select at least one mesh")
    output = Path(output)
    output.write_text(json.dumps({"format": "palmeiras-player-intermediate-v1", "meshes": meshes}) + "\n")
    print(f"Exported {len(meshes)} mesh(es) to {output}")


if __name__ == "__main__":
    export_selected()
