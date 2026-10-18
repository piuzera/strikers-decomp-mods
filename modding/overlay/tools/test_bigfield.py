"""Palace seam and visibility regressions using native retail mesh vertices."""

import struct
import unittest

import bigfield as field
from strikers_mesh import Model


def objects(data):
    return {data[b:b + 64].split(b"\0", 1)[0].decode().split("/")[-1]: b
            for c in field.walk(field.chunks(data)) if c["id"] == 0x19003
            for b in field.world_object_records(data, c)}


def transform(matrix, point):
    return tuple(sum(point[j] * matrix[j * 4 + i] for j in range(3)) + matrix[12 + i]
                 for i in range(3))


class MatrixTests(unittest.TestCase):
    def test_horizontal_world_scale_handles_rotated_and_tilted_objects(self):
        source = bytearray(0xE0)
        matrix = (0, 1, 0, 0, -0.8, 0, 0.6, 0, 0.6, 0, 0.8, 0, 4, -7, 3, 1)
        struct.pack_into(">16f", source, 0xA0, *matrix)
        struct.pack_into(">f", source, 0x98, 5)
        edited = bytearray(source)
        field.scale_world_object(edited, source, 0)
        actual = transform(struct.unpack_from(">16f", edited, 0xA0), (2, 3, 4))
        before = transform(matrix, (2, 3, 4))
        for axis, value in enumerate(actual):
            self.assertAlmostEqual(value, before[axis] * (field.SCALE if axis < 2 else 1), places=5)
        self.assertEqual(struct.unpack_from(">f", edited, 0x98)[0], 10)


@unittest.skipUnless((field.ORIG / "files" / field.WLD_REL).is_file(), "Requires local retail Palace")
class PalaceGeometryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original = (field.ORIG / "files" / field.WLD_REL).read_bytes()
        cls.edited = field.edit_wld(cls.original)
        cls.objects = objects(cls.original)
        glg = (field.ORIG / "files" / field.WLD_REL.with_suffix(".glg")).read_bytes()
        cls.mesh = Model(glg)
        cls.models = {}
        table = next(c for c in field.walk(field.chunks(glg)) if c["id"] == 0x1B003)
        for offset in range(table["data"], table["off"] + 8 + table["size"], 16):
            count, model_id, _, packet_offset = struct.unpack_from(">4I", glg, offset)
            first = packet_offset // 74
            cls.models[model_id] = cls.mesh.packets[first:first + count]

    def test_mesh_vertices_preserve_shared_edges_under_world_enlargement(self):
        # Check actual indexed vertices, including both goal aprons, both sides
        # of the seating bowl, stairs, entrance covers, rotated wire and crowd.
        checked = set()
        for name, base in self.objects.items():
            if field.is_goal_object(name) or name in field.LIGHTING_OBJECTS:
                continue
            model_id = struct.unpack_from(">I", self.original, base + 0x84)[0]
            if model_id not in self.models:
                # World::HandleObjectCreation skips references without a model.
                self.assertIn(name, {"camera02.target", "camera01.target", "camera03.target",
                                     "tape01.target", "tape02.target", "new large pod24"})
                continue
            before = struct.unpack_from(">16f", self.original, base + 0xA0)
            after = struct.unpack_from(">16f", self.edited, base + 0xA0)
            offsets = {p["position_offsets"][i] for p in self.models[model_id] for i in p["indices"]}
            for offset in offsets:
                vertex = self.mesh.vertex(offset)
                old = transform(before, vertex)
                new = transform(after, vertex)
                for axis in range(3):
                    self.assertAlmostEqual(new[axis], old[axis] * (field.SCALE if axis < 2 else 1), places=4,
                                           msg=f"{name}: vertex {offset:#x}, axis {axis}")
            checked.add(name)
        self.assertTrue({"outer_pitch_01", "outer_pitch_02", "seating_01", "upper_seating_01",
                         "entrance_walkway_02", "stairs_11", "crowd_01"} <= checked)

    def test_goals_keep_retail_dimensions_and_lighting_records_are_unchanged(self):
        for name, base in self.objects.items():
            if field.is_goal_object(name):
                old = struct.unpack_from(">16f", self.original, base + 0xA0)
                new = struct.unpack_from(">16f", self.edited, base + 0xA0)
                self.assertEqual(old[:12], new[:12], name)
                self.assertEqual(old[13:], new[13:], name)
                self.assertAlmostEqual(new[12] - old[12], field.DELTA_X if old[12] > 0 else -field.DELTA_X, places=4)
                self.assertEqual(self.original[base + 0x98:base + 0x9C], self.edited[base + 0x98:base + 0x9C])
            elif name in field.LIGHTING_OBJECTS:
                self.assertEqual(self.original[base:base + 0xE0], self.edited[base:base + 0xE0])

    def test_visibility_bounds_cover_enlarged_geometry_and_verification_rejects_regressions(self):
        field.verify_wld(self.edited, original=self.original)
        for name in ("pitch", "outer_pitch_02", "seating_01", "stairs_11"):
            base = self.objects[name]
            radius = struct.unpack_from(">f", self.original, base + 0x98)[0]
            self.assertAlmostEqual(struct.unpack_from(">f", self.edited, base + 0x98)[0], radius * field.SCALE)
        for offset in (0x98, 0xA0, 0xD0):
            damaged = bytearray(self.edited)
            base = self.objects["outer_pitch_02"]
            damaged[base + offset:base + offset + 4] = self.original[base + offset:base + offset + 4]
            with self.assertRaises(ValueError):
                field.verify_wld(damaged, original=self.original)

    def test_only_object_matrices_radii_helpers_and_physics_are_edited(self):
        allowed = set()
        for chunk in field.walk(field.chunks(self.original)):
            if chunk["id"] == 0x19003:
                for base in field.world_object_records(self.original, chunk):
                    allowed.update(range(base + 0xA0, base + 0xE0))
                    allowed.update(range(base + 0x98, base + 0x9C))
            elif chunk["id"] == 0x19201:
                for base in field.helper_records(self.original, chunk):
                    allowed.update(range(base + 0x70, base + 0x78))
            elif chunk["id"] == 0x1D002:
                for base in range(chunk["data"], chunk["off"] + 8 + chunk["size"], 0xA0):
                    allowed.update(range(base + 0x30, base + 0x34))
        self.assertEqual(len(self.original), len(self.edited))
        self.assertTrue(all(i in allowed for i, (old, new) in enumerate(zip(self.original, self.edited)) if old != new))


if __name__ == "__main__":
    unittest.main()
