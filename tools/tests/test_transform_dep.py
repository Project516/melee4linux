import os
import posixpath
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools import transform_dep


class TransformDependenciesTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.source = self.directory / "source.d"

    def transform(self, text):
        self.source.write_text(text, encoding="utf-8")
        return transform_dep.import_d_file(str(self.source))

    def test_normal_paths_keep_continuations_and_existing_output(self):
        original = (
            r"build\source.o: src\source.c" + " \\\n"
            + "\t" + r"Z:\project\first.h" + " \\\n"
            + "\t" + r"Z:\project\second.h" + " \n"
        )
        self.assertEqual(
            self.transform(original),
            "build/source.o: src/source.c \\\n"
            "\t/project/first.h \\\n"
            "\t/project/second.h\n",
        )

    def test_mwcc_space_escapes_survive_in_targets_and_dependencies(self):
        # MWCC emits one header per line, with spaces escaped inside paths.
        original = (
            r"build\dep\ paths\source\ name.o: build\dep\ paths\source\ name.c"
            + " \\\n"
            + "\t" + r"Z:\project\dep\ paths\header\ name.h" + " \n"
        )
        self.assertEqual(
            self.transform(original),
            r"build/dep\ paths/source\ name.o: build/dep\ paths/source\ name.c"
            + " \\\n"
            + "\t" + r"/project/dep\ paths/header\ name.h" + "\n",
        )

    def test_empty_dependency_lines_do_not_create_paths(self):
        original = (
            "source.o: source.c \\\n"
            "\n \t\n"
            + "\t" + r"Z:\project\header.h" + "\n\n"
        )
        self.assertEqual(
            self.transform(original),
            "source.o: source.c \\\n\t/project/header.h\n",
        )

    def test_target_line_without_continuation_keeps_space_escapes(self):
        self.assertEqual(
            self.transform(r"source\ name.o: source\ name.c" + "\n"),
            r"source\ name.o: source\ name.c" + "\n",
        )

    def test_wsl_drive_mapping_keeps_spaces_and_z_root(self):
        original = (
            "source.o: source.c \\\n"
            + "\t" + r"D:\Program\ Files\header\ name.h" + " \\\n"
            + "\t" + r"Z:\project\last.h" + "\n"
        )
        # The branch runs on a Unix host. Use Unix joins on Windows CI too.
        with (
            patch.object(transform_dep, "in_wsl", return_value=True),
            patch.object(transform_dep.os.path, "join", side_effect=posixpath.join),
        ):
            self.assertEqual(
                self.transform(original),
                "source.o: source.c \\\n"
                + "\t" + r"/mnt/d/Program\ Files/header\ name.h" + " \\\n"
                + "\t/project/last.h\n",
            )

    def test_wine_resolves_unescaped_path_before_escaping_the_result(self):
        original = (
            "source.o: source.c \\\n"
            + "\t" + r"C:\Program\ Files\header\ name.h" + "\n"
        )
        devices = os.path.join(str(self.directory), "wine prefix", "dosdevices")
        resolved_path = "/wine prefix/drive_c/Program Files/header name.h"
        with (
            patch.object(transform_dep, "winedevices", devices),
            patch.object(transform_dep, "in_wsl", return_value=False),
            patch.object(transform_dep.os.path, "realpath", return_value=resolved_path) as resolve,
        ):
            converted = self.transform(original)
        resolve.assert_called_once_with(
            os.path.join(devices, "c:/Program Files/header name.h")
        )
        self.assertEqual(
            converted,
            "source.o: source.c \\\n"
            + "\t" + r"/wine\ prefix/drive_c/Program\ Files/header\ name.h" + "\n",
        )

    def test_missing_home_uses_a_default_or_the_wineprefix_override(self):
        environment = os.environ.copy()
        environment.pop("HOME", None)
        environment.pop("WINEPREFIX", None)
        root = Path(__file__).resolve().parents[2]
        command = [sys.executable, "-c", "from tools.transform_dep import winedevices; print(winedevices)"]
        for prefix in (None, str(self.directory / "custom wine")):
            with self.subTest(prefix=prefix):
                if prefix is not None:
                    environment["WINEPREFIX"] = prefix
                result = subprocess.run(
                    command, cwd=root, env=environment, capture_output=True,
                    text=True, check=False,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                if prefix is not None:
                    self.assertEqual(result.stdout.strip(), os.path.join(prefix, "dosdevices"))
                else:
                    self.assertTrue(result.stdout.strip().endswith(os.path.join(".wine", "dosdevices")))


if __name__ == "__main__":
    unittest.main()
