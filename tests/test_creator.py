"""Creator helper contracts and documentation links. Original tests: MIT."""
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import struct
import sys
import tempfile
import types
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("creator", ROOT / "modding/creator.py")
creator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(creator)


class CreatorTests(unittest.TestCase):
    def test_name_edit_preserves_other_lookup_and_supports_unicode(self):
        def native_hash(text):
            value = 0xFFFFFFFF
            for byte in text.lower().encode("ascii"):
                value = (value * 33 + byte) & 0xFFFFFFFF
            return value
        keys = (native_hash("PALMEIRAS"), native_hash("other"))
        strings = "PALMEIRAS\0OTHER\0".encode("utf-16-be")
        header = bytearray(20)
        header[:4] = b"NLOC"
        struct.pack_into(">I", header, 12, 2)
        blob = header + struct.pack(">4I", keys[0], 0, keys[1], 10) + strings
        with tempfile.TemporaryDirectory() as directory:
            game = Path(directory)
            fe = game / "files/art/fe"
            fe.mkdir(parents=True)
            target = fe / "english.loc"
            target.write_bytes(blob)
            module = types.SimpleNamespace(lower_hash=native_hash)
            with mock.patch.dict(sys.modules, {"palmeiras_texture": module}):
                creator.edit_name(game, "PALMEIRAS", "CLUBE SÃO")
                with self.assertRaises(ValueError):
                    creator.edit_name(game, "missing", "NONE")
            after = target.read_bytes()
            table = struct.unpack_from(">4I", after, 20)
            self.assertEqual(table, (keys[0], len(strings) // 2, keys[1], 10))
            self.assertEqual(after[36:36 + len(strings)], strings)
            self.assertEqual(after[36 + len(strings):], "CLUBE SÃO\0".encode("utf-16-be"))

    def test_source_and_overlay_inventory_match(self):
        meta = json.loads((ROOT / "modding/source/upstream.json").read_text())
        self.assertEqual(meta["commit"], "d1f357ffeb1d8e89311edebf9a4b304b05ece7bb")
        self.assertEqual(hashlib.sha256((ROOT / "modding/source/combined-mod.patch").read_bytes()).hexdigest(), meta["patch_sha256"])
        for path, digest in meta["overlay_sha256"].items():
            self.assertEqual(hashlib.sha256((ROOT / "modding/overlay" / path).read_bytes()).hexdigest(), digest, path)

    def test_all_local_markdown_and_media_links_exist(self):
        for path in ROOT.rglob("*.md"):
            if any(part in (".git", "dist") for part in path.parts):
                continue
            text = path.read_text()
            links = re.findall(r"\]\(([^)]+)\)", text) + re.findall(r'(?:href|src)="([^"]+)"', text)
            for link in links:
                if re.match(r"[a-z]+:", link) or link.startswith("#"):
                    continue
                target = link.split("#", 1)[0]
                self.assertTrue((path.parent / target).exists(), f"Broken link in {path.relative_to(ROOT)}: {link}")


if __name__ == "__main__":
    unittest.main()
