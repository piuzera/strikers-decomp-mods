"""Validate native exporter contracts independently of the Blender scene."""

import copy
import struct
import unittest
from pathlib import Path

from export_palmeiras import FILES, export, generate, geometry, quantize_weights, validate
from palmeiras_texture import (ATLAS_SIZE, TEXTURE_NAME, append_texture,
                               build_atlas, encode_texture, lower_hash,
                               parse_bundle, swizzle_16bpp, unswizzle_16bpp,
                               validate_bundle)
from strikers_mesh import Model, payload, walk


class WeightTests(unittest.TestCase):
    def test_quantization_conserves_weight(self):
        for values in ([1], [1, 1, 1], [0.99999, 0.00001], [0.1, 0.2, 0.3, 0.4]):
            result = quantize_weights({f"0x{i + 1:x}": v for i, v in enumerate(values)})
            self.assertEqual(sum(weight for _, weight in result), 65535)
            for bone, weight in result:
                self.assertLessEqual(abs(weight / 65535 - values[bone - 1] / sum(values)), 1 / 65535)

    def test_invalid_weights_rejected(self):
        for weights in ({}, {"0x1": -1}, {"0x1": float("nan")}, {"0x1": 0}):
            with self.subTest(weights=weights), self.assertRaises(ValueError):
                quantize_weights(weights)


class TextureTests(unittest.TestCase):
    def test_swizzle_roundtrip(self):
        pixels = [(x * 31 + y * 7) & 0xFFFF for y in range(16) for x in range(16)]
        swizzled = swizzle_16bpp(16, 16, pixels)
        self.assertEqual(len(swizzled), 16 * 16 * 2)
        self.assertEqual(unswizzle_16bpp(16, 16, swizzled), pixels)
        # Tiles are 32-byte aligned runs of the original rows.
        self.assertEqual(swizzled[0:8], struct.pack(">4H", pixels[0], pixels[1], pixels[2], pixels[3]))

    def test_atlas_blocks_and_capacity(self):
        pixels, blocks = build_atlas([[0.01, 0.18, 0.05, 1], [0.9, 0.9, 0.9, 1], [0.01, 0.18, 0.05, 0.5]])
        self.assertEqual(len(blocks), 2)  # alpha is not part of the atlas key
        for (u, v) in blocks.values():
            self.assertIn(u, (128, 384, 640, 896))
            self.assertIn(v, (128, 384, 640, 896))
        with self.assertRaises(ValueError):
            build_atlas([[i / 64, 0, 0, 1] for i in range(17)])

    def test_bundle_append_preserves_retail_payloads(self):
        bundle = (FILES / "art/characters/Mario/Mario.glt").read_bytes()
        original = parse_bundle(bundle)
        pixels, _ = build_atlas([[0.1, 0.2, 0.3, 1]])
        new_bundle, hash_value = append_texture(bundle, TEXTURE_NAME,
                                                encode_texture(ATLAS_SIZE, ATLAS_SIZE, pixels))
        new_hash, blob = validate_bundle(new_bundle, original)
        self.assertEqual(new_hash, hash_value)
        self.assertEqual(hash_value, lower_hash(TEXTURE_NAME))
        levels, fmt = struct.unpack_from(">II", blob, 0)
        width, height = struct.unpack_from(">HH", blob, 0xE)
        self.assertEqual((levels, fmt, width, height), (1, 0, ATLAS_SIZE, ATLAS_SIZE))
        self.assertEqual(len(blob), 0x20 + ATLAS_SIZE * ATLAS_SIZE * 2)
        parsed = parse_bundle(new_bundle)
        self.assertEqual(len(parsed), len(original) + 1)


TEMPLATE = FILES / "art/characters/Mario/Mario.glg"
BUNDLE = FILES / "art/characters/Mario/Mario.glt"


@unittest.skipUnless(TEMPLATE.is_file(), "Requires local retail template")
class NativeExportTests(unittest.TestCase):
    def setUp(self):
        self.template = TEMPLATE.read_bytes()
        self.bones = sorted(Model(self.template).bind_matrices())[:2]
        self.document = {"format": "palmeiras-player-intermediate-v1", "meshes": [{
            "name": "triangle", "positions": [[0, 0, 0], [0.2, 0, 0], [0, 0, 0.2]],
            "weights": [{self.bones[0]: 1}, {self.bones[1]: 1},
                        {self.bones[0]: 0.25, self.bones[1]: 0.75}],
            "materials": [{"base_color": [0.01, 0.18, 0.05, 1]}],
            "triangles": [{"vertices": [0, 1, 2], "normal": [0, -1, 0], "material": 0}],
        }]}
        self.blocks = build_atlas([[0.01, 0.18, 0.05, 1]])[1]
        self.diffuse = lower_hash(TEXTURE_NAME)

    def export(self):
        return export(self.document, self.template, self.diffuse, self.blocks)

    def test_positions_indices_and_template_id_survive(self):
        output, report = export(self.document, self.template, self.diffuse, self.blocks)
        model = Model(output)
        self.assertEqual(report["triangles"], 1)
        self.assertEqual(report["software_vertices"], 3)
        self.assertEqual(model.packets[0]["indices"], (0, 1, 2))
        for actual, expected in zip(sorted(model.positions), self.document["meshes"][0]["positions"]):
            for a, b in zip(model.vertex(actual), expected):
                self.assertAlmostEqual(a, b, places=6)
        for original_chunk in walk(Model(self.template).tree):
            if original_chunk["id"] == "0x0001b003":
                original_id = struct.unpack_from(">I", self.template, original_chunk["data_offset"] + 4)[0]
        self.assertEqual(report["model_id"], f"0x{original_id:08x}")
        self.assertEqual(model.bind_matrices(), Model(self.template).bind_matrices())
        self.assertEqual(report["diffuse_texture"], f"0x{self.diffuse:08x}")

    def test_packet_state_uses_validated_constants(self):
        output, _ = self.export()
        exported = next(c for c in walk(Model(output).tree) if c["id"] == "0x0001b004")
        raw = output[payload(exported)[0]:payload(exported)[1]][:74]
        texstate, = struct.unpack_from(">Q", raw, 0x10)
        matstate, _program, raster = struct.unpack_from(">III", raw, 0x18)
        self.assertEqual(texstate, (63 << 18) | (63 << 30) | (63 << 36) | (63 << 42) | (63 << 48))
        self.assertEqual(matstate, 0)
        self.assertEqual(raster, 1 | (1 << 1) | (1 << 2) | (3 << 18))
        self.assertEqual(raw[0x40], 1)  # texconfig: diffuse only
        texture, = struct.unpack_from(">I", raw, 0x28)
        self.assertEqual(texture, self.diffuse)

    def test_independent_cpu_weight_reconstruction(self):
        output, _ = self.export()
        model = Model(output)
        maps = [c for c in walk(model.tree) if c["id"] == "0x0001b00b"]
        begin, end = payload(maps[0])
        matrix_bones = dict((value, bone) for bone, value in
                            (struct.unpack_from(">II", output, i) for i in range(begin, end, 8)))
        weights = [{} for _ in range(3)]
        lists = [c for c in walk(model.tree) if c["id"] == "0x0001b00e"]
        for matrix_index, entry in enumerate(lists):
            begin, end = payload(entry)
            for i in range(begin, end, 4):
                vertex, weight = struct.unpack_from(">HH", output, i)
                weights[vertex][f"0x{matrix_bones[matrix_index]:08x}"] = weight / 65535
        # Distinct synthetic bone translations reveal mismatched map/list ordering.
        translations = {bone: i + 1 for i, bone in enumerate(self.bones)}
        for source, reconstructed in zip(self.document["meshes"][0]["weights"], weights):
            expected = sum(translations[b] * w for b, w in source.items())
            actual = sum(translations[b] * w for b, w in reconstructed.items())
            self.assertAlmostEqual(actual, expected, delta=2 / 65535)

    def test_welds_duplicate_triangle_corners(self):
        document = copy.deepcopy(self.document)
        document["meshes"][0]["triangles"] *= 2
        vertices, packets = geometry(document, self.blocks)
        self.assertEqual(len(vertices), 3)
        self.assertEqual(len(packets[0]["indices"]), 6)

    def test_uv_stream_uses_authored_atlas_blocks(self):
        output, _ = self.export()
        model = Model(output)
        render = next(c for c in walk(model.tree) if c["id"] == "0x0001b006")
        stream_chunk = one = next(c for c in walk(model.tree) if c["id"] == "0x0001b005")
        address, stream_id, stride = struct.unpack_from(">IBB", output, payload(stream_chunk)[0] + 3 * 6)
        self.assertEqual((stream_id, stride), (3, 4))
        pair = struct.unpack_from(">2h", output, payload(render)[0] + address)
        self.assertIn(pair, set(self.blocks.values()))

    def test_missing_bind_matrix_rejected(self):
        self.document["meshes"][0]["weights"][0] = {"0x12345678": 1}
        with self.assertRaisesRegex(ValueError, "Missing native bind matrices"):
            self.export()

    def test_mesh_uv_seams_and_vertical_orientation_survive(self):
        document = copy.deepcopy(self.document)
        mesh = document["meshes"][0]
        mesh["triangles"][0]["uvs"] = [[0.1, 0.2], [0.8, 0.2], [0.1, 0.9]]
        second = copy.deepcopy(mesh["triangles"][0])
        second["uvs"][0] = [0.4, 0.2]
        mesh["triangles"].append(second)
        vertices, packets = geometry(document, None)
        self.assertEqual(len(vertices), 4)  # duplicate position, distinct UV
        self.assertNotEqual(packets[0]["indices"][0], packets[0]["indices"][3])
        self.assertEqual(vertices[0][6], (102, 819))  # V flipped for GX
        output, report = export(document, self.template, self.diffuse, None)
        self.assertEqual(report["texture_mapping"], "mesh UV")
        self.assertEqual(report["software_vertices"], 4)
        model = Model(output)
        self.assertEqual([(s["id"], s["stride"]) for s in model.packets[0]["streams"]],
                         [(0, 12), (1, 3), (2, 4), (3, 4)])
        # Compact bind normals encode exactly the existing software precision.
        render = next(c for c in walk(model.tree) if c["id"] == "0x0001b006")
        address = model.packets[0]["streams"][1]["address"]
        self.assertEqual(struct.unpack_from(">3b", output, payload(render)[0] + address), (0, -64, 0))

    def test_mesh_uv_missing_nonfinite_or_out_of_range_rejected(self):
        for uvs in (None, [[0, 0]], [[0, 0], [1, 0], [float("nan"), 1]],
                    [[0, 0], [1, 0], [0, 1.01]]):
            document = copy.deepcopy(self.document)
            if uvs is not None:
                document["meshes"][0]["triangles"][0]["uvs"] = uvs
            with self.subTest(uvs=uvs), self.assertRaises(ValueError):
                geometry(document, None)

    def test_mesh_uv_validation_checks_every_vertex(self):
        document = copy.deepcopy(self.document)
        document["meshes"][0]["triangles"][0]["uvs"] = [[0, 0], [1, 0], [0, 1]]
        output, _ = export(document, self.template, self.diffuse, None)
        model = Model(output)
        render = next(c for c in walk(model.tree) if c["id"] == "0x0001b006")
        uv_address = model.packets[0]["streams"][3]["address"]
        corrupted = bytearray(output)
        struct.pack_into(">2h", corrupted, payload(render)[0] + uv_address + 8, 2000, 0)
        with self.assertRaisesRegex(ValueError, "outside texture bounds"):
            validate(bytes(corrupted), self.diffuse, None)

    def test_corrupt_weight_and_truncated_file_rejected(self):
        output, _ = self.export()
        model = Model(output)
        pairs = next(c for c in walk(model.tree) if c["id"] == "0x0001b00e")
        corrupted = bytearray(output)
        struct.pack_into(">H", corrupted, pairs["data_offset"] + 2, 1)
        with self.assertRaises(ValueError):
            validate(bytes(corrupted), self.diffuse, self.blocks)
        with self.assertRaises(ValueError):
            validate(output[:-1], self.diffuse, self.blocks)


@unittest.skipUnless(TEMPLATE.is_file() and Path(
        "mods/palmeiras/assets/work/player-intermediate.json").is_file(), "Requires Blender intermediate")
class FullPipelineTests(unittest.TestCase):
    def test_generate_writes_bundle_and_models(self):
        import json
        import tempfile

        intermediate = Path("mods/palmeiras/assets/work/player-intermediate.json")
        with tempfile.TemporaryDirectory() as directory:
            results = generate(output=Path(directory))
            self.assertEqual(results["texture"]["hash"], f"0x{lower_hash(TEXTURE_NAME):08x}")
            bundle = (Path(directory) / "Mario.glt").read_bytes()
            new_hash, _ = validate_bundle(bundle, parse_bundle(BUNDLE.read_bytes()))
            self.assertEqual(f"0x{new_hash:08x}", results["texture"]["hash"])
            document = json.loads(intermediate.read_text())
            colors = [m["base_color"] for mesh in document["meshes"] for m in mesh["materials"]]
            blocks = build_atlas(colors)[1]
            for name in ("Mario.glg", "Mario_blend.glg"):
                report = results[name]
                self.assertFalse(report["morph_buffer_used"])
                self.assertTrue(report["weight_totals_valid"])
                validate(Path(directory, name).read_bytes(), new_hash, blocks)


if __name__ == "__main__":
    unittest.main()
