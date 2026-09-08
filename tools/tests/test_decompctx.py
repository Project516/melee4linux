import contextlib
import io
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools import decompctx


class DecompContextTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.source = self.root / "src"
        self.source.mkdir()
        self.include = self.root / "include"
        self.include.mkdir()
        self.output = self.root / "ctx.c"
        self.depfile = self.root / "ctx.c.d"
        self.enterContext(patch.object(decompctx, "root_dir", str(self.root)))
        self.stdout = self.enterContext(contextlib.redirect_stdout(io.StringIO()))
        self.stderr = self.enterContext(contextlib.redirect_stderr(io.StringIO()))

    def run_cli(self, source="src/unit.c", *options, depfile=True):
        arguments = [
            "decompctx.py", str(self.root / source), "-I", str(self.include),
            "-o", "ctx.c", *options,
        ]
        if depfile:
            arguments += ["-d", "ctx.c.d"]
        with patch("sys.argv", arguments):
            return decompctx.main()

    def test_paths_resolve_from_a_different_working_directory(self):
        nested = self.root / "other"
        nested.mkdir()
        (self.source / "unit.c").write_text('#include "local.h"\n', encoding="utf-8")
        (self.source / "local.h").write_text('#include <shared.h>\n', encoding="utf-8")
        (self.include / "local.h").write_text("wrong search order\n", encoding="utf-8")
        (self.include / "shared.h").write_text("typedef int Shared;\n", encoding="utf-8")
        previous_directory = Path.cwd()
        try:
            os.chdir(nested)
            with patch("sys.argv", [
                "decompctx.py", "../src/unit.c", "-I", "../include",
                "-o", "ctx.c", "-d", "ctx.c.d",
            ]):
                self.assertEqual(decompctx.main(), 0)
        finally:
            os.chdir(previous_directory)

        context = self.output.read_text(encoding="utf-8")
        self.assertIn("typedef int Shared;", context)
        self.assertNotIn("wrong search order", context)
        self.assertFalse((nested / "ctx.c").exists())
        self.assertEqual(
            self.depfile.read_text(encoding="utf-8"),
            "ctx.c: \\\n\tsrc/unit.c \\\n\tsrc/local.h \\\n\tinclude/shared.h",
        )

    def test_repeat_runs_expand_guards_and_keep_dependencies(self):
        (self.source / "unit.c").write_text(
            '#ifndef UNIT_H\n#define UNIT_H\n#include "shared.h"\n'
            '#include "shared.h"\n#endif\n', encoding="utf-8",
        )
        (self.include / "shared.h").write_text(
            "#pragma once\ntypedef int Shared;\n", encoding="utf-8",
        )
        self.assertEqual(self.run_cli("src/unit.c", "-D", "VALUE=3", "-D", "FLAG"), 0)
        context = self.output.read_bytes()
        dependencies = self.depfile.read_bytes()
        self.assertEqual(context.count(b"typedef int Shared;"), 1)
        self.assertIn(
            "#define VALUE 3\n#define FLAG\n", self.output.read_text(encoding="utf-8"),
        )

        self.assertEqual(self.run_cli("src/unit.c", "-D", "VALUE=3", "-D", "FLAG"), 0)
        self.assertEqual(self.output.read_bytes(), context)
        self.assertEqual(self.depfile.read_bytes(), dependencies)

    def test_missing_include_fails_without_replacing_existing_outputs(self):
        (self.source / "unit.c").write_text(
            '#ifndef UNIT_H\n#define UNIT_H\n#include "missing.h"\n#endif\n',
            encoding="utf-8",
        )
        self.output.write_bytes(b"working context")
        self.depfile.write_bytes(b"working dependencies")
        self.assertEqual(self.run_cli(), 1)
        self.assertIn('unit.c:3: cannot find include "missing.h"', self.stderr.getvalue())
        self.assertEqual(self.output.read_bytes(), b"working context")
        self.assertEqual(self.depfile.read_bytes(), b"working dependencies")

        # A failure has already recorded UNIT_H. A second run must still expand it.
        (self.include / "missing.h").write_text("typedef int Found;\n", encoding="utf-8")
        self.assertEqual(self.run_cli(), 0)
        self.assertIn("typedef int Found;", self.output.read_text(encoding="utf-8"))

    def test_excluded_headers_and_assembly_includes_still_work(self):
        (self.source / "unit.c").write_text(
            '#include "generated/table.h"\n#include "function.s"\nint value;\n',
            encoding="utf-8",
        )
        self.assertEqual(self.run_cli("src/unit.c", "-x", "generated/*.h"), 0)
        context = self.output.read_text(encoding="utf-8")
        self.assertIn("/* Skipped excluded file */", context)
        self.assertIn('#include "function.s"\nint value;', context)
        self.assertEqual(self.stderr.getvalue(), "")

    def test_encoding_fallback_reads_before_processing(self):
        (self.source / "unit.c").write_bytes(
            b'#ifndef UNIT_H\n#define UNIT_H\n/* caf\xe9 */\n#include "shared.h"\n#endif\n'
        )
        (self.include / "shared.h").write_text("typedef int Shared;\n", encoding="utf-8")
        real_open = open

        def locale_open(path, **options):
            # Use a fixed locale encoding so the fallback test is portable.
            return real_open(path, encoding=options.get("encoding", "latin-1"))

        with patch.object(decompctx, "open", side_effect=locale_open, create=True):
            self.assertEqual(self.run_cli(), 0)
        context = self.output.read_text(encoding="utf-8")
        self.assertIn("/* café */", context)
        self.assertEqual(context.count("typedef int Shared;"), 1)

    def test_failed_output_replacement_keeps_existing_context_and_cleans_up(self):
        (self.source / "unit.c").write_text("int replacement;\n", encoding="utf-8")
        self.output.write_bytes(b"working context")
        before = set(self.root.iterdir())
        with patch.object(decompctx.os, "replace", side_effect=OSError("disk error")):
            self.assertEqual(self.run_cli(depfile=False), 1)
        self.assertEqual(self.output.read_bytes(), b"working context")
        self.assertEqual(set(self.root.iterdir()), before)
        self.assertIn("disk error", self.stderr.getvalue())

    def test_failed_dependency_write_keeps_existing_context(self):
        (self.source / "unit.c").write_text("int replacement;\n", encoding="utf-8")
        self.output.write_bytes(b"working context")
        self.assertEqual(
            self.run_cli("src/unit.c", "-d", "missing/directory/ctx.d", depfile=False), 1,
        )
        self.assertEqual(self.output.read_bytes(), b"working context")

    def test_cli_missing_source_has_failure_status_and_no_traceback(self):
        result = subprocess.run(
            [
                sys.executable, str(Path(decompctx.__file__).resolve()),
                str(self.source / "missing.c"), "-I", str(self.include),
                "-o", str(self.output),
            ],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("missing.c", result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        self.assertFalse(self.output.exists())


if __name__ == "__main__":
    unittest.main()
