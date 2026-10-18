"""Native-data integration checks; skipped when the local disc is not extracted."""

import math
import struct
import unittest
from pathlib import Path

from strikers_mesh import Model, skeleton

FILES = Path(__file__).resolve().parents[1] / "orig/G4QE01/files"
MARIO = FILES / "art/characters/Mario"


@unittest.skipUnless((MARIO / "Mario.glg").is_file(), "Requires local USA disc extraction")
class NativeMeshTests(unittest.TestCase):
    def test_identity_roundtrip_all_variants(self):
        for name in ("Mario.glg", "Mario_blend.glg"):
            with self.subTest(name=name):
                original = (MARIO / name).read_bytes()
                self.assertEqual(Model(original).rewrite(1.0), original)

    def test_probe_changes_only_geometry_vectors(self):
        for name in ("Mario.glg", "Mario_blend.glg"):
            with self.subTest(name=name):
                model = Model((MARIO / name).read_bytes())
                result = model.rewrite(1.15)
                self.assertEqual(len(result), len(model.data))
                allowed = set()
                for offset in model.positions | model.software_positions | model.morph_deltas:
                    size = struct.calcsize(model.position_formats.get(offset, ">3f"))
                    allowed.update(range(offset, offset + size))
                changed = {i for i, pair in enumerate(zip(result, model.data)) if pair[0] != pair[1]}
                self.assertTrue(changed)
                self.assertTrue(changed <= allowed)
                rewritten = Model(result)
                self.assertEqual(len(rewritten.packets), len(model.packets))
                for offset in model.positions:
                    for before, after in zip(model.vertex(offset), rewritten.vertex(offset)):
                        self.assertAlmostEqual(after, before * 1.15, delta=1 / 256)

    def test_obj_has_valid_faces(self):
        obj = Model((MARIO / "Mario.glg").read_bytes()).obj().splitlines()
        count = sum(line.startswith("v ") for line in obj)
        faces = [line for line in obj if line.startswith("f ")]
        self.assertGreater(len(faces), 100)
        for face in faces:
            self.assertTrue(all(1 <= int(index) <= count for index in face.split()[1:]))

    def test_rejects_truncation_and_invalid_scale(self):
        data = (MARIO / "Mario.glg").read_bytes()
        with self.assertRaises(ValueError):
            Model(data[:-1])
        model = Model(data)
        for scale in (0, 2, math.nan, math.inf):
            with self.subTest(scale=scale), self.assertRaises(ValueError):
                model.rewrite(scale)

    def test_skeleton_matches_bind_matrix_count(self):
        hierarchy = skeleton(FILES / "art/animation/Mario.shier")
        model = Model((MARIO / "Mario.glg").read_bytes())
        from strikers_mesh import payload, walk
        matrices = [c for c in walk(model.tree) if c["id"] == "0x0001b00a"]
        self.assertEqual(len(matrices), 1)
        begin, end = payload(matrices[0])
        self.assertEqual((end - begin) // 68, hierarchy["nodes"])
        bone_ids = {int(bone["id"], 16) for bone in hierarchy["bones"]}
        matrix_ids = {struct.unpack_from(">I", model.data, i)[0] for i in range(begin, end, 68)}
        # The extracted assets use different identifiers for the virtual root.
        # Require every non-root skeleton ID to resolve to a bind matrix.
        non_root_ids = {int(bone["id"], 16) for bone in hierarchy["bones"] if bone["parent"] != -1}
        self.assertTrue(non_root_ids <= matrix_ids)
        self.assertEqual(len(matrix_ids - bone_ids), 1)
        decoded = model.bind_matrices()
        self.assertEqual(len(decoded), hierarchy["nodes"])
        for rows in decoded.values():
            for value, expected in zip(rows[3], (0, 0, 0, 1)):
                self.assertAlmostEqual(value, expected, places=5)


if __name__ == "__main__":
    unittest.main()
