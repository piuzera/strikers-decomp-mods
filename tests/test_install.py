"""Installer regression tests; synthetic data only, no game or Dolphin needed.

Copyright (c) 2026 piuzera. Licensed under the MIT License.
"""

import bz2
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import install


def number(value):
    return (abs(value) | ((1 << 63) if value < 0 else 0)).to_bytes(8, "little")


def patch(controls, differences, extra, size):
    control = bz2.compress(b"".join(number(v) for row in controls for v in row))
    diff = bz2.compress(differences)
    return b"BSDIFF40" + number(len(control)) + number(len(diff)) + number(size) + control + diff + bz2.compress(extra)


def record(path, data):
    return {"path": path, "size": len(data), "sha256": hashlib.sha256(data).hexdigest()}


class DecoderTests(unittest.TestCase):
    def test_difference_extra_and_negative_seek(self):
        data = patch([(3, 1, -3), (3, 0, 0)], b"\0\1\0\0\0\1", b"!", 7)
        self.assertEqual(install.apply_bsdiff(b"abc", data, 7), b"acc!abd")

    def test_negative_source_position_and_empty_target(self):
        data = patch([(0, 0, -1), (2, 0, 0)], b"X\0", b"", 2)
        self.assertEqual(install.apply_bsdiff(b"ab", data, 2), b"Xa")
        self.assertEqual(install.apply_bsdiff(b"unused", patch([], b"", b"", 0), 0), b"")

    def test_corrupt_patch_bounds_and_size_are_rejected(self):
        cases = [b"bad", patch([(4, 0, 0)], b"abc", b"", 3),
                 patch([(-1, 0, 0)], b"", b"", 3),
                 patch([(3, 0, 0)], b"ab", b"", 3),
                 patch([(0, 3, 0)], b"", b"ab", 3),
                 patch([(3, 0, 0)], b"abcX", b"", 3)]
        for data in cases:
            with self.subTest(data=data[:32]), self.assertRaises(ValueError):
                install.apply_bsdiff(b"abc", data, 3)
        with self.assertRaises(ValueError):
            install.apply_bsdiff(b"abc", patch([(3, 0, 0)], b"\0\0\0", b"", 3), 4)


class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root / "clean"
        self.package = self.root / "package"
        self.output = self.root / "mod"
        (self.source / "sys").mkdir(parents=True)
        (self.source / "files").mkdir()
        (self.package / "patches").mkdir(parents=True)
        (self.source / "sys/main.dol").write_bytes(b"synthetic-game")
        (self.source / "files/user.ini").write_bytes(b"")
        (self.source / "private-log.txt").write_bytes(b"must not be copied")
        self.data = patch([(0, 3, 0)], b"", b"mod", 3)
        (self.package / "patches/test.bsdiff").write_bytes(self.data)
        self.manifest = {"format": 1, "patch_format": "BSDIFF40", "release": "test",
                         "source_files": [record("sys/main.dol", b"synthetic-game"), record("files/user.ini", b"")],
                         "output_files": [record("sys/main.dol", b"mod"), record("files/user.ini", b""), record("files/new.dat", b"mod")],
                         "patches": [{"target": name, "source": "sys/main.dol", "patch": "patches/test.bsdiff",
                                      "patch_size": len(self.data), "patch_sha256": hashlib.sha256(self.data).hexdigest(),
                                      "target_size": 3, "target_sha256": hashlib.sha256(b"mod").hexdigest()}
                                     for name in ("sys/main.dol", "files/new.dat")]}
        self.write_manifest()
        self.retail_hash = mock.patch.object(install, "RETAIL_DOL_SHA1", hashlib.sha1(b"synthetic-game").hexdigest())
        self.retail_hash.start()
        self.addCleanup(self.retail_hash.stop)

    def write_manifest(self):
        (self.package / "manifest.json").write_text(json.dumps(self.manifest))

    def apply(self):
        install.install(self.source, self.output, self.package)

    def test_install_new_files_verify_and_preserve_source(self):
        self.apply()
        install.verify(self.output, self.package)
        self.assertEqual((self.source / "sys/main.dol").read_bytes(), b"synthetic-game")
        self.assertEqual((self.output / "files/new.dat").read_bytes(), b"mod")
        self.assertEqual((self.output / "files/user.ini").read_bytes(), b"")
        self.assertFalse((self.output / "private-log.txt").exists())
        (self.output / "files/new.dat").write_bytes(b"bad")
        with self.assertRaises(ValueError):
            install.verify(self.output, self.package)

    def test_wrong_game_corrupt_input_and_corrupt_patch_leave_no_output(self):
        for relative, data in (("sys/main.dol", b"wrong-game"), ("files/user.ini", b"modified")):
            target = self.source / relative
            old = target.read_bytes()
            target.write_bytes(data)
            with self.assertRaises(ValueError):
                self.apply()
            self.assertFalse(self.output.exists())
            target.write_bytes(old)
        (self.package / "patches/test.bsdiff").write_bytes(b"corrupt")
        with self.assertRaises(ValueError):
            self.apply()
        self.assertFalse(self.output.exists())

    def test_failed_output_hash_cleans_temporary_directory(self):
        self.manifest["patches"][0]["target_sha256"] = "0" * 64
        self.write_manifest()
        with self.assertRaises(ValueError):
            self.apply()
        self.assertFalse(self.output.exists())
        self.assertEqual(list(self.root.glob(".mod-install-*")), [])

    def test_refuse_existing_or_nested_output(self):
        self.output.mkdir()
        (self.output / "keep").write_text("existing user work")
        with self.assertRaises(ValueError):
            self.apply()
        self.assertEqual((self.output / "keep").read_text(), "existing user work")
        with self.assertRaises(ValueError):
            install.install(self.source, self.source / "nested", self.package)

    def test_unsafe_paths_are_rejected(self):
        for value in ("../escape", "/absolute", "C:/absolute", "foo\\bar", ""):
            with self.subTest(value=value), self.assertRaises(ValueError):
                install.safe_path(self.root, value)
        self.manifest["patches"][0]["target"] = "../escape"
        self.write_manifest()
        with self.assertRaises(ValueError):
            self.apply()
        self.assertFalse(self.output.exists())

    def test_launch_enforces_memory_and_preserves_controls(self):
        self.apply()
        controls = self.root / "mod-dolphin-user/Config/GCPadNew.ini"
        controls.parent.mkdir(parents=True)
        controls.write_text("user controls")
        with mock.patch.object(install, "ROOT", self.package), \
                mock.patch.object(install, "verify") as verify, \
                mock.patch.object(install, "find_dolphin", return_value="Dolphin"), \
                mock.patch.object(install.subprocess, "run") as run:
            install.launch(self.output)
        verify.assert_called_once_with(self.output)
        args = run.call_args.args[0]
        self.assertIn("Dolphin.Core.RAMOverrideEnable=True", args)
        self.assertIn("Dolphin.Core.MEM1Size=50331648", args)
        self.assertIn(str(self.output / "sys/main.dol"), args)
        self.assertEqual(controls.read_text(), "user controls")


if __name__ == "__main__":
    unittest.main()
