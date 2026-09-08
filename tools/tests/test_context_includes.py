import contextlib
import io
import os
import shlex
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools import decompctx
from tools.project import context_include_flags


class ContextIncludeTests(unittest.TestCase):
    def test_compiler_include_forms_keep_their_order(self):
        self.assertEqual(
            context_include_flags(["-O4", "-i first", "-I second", "-I+third"]),
            "-I first -I second -I third",
        )

    def test_recursive_compiler_path_finds_internal_headers(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            previous_directory = Path.cwd()
            try:
                os.chdir(root)
                Path("sdk/os").mkdir(parents=True)
                Path("sdk/dvd").mkdir()
                Path("first").mkdir()
                Path("last").mkdir()
                Path("unit.c").write_text(
                    '#include <public.h>\n#include <__os.h>\n', encoding="utf-8"
                )
                Path("first/public.h").write_text("int public_value;\n", encoding="utf-8")
                Path("sdk/os/__os.h").write_text("int internal_value;\n", encoding="utf-8")
                Path("last/__os.h").write_text("int wrong_value;\n", encoding="utf-8")
                flags = context_include_flags(["-i first", "-ir sdk", "-i last"])
                with (
                    patch.object(decompctx, "root_dir", str(root)),
                    patch("sys.argv", ["decompctx.py", "unit.c", *shlex.split(flags)]),
                    contextlib.redirect_stdout(io.StringIO()),
                ):
                    self.assertEqual(decompctx.main(), 0)
                context = Path("ctx.c").read_text(encoding="utf-8")
                self.assertIn("int public_value;", context)
                self.assertIn("int internal_value;", context)
                self.assertNotIn("int wrong_value;", context)
            finally:
                os.chdir(previous_directory)


if __name__ == "__main__":
    unittest.main()
