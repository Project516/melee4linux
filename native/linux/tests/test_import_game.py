# SPDX-License-Identifier: GPL-3.0-or-later
"""Check the module builder's inputs, identity stamp, and generated build rules."""

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


SPEC = importlib.util.spec_from_file_location(
    "import_game", Path(__file__).resolve().parents[1] / "import_game.py"
)
importer = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = importer
SPEC.loader.exec_module(importer)


def make_tools(root: Path) -> importer.Tools:
    share = root / "share"
    for relative in (
            "zig/zig", "ninja", "module/module_export.c", "module/module.exports",
            "module/gen_module_tables.py", "module/gxruntime/include/core/cpu.h",
            "module/staticrecomp/StaticRecompABI.h",
            *(f"module/gxruntime/src/core/{name}" for name in importer.CPU_SOURCES)):
        path = share / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("test")
    (share / "build-id.txt").write_text("melee4linux=test\n")
    dolrecomp = root / "bin/dolrecomp"
    dolrecomp.parent.mkdir(parents=True)
    dolrecomp.write_text("test")
    return importer.Tools(share, dolrecomp)


def make_generated(root: Path, chunks: int) -> Path:
    generated = root / "generated"
    (generated / "chunks").mkdir(parents=True)
    (generated / "generated.h").write_text("void func_80003100(CPUState* ctx);\n")
    (generated / "generated_smc.txt").write_text("")
    for index in range(chunks):
        (generated / "chunks" / f"chunk_{index:04d}_text_8000{index:04X}.c").write_text("")
    return generated


class ToolsTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def test_incomplete_tools_are_reported(self):
        tools = make_tools(self.root)
        (tools.module / "module.exports").unlink()
        with self.assertRaisesRegex(importer.ImportError_, "module.exports"):
            tools.check()

    def test_build_id_falls_back_for_checkouts(self):
        tools = make_tools(self.root)
        self.assertEqual(tools.build_id, "melee4linux=test")
        (tools.root / "build-id.txt").unlink()
        self.assertEqual(tools.build_id, "development")


class GameCheckTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.game = Path(self.temporary.name) / "GALE01"
        (self.game / "sys").mkdir(parents=True)
        (self.game / "sys/main.dol").write_bytes(b"executable")
        (self.game / "sys/apploader.img").write_bytes(b"loader")

    def test_rejects_other_executables_with_both_hashes(self):
        with self.assertRaisesRegex(importer.ImportError_, "USA v1.02.*expected 08e0bf20") as context:
            importer.check_game(self.game)
        self.assertIn(hashlib.sha1(b"executable").hexdigest(), str(context.exception))

    def test_accepts_the_verified_executable(self):
        with patch.object(importer, "DOL_SHA1", hashlib.sha1(b"executable").hexdigest()):
            self.assertEqual(importer.check_game(self.game), importer.DOL_SHA1)

    def test_requires_the_disc_loader(self):
        (self.game / "sys/apploader.img").unlink()
        with self.assertRaisesRegex(importer.ImportError_, "incomplete"):
            importer.check_game(self.game)


class StampTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.tools = make_tools(self.root)
        self.module = self.root / "StaticRecompModules" / importer.MODULE_NAME
        self.module.parent.mkdir()
        self.module.write_bytes(b"module")

    def test_current_module_needs_matching_stamp(self):
        self.assertFalse(importer.module_current(self.module, self.tools, "abc"))
        stamp = importer.stamp_identity(self.tools, "abc")
        importer.stamp_path(self.module).write_text(json.dumps(stamp))
        self.assertTrue(importer.module_current(self.module, self.tools, "abc"))

    def test_new_build_or_executable_invalidates_module(self):
        importer.stamp_path(self.module).write_text(json.dumps(importer.stamp_identity(self.tools, "abc")))
        self.assertFalse(importer.module_current(self.module, self.tools, "def"))
        (self.tools.root / "build-id.txt").write_text("melee4linux=newer\n")
        self.assertFalse(importer.module_current(self.module, self.tools, "abc"))

    def test_corrupt_stamp_is_not_current(self):
        importer.stamp_path(self.module).write_text("{not json")
        self.assertFalse(importer.module_current(self.module, self.tools, "abc"))


class NinjaTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.tools = make_tools(self.root)
        self.build = self.root / "module-build"
        self.build.mkdir()

    def test_escapes_paths_and_keeps_ninja_variables(self):
        self.assertEqual(importer.ninja_path("/a b/c:d$e"), "/a$ b/c$:d$$e")
        command = importer.ninja_command(["/tool dir/zig", "cc", "-MF", "$out.d", "-c", '"$in"', '-DX="Y"'])
        self.assertEqual(command, "'/tool dir/zig' cc -MF $out.d -c \"$in\" '-DX=\"Y\"'")

    def test_groups_chunks_into_archives_and_links_once(self):
        generated = make_generated(self.root, importer.ARCHIVE_GROUP + 3)
        module = importer.write_ninja(self.build, self.tools, generated, "aarch64-linux-gnu.2.28")
        text = (self.build / "build.ninja").read_text()
        self.assertEqual(module, self.build / importer.MODULE_NAME)
        self.assertEqual(text.count(": ar "), 2)
        self.assertEqual(text.count(": link "), 1)
        self.assertEqual(text.count(": cc "), importer.ARCHIVE_GROUP + 3 + 1 + len(importer.CPU_SOURCES))
        self.assertIn("-ffp-contract=off -fno-fast-math -fvisibility=hidden", text)
        self.assertIn("-target aarch64-linux-gnu.2.28", text)
        self.assertIn("--whole-archive", text)
        self.assertIn("--version-script=", text)
        self.assertNotIn("DOLRECOMP_MODULE_HAVE_X86_64_V3", text)
        # The generated tables are a build input of the export glue only.
        self.assertRegex(text, r"build \S+/runtime/module_export\.o: cc \S+ \| \S+module_tables\.inc")

    def test_x86_64_v3_dispatch_is_enabled_from_the_generated_header(self):
        generated = make_generated(self.root, 1)
        (generated / "generated.h").write_text("dolrecomp_call__x86_64_v3\n")
        importer.write_ninja(self.build, self.tools, generated, "x86_64-linux-gnu.2.28")
        self.assertIn("-DDOLRECOMP_MODULE_HAVE_X86_64_V3=1", (self.build / "build.ninja").read_text())

    def test_no_chunks_is_an_error(self):
        generated = self.root / "generated"
        (generated / "chunks").mkdir(parents=True)
        (generated / "generated.h").write_text("")
        with self.assertRaisesRegex(importer.ImportError_, "no chunks"):
            importer.write_ninja(self.build, self.tools, generated, "aarch64-linux-gnu.2.28")

    @unittest.skipUnless(shutil.which("ninja"), "ninja is not installed")
    def test_generated_rules_parse_and_order(self):
        generated = make_generated(self.root / "with space", 4)
        # gen_module_tables.py writes this before ninja runs.
        (self.build / "module_tables.inc").write_text("")
        importer.write_ninja(self.build, self.tools, generated, "aarch64-linux-gnu.2.28")
        result = subprocess.run(["ninja", "-C", str(self.build), "-n"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("LINK", result.stdout)


class StatusTests(unittest.TestCase):
    def test_status_file_is_replaced_atomically_with_all_fields(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "Setup/import-status.txt"
            status = importer.Status(path)
            status.update("Compiling native code", 3, 10)
            self.assertEqual(
                path.read_text(), "message=Compiling native code\ncompleted=3\ntotal=10\ndone=0\nerror=\n")
            status.update("Native module build failed", done=True, error="boom")
            self.assertIn("done=1\nerror=boom\n", path.read_text())
            self.assertEqual(sorted(p.name for p in path.parent.iterdir()), ["import-status.txt"])


class JobsTests(unittest.TestCase):
    def test_default_jobs_is_bounded_by_memory_and_cpus(self):
        with patch.object(os, "cpu_count", return_value=16), \
                patch("builtins.open", unittest.mock.mock_open(read_data="MemTotal:        2097152 kB\n")):
            self.assertEqual(importer.default_jobs(), 2)
        with patch.object(os, "cpu_count", return_value=2), \
                patch("builtins.open", unittest.mock.mock_open(read_data="MemTotal:       67108864 kB\n")):
            self.assertEqual(importer.default_jobs(), 2)


if __name__ == "__main__":
    unittest.main()
