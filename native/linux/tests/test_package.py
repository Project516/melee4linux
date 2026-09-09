# SPDX-License-Identifier: GPL-3.0-or-later
"""Check AppDir packaging inputs, library selection, and output validation."""

import importlib.util
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch
import zlib


SPEC = importlib.util.spec_from_file_location(
    "linux_package", Path(__file__).resolve().parents[1] / "package.py"
)
package = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(package)


class InputTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def make_input(self):
        dolphin = "upstream/ModernGekko-Template/lib/ModernGekko/vendor/dolphin"
        for name in (
            "build/runtime/MeleeRuntime", "build/runtime/MeleeLauncher", "build/dolrecomp/dolrecomp",
            "build/runtime/melee-build-id.txt", "build/runtime/Sys/test.ini", "LICENSE", "CREDITS.md",
            f"{dolphin}/module-template/module_export.c", f"{dolphin}/module-template/module.exports",
            f"{dolphin}/module-template/gen_module_tables.py", f"{dolphin}/GXRuntime/include/core/cpu.h",
            f"{dolphin}/Source/Core/Core/PowerPC/StaticRecomp/StaticRecompABI.h",
        ):
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"test input")

    def test_missing_runtime_stops_before_packaging(self):
        with self.assertRaisesRegex(package.PackageError, "MeleeRuntime"):
            package.validate_inputs(self.root)

    def test_complete_input_passes(self):
        self.make_input()
        package.validate_inputs(self.root)

    def test_empty_sys_directory_is_rejected(self):
        self.make_input()
        (self.root / "build/runtime/Sys/test.ini").unlink()
        with self.assertRaisesRegex(package.PackageError, "resource directory"):
            package.validate_inputs(self.root)

    def test_texture_pack_rejects_missing_textures_and_symlinks(self):
        with self.assertRaisesRegex(package.PackageError, "DDS textures"):
            package.validate_texture_pack(self.root)
        textures = self.root / "GALE01"
        textures.mkdir()
        (textures / "texture.dds").write_bytes(b"DDS test")
        self.assertEqual(package.validate_texture_pack(self.root), self.root.resolve())
        (textures / "external.dds").symlink_to(textures / "texture.dds")
        with self.assertRaisesRegex(package.PackageError, "symbolic links"):
            package.validate_texture_pack(self.root)


class OutputTests(unittest.TestCase):
    def test_output_suffix_matches_mode(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with self.assertRaisesRegex(package.PackageError, "AppImage"):
                package.validate_output(root / "Melee.tar", replace=False, appdir=False)
            with self.assertRaisesRegex(package.PackageError, "AppDir"):
                package.validate_output(root / "Melee.AppImage", replace=False, appdir=True)
            package.validate_output(root / "Melee.AppImage", replace=False, appdir=False)

    def test_existing_output_needs_replace(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "Melee.AppImage"
            output.write_bytes(b"old")
            with self.assertRaisesRegex(package.PackageError, "--replace"):
                package.validate_output(output, replace=False, appdir=False)
            package.validate_output(output, replace=True, appdir=False)
            link = Path(temporary) / "Link.AppImage"
            link.symlink_to(output)
            with self.assertRaisesRegex(package.PackageError, "symbolic link"):
                package.validate_output(link, replace=True, appdir=False)


class LibraryTests(unittest.TestCase):
    def test_system_and_driver_libraries_stay_on_the_host(self):
        for name in ("libc.so.6", "ld-linux-aarch64.so.1", "libstdc++.so.6", "libgcc_s.so.1", "libGL.so.1",
                     "libvulkan.so.1", "libX11.so.6", "libxcb.so.1", "libasound.so.2", "libdrm.so.2",
                     "libz.so.1", "libudev.so.1"):
            self.assertTrue(package.EXCLUDED_LIBRARIES.match(name), name)

    def test_desktop_libraries_are_bundled(self):
        for name in ("libpulse.so.0", "libpulsecommon-16.1.so", "libwayland-client.so.0", "libXrandr.so.2",
                     "libXi.so.6", "libatomic.so.1", "libxkbcommon.so.0", "libbluetooth.so.3"):
            self.assertIsNone(package.EXCLUDED_LIBRARIES.match(name), name)

    def test_dependencies_parse_ldd_and_skip_excluded(self):
        output = ("\tlinux-vdso.so.1 (0x0000ffff)\n"
                  "\tlibpulse.so.0 => /usr/lib/aarch64-linux-gnu/libpulse.so.0 (0x0000ffff8000)\n"
                  "\tlibc.so.6 => /lib/aarch64-linux-gnu/libc.so.6 (0x0000ffff7000)\n"
                  "\t/lib/ld-linux-aarch64.so.1 (0x0000ffff9000)\n")
        with patch.object(package, "run", return_value=output):
            self.assertEqual(package.dependencies(Path("/tmp/bin")),
                             [Path("/usr/lib/aarch64-linux-gnu/libpulse.so.0")])

    def test_unresolved_dependency_fails(self):
        with patch.object(package, "run", return_value="\tlibfoo.so.1 => not found\n"):
            with self.assertRaisesRegex(package.PackageError, "Unresolved library"):
                package.dependencies(Path("/tmp/bin"))


class IconTests(unittest.TestCase):
    def test_png_has_valid_header_and_size(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "icon.png"
            package.write_png(path, size=8)
            data = path.read_bytes()
            self.assertEqual(data[:8], b"\x89PNG\r\n\x1a\n")
            length, kind = struct.unpack(">I4s", data[8:16])
            self.assertEqual((length, kind), (13, b"IHDR"))
            self.assertEqual(struct.unpack(">II", data[16:24]), (8, 8))
            crc = struct.unpack(">I", data[16 + length:20 + length])[0]
            self.assertEqual(crc, zlib.crc32(data[12:16 + length]) & 0xFFFFFFFF)


class PinTests(unittest.TestCase):
    def test_every_architecture_pins_every_tool_with_a_sha256(self):
        for arch, pins in package.DOWNLOADS.items():
            self.assertEqual(sorted(pins), ["appimage-runtime", "appimagetool", "ninja", "python", "zig"], arch)
            for name, (url, digest) in pins.items():
                self.assertTrue(url.startswith("https://"), (arch, name))
                self.assertRegex(digest, r"^[0-9a-f]{64}$", (arch, name))
                self.assertIn(arch if arch == "aarch64" else "x86_64", url.replace("linux.zip", "x86_64"),
                              (arch, name))


if __name__ == "__main__":
    unittest.main()
