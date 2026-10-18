"""Native palette/mip round trips and authored-art staging regressions."""

import json
import shutil
import struct
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import native_ui_art as art
from extract_native_references import decode_texture, png_bytes


def ci8_template(width, height, levels):
    size = sum((width >> i) * (height >> i) for i in range(levels))
    return struct.pack(">II5BxHH2xIII", levels, 8, 5, 5, 5, 4, 0, width, height, 256, 0, 0) + bytes(size + 512)


class NativeUIEncodingTests(unittest.TestCase):
    def test_tile_order_transparency_and_mip_colours_survive_round_trip(self):
        rows = [[((255, 0, 0, 255) if x % 2 == 0 else (0, 0, 0, 0))
                 if y < 4 else ((0, 255, 0, 255) if x < 8 else (0, 0, 255, 255))
                 for x in range(16)] for y in range(8)]
        template = ci8_template(16, 8, 2)
        encoded = art.encode_ci8(template, rows)
        self.assertEqual(encoded[:32], template[:32])
        self.assertEqual(len(encoded), len(template))
        width, height, decoded, _, levels = decode_texture(encoded)
        self.assertEqual((width, height, levels), (16, 8, 2))
        self.assertEqual(decoded, rows)
        palette_offset = 32 + 16 * 8 + 8 * 4
        palette = [art.expand(v) for v in struct.unpack_from(">256H", encoded, palette_offset)]
        # First mip pixel covers red plus transparent black: preserve red RGB
        # and intermediate alpha rather than making a dark or opaque fringe.
        first = palette[encoded[32 + 16 * 8]]
        self.assertEqual(first[:3], (255, 0, 0))
        self.assertGreater(first[3], 0)
        self.assertLess(first[3], 255)

    def test_direct_texture_keeps_authored_canvas_and_alpha(self):
        rows = [[(255, 255, 255, 255) if x == y else (0, 0, 0, 0) for x in range(8)] for y in range(8)]
        width, height, decoded, fmt, levels = decode_texture(art.encode_rgb5a3(rows))
        self.assertEqual((width, height, fmt, levels), (8, 8, "RGB5A3", 1))
        self.assertEqual(decoded, rows)

    def test_high_colour_art_quantizes_to_native_allocation_without_tinting(self):
        rows = [[(x * 8, y * 16, (x * 17 + y * 13) % 256, 255) for x in range(32)] for y in range(16)]
        encoded = art.encode_ci8(ci8_template(32, 16, 2), rows)
        _, _, decoded, _, _ = decode_texture(encoded)
        error = sum(abs(a - b) for source, target in zip(rows, decoded)
                    for original, actual in zip(source, target) for a, b in zip(original[:3], actual[:3]))
        self.assertLess(error / (32 * 16 * 3), 25)
        self.assertTrue(all(p[3] == 255 for row in decoded for p in row))
        self.assertLessEqual(len({p for row in decoded for p in row}), 256)

    @unittest.skipUnless(shutil.which("magick"), "Requires ImageMagick")
    def test_rectangular_png_dimensions_are_read_instead_of_guessed(self):
        rows = [[(255, 0, 0, 255)] * 16 for _ in range(8)]
        with tempfile.TemporaryDirectory(prefix="strikers-ui-art-") as directory:
            path = Path(directory) / "banner.png"
            path.write_bytes(png_bytes(16, 8, rows))
            self.assertEqual(art.read_rgba(path), rows)
            with self.assertRaisesRegex(ValueError, "must be"):
                art.load_art({"banner": path}, {"banner": (8, 16)})


class AuthoredUIStagingTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("magick"), "Requires ImageMagick")
    def test_fast_banner_update_refreshes_both_formats_and_manifest(self):
        import hashlib
        import combined_mod as combined
        import palmeiras_team as team
        rows = [[(255, 0, 0, 255) if x < 128 else (0, 0, 0, 0) for x in range(256)] for _ in range(64)]
        with tempfile.TemporaryDirectory(prefix="strikers-banner-") as directory:
            root = Path(directory)
            disc = root / "disc"
            fe = disc / "files/art/fe"
            fe.mkdir(parents=True)
            (disc / "sys").mkdir()
            (disc / "sys/main.dol").write_bytes(b"fixture")
            png = root / "banner.png"
            png.write_bytes(png_bytes(256, 64, rows))
            native = ci8_template(256, 64, 4)
            target = team.lower_hash("fe/captain_icons/captain_icons_palmeiras")
            files = ("BootUI.Res", "InGameUI.Res", "MainUI.Dmn", "CaptainIconsUI.Res")
            for name in files:
                key, blob = (target, native) if name == files[-1] else (team.HEADER_HASH, b"old banner")
                (fe / name).write_bytes(team.pack_bundle(32, [(123, b"retained native"), (key, blob)]))
            manifest = {"runtime_verified": True, "sha256": {},
                        "ui_art": {"palmeiras": {"sources": {"icons": {"path": str(png), "sha256": "old"}}}}}
            (root / "manifest.json").write_text(json.dumps(manifest))
            with mock.patch.object(combined, "BUILD", root), mock.patch.object(combined, "DISC", disc), \
                    mock.patch.object(team, "HEADER_PNG", png):
                combined.update_badge()
            result = json.loads((root / "manifest.json").read_text())
            self.assertFalse(result["runtime_verified"])
            self.assertEqual(result["ui_art"]["palmeiras"]["sources"]["icons"]["sha256"], hashlib.sha256(png.read_bytes()).hexdigest())
            for name in files:
                path = fe / name
                entries = dict(team.unpack_bundle(path.read_bytes())[1])
                self.assertEqual(entries[123], b"retained native")
                blob = entries[target if name == files[-1] else team.HEADER_HASH]
                self.assertEqual(decode_texture(blob)[2], rows)
                if name == files[-1]:
                    self.assertEqual(blob[:32], native[:32])
                    self.assertEqual(len(blob), len(native))
                self.assertEqual(result["sha256"][str(path.relative_to(disc))], hashlib.sha256(path.read_bytes()).hexdigest())
            self.assertEqual((root / "manifest.json").read_bytes(), (disc / "combined-manifest.json").read_bytes())

    def test_native_sidekicks_keep_palmeiras_pairing_resources(self):
        import palmeiras_team as team
        aliases = team.resource_aliases()
        for folder in ("cup_loadingscreenssidekicks", "supercup_loadingscreenssidekicks"):
            for kick in ("toad", "koopa", "hammerbro", "birdo"):
                for suffix in ("", "_bg"):
                    source = team.lower_hash(f"fe/{folder}/{kick}_daisy_l{suffix}")
                    target = team.lower_hash(f"fe/{folder}/{kick}_palmeiras_l{suffix}")
                    self.assertEqual(aliases[source], (target, None))

    def test_staged_ui_is_encoded_from_authored_sources_and_name_is_uppercase(self):
        import combined_mod as combined
        import human_sidekick as human
        import palmeiras_team as team
        manifest_path = combined.DISC / "combined-manifest.json"
        if not manifest_path.is_file():
            self.skipTest("Requires a locally staged combined disc")
        manifest = json.loads(manifest_path.read_text())
        self.assertEqual(manifest["ui_art"]["human"]["display_name"], "HUMAN")
        entries = dict(team.unpack_bundle((combined.DISC / "files/art/fe/MainUI.Dmn").read_bytes())[1])
        for key, path in ((team.CREST_HASH, team.ART["crest"]),
                          (team.HEADER_HASH, team.HEADER_PNG), (human.ICON_HASH, human.PORTRAIT)):
            _, _, pixels, _, _ = decode_texture(entries[key])
            expected = [[art.expand(art.quantize(p)) for p in row] for row in art.read_rgba(path)]
            self.assertEqual(pixels, expected, str(path))
        for path in (combined.DISC / "files/art/fe").glob("*.loc"):
            blob = path.read_bytes()
            if blob[:4] != b"NLOC":
                continue
            count = struct.unpack_from(">I", blob, 12)[0]
            table = dict(struct.unpack_from(">II", blob, 20 + i * 8) for i in range(count))
            strings = blob[20 + count * 8:]
            start = table[team.lower_hash("HUMAN")] * 2
            self.assertEqual(strings[start:start + 12].decode("utf-16-be"), "HUMAN\0", path.name)


if __name__ == "__main__":
    unittest.main()
