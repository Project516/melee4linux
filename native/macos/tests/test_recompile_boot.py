# SPDX-License-Identifier: GPL-3.0-or-later
"""Check the binary boundaries of the local native compilation input."""

import hashlib
import importlib.util
from pathlib import Path
import struct
import unittest
from unittest.mock import patch


spec = importlib.util.spec_from_file_location(
    "recompile_boot", Path(__file__).resolve().parents[1] / "recompile_boot.py"
)
boot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(boot)


class CompilationInputTests(unittest.TestCase):
    def setUp(self):
        self.game = bytearray(0x140)
        struct.pack_into(">I", self.game, 0, 0x100)
        struct.pack_into(">I", self.game, 0x48, 0x80003100)
        struct.pack_into(">I", self.game, 0x90, 0x40)
        struct.pack_into(">I", self.game, 0xE0, 0x80003104)
        self.game[0x100:] = bytes(range(0x40))
        self.loader = bytearray(32 + 64 + 32)
        struct.pack_into(">III", self.loader, 0x10, 0x81200004, 64, 32)
        self.loader[32:] = bytes(range(96))
        self.hash = patch.object(boot, "DOL_SHA1", hashlib.sha1(self.game).hexdigest())
        self.hash.start()
        self.addCleanup(self.hash.stop)
        for name, value in (
            ("LOADER_SHA1", hashlib.sha1(self.loader).hexdigest()),
            ("LOADER_CODE_SIZE", 32),
        ):
            mock = patch.object(boot, name, value)
            mock.start()
            self.addCleanup(mock.stop)

    def test_preserves_game_and_appends_loader_at_its_load_address(self):
        game_before = bytes(self.game)
        loader_before = bytes(self.loader)
        result = boot.compilation_dol(self.game, self.loader)
        self.assertEqual(self.game, game_before)
        self.assertEqual(self.loader, loader_before)
        self.assertEqual(result[0x100:len(self.game)], game_before[0x100:])
        self.assertEqual(result[0xE0:0xE4], game_before[0xE0:0xE4])
        offset = struct.unpack_from(">I", result, 8)[0]
        address = struct.unpack_from(">I", result, 0x50)[0]
        size = struct.unpack_from(">I", result, 0x98)[0]
        self.assertEqual(address, 0x81200000)
        self.assertEqual(offset % 32, 0)
        self.assertEqual(size, 32)
        self.assertEqual(result[offset:], loader_before[32:])
        # Reconstruct the loaded bytes from each independent DOL section.
        loaded = bytearray(96)
        for slot in (2, 3, 15):
            file_offset = struct.unpack_from(">I", result, slot * 4)[0]
            address = struct.unpack_from(">I", result, 0x48 + slot * 4)[0]
            length = struct.unpack_from(">I", result, 0x90 + slot * 4)[0]
            start = address - 0x81200000
            loaded[start:start + length] = result[file_offset:file_offset + length]
        self.assertEqual(loaded, loader_before[32:])
        self.assertEqual(struct.unpack_from(">I", result, 0x98)[0], 32)
        self.assertEqual(struct.unpack_from(">I", result, 0xCC)[0], 32)

    def test_rejects_a_changed_game(self):
        self.game[-1] ^= 1
        with self.assertRaisesRegex(ValueError, "must match"):
            boot.compilation_dol(self.game, self.loader)

    def test_rejects_truncated_loader_header(self):
        with self.assertRaisesRegex(ValueError, "header"):
            boot.compilation_dol(self.game, self.loader[:31])

    def test_rejects_changed_loader_code(self):
        self.loader[40] ^= 1
        with self.assertRaisesRegex(ValueError, "loader must match"):
            boot.compilation_dol(self.game, self.loader)

    def test_rejects_missing_payload_and_unexpected_trailer(self):
        for loader in (self.loader[:-4], self.loader + b"extra"):
            with self.subTest(length=len(loader)), self.assertRaisesRegex(ValueError, "length"):
                boot.compilation_dol(self.game, loader)

    def test_rejects_entry_outside_loader_code_or_unaligned(self):
        for entry in (0x811FFFFC, 0x81200040, 0x81200002):
            struct.pack_into(">I", self.loader, 0x10, entry)
            with self.subTest(entry=entry), self.assertRaisesRegex(ValueError, "entry"):
                boot.compilation_dol(self.game, self.loader)

    def test_rejects_loader_that_overlaps_boot_scratch_memory(self):
        loader = bytearray(32 + 0x100004)
        struct.pack_into(">III", loader, 0x10, 0x81200004, 0x100004, 0)
        with self.assertRaisesRegex(ValueError, "scratch"):
            boot.compilation_dol(self.game, loader)


if __name__ == "__main__":
    unittest.main()
