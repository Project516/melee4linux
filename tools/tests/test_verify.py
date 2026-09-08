"""Run with python3 -m unittest discover -s tools/tests."""

import hashlib
import io
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import call, patch

from tools.verify import main, verify


class VerifyTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.dol = self.root / "build/GALE01/main.dol"
        self.report = self.dol.with_name("report.json")
        self.manifest = self.root / "config/GALE01/build.sha1"
        self.dol.parent.mkdir(parents=True)
        self.manifest.parent.mkdir(parents=True)
        self.dol.write_bytes(b"original game executable")
        self.measures = {
            "fuzzy_match_percent": 99.999954,
            "total_code": "32",
            "matched_code": "32",
            "complete_code": "32",
            "total_data": "16",
            "matched_data": "16",
            "complete_data": "16",
            "total_functions": 2,
            "matched_functions": 2,
            "total_units": 1,
            "complete_units": 1,
        }
        self.report_data = {
            "measures": self.measures,
            "units": [{"metadata": {"complete": True}}],
        }
        self.report.write_text(json.dumps(self.report_data))
        self.expected = hashlib.sha1(self.dol.read_bytes()).hexdigest()
        self.manifest.write_text(f"{self.expected}  build/GALE01/main.dol")
        (self.root / "build.ninja").touch()
        self.run = self.enterContext(patch("tools.verify.subprocess.run"))
        self.stdout = self.enterContext(patch("sys.stdout", new_callable=io.StringIO))

    def test_builds_executable_and_report_before_diff(self):
        verify(self.root, "GALE01", "/custom path/ninja")

        self.assertEqual(
            self.run.call_args_list,
            [
                call(
                    [
                        "/custom path/ninja",
                        "build/GALE01/main.dol",
                        "build/GALE01/report.json",
                    ],
                    cwd=self.root,
                    check=True,
                ),
                call(["/custom path/ninja", "diff"], cwd=self.root, check=True),
            ],
        )
        self.assertIn(f"SHA-1 {self.expected}", self.stdout.getvalue())

    def test_build_failure_stops_before_diff_even_with_old_artifacts(self):
        self.run.side_effect = subprocess.CalledProcessError(2, "ninja")

        with self.assertRaises(subprocess.CalledProcessError):
            verify(self.root, "GALE01", "ninja")

        self.assertEqual(self.run.call_count, 1)
        self.assertEqual(self.stdout.getvalue(), "")

    def test_diff_failure_does_not_pass_with_matching_hash(self):
        self.run.side_effect = [None, subprocess.CalledProcessError(1, "ninja diff")]

        with self.assertRaises(subprocess.CalledProcessError):
            verify(self.root, "GALE01", "ninja")

        self.assertEqual(self.stdout.getvalue(), "")

    def test_perfect_progress_does_not_hide_hash_mismatch(self):
        self.dol.write_bytes(b"different executable")
        self.measures["fuzzy_match_percent"] = 100
        self.report.write_text(json.dumps(self.report_data))

        with self.assertRaisesRegex(ValueError, "SHA-1 mismatch"):
            verify(self.root, "GALE01", "ninja")

        self.assertEqual(self.stdout.getvalue(), "")

    def test_original_object_fallback_does_not_hide_incomplete_source(self):
        for key in ("complete_code", "complete_data", "complete_units"):
            with self.subTest(key=key):
                original = self.measures[key]
                self.measures[key] = 0
                self.report.write_text(json.dumps(self.report_data))
                with self.assertRaisesRegex(ValueError, key):
                    verify(self.root, "GALE01", "ninja")
                self.measures[key] = original

        self.assertEqual(self.stdout.getvalue(), "")

    def test_matching_executable_does_not_hide_source_mismatch(self):
        for key in ("matched_code", "matched_data", "matched_functions"):
            with self.subTest(key=key):
                original = self.measures[key]
                self.measures[key] = int(original) - 1
                self.report.write_text(json.dumps(self.report_data))
                with self.assertRaisesRegex(ValueError, key):
                    verify(self.root, "GALE01", "ninja")
                self.measures[key] = original

        self.assertEqual(self.stdout.getvalue(), "")

    def test_invalid_report_fails_with_matching_executable(self):
        for content in ("", "{", "null", "[]", "{}", '{"measures": {}}'):
            with self.subTest(content=content):
                self.report.write_text(content)
                with self.assertRaises(ValueError):
                    verify(self.root, "GALE01", "ninja")

        self.assertEqual(self.stdout.getvalue(), "")

    def test_invalid_counts_are_not_coerced_to_valid_totals(self):
        for invalid in (True, -1, 1.5, "1.5", "", None):
            with self.subTest(invalid=invalid):
                self.measures["complete_units"] = invalid
                self.report.write_text(json.dumps(self.report_data))
                with self.assertRaisesRegex(ValueError, "nonnegative integer"):
                    verify(self.root, "GALE01", "ninja")

    def test_empty_totals_do_not_pass(self):
        for key in self.measures:
            self.measures[key] = 0
        self.report_data["units"] = []
        self.report.write_text(json.dumps(self.report_data))

        with self.assertRaisesRegex(ValueError, "greater than zero"):
            verify(self.root, "GALE01", "ninja")

    def test_invalid_or_incomplete_units_do_not_pass(self):
        for units in (None, [], [None], [{}], [{"metadata": {"complete": False}}]):
            with self.subTest(units=units):
                self.report_data["units"] = units
                self.report.write_text(json.dumps(self.report_data))
                with self.assertRaises(ValueError):
                    verify(self.root, "GALE01", "ninja")

    def test_missing_artifacts_fail_even_when_ninja_succeeds(self):
        for artifact in (self.dol, self.report):
            with self.subTest(artifact=artifact.name):
                contents = artifact.read_bytes()
                artifact.unlink()
                with self.assertRaisesRegex(ValueError, "artifact is missing"):
                    verify(self.root, "GALE01", "ninja")
                artifact.write_bytes(contents)

        self.assertEqual(self.stdout.getvalue(), "")

    def test_missing_configuration_does_not_run_ninja_or_configure(self):
        (self.root / "build.ninja").unlink()

        with self.assertRaisesRegex(ValueError, "Run configure.py"):
            verify(self.root, "GALE01", "ninja")

        self.run.assert_not_called()

    def test_invalid_manifest_stops_before_build(self):
        for content in (
            "",
            "invalid  build/GALE01/main.dol",
            f"{self.expected}  build/GALE01/other.dol",
            f"{self.expected}  build/GALE01/main.dol\n" * 2,
        ):
            with self.subTest(content=content):
                self.manifest.write_text(content)
                with self.assertRaisesRegex(ValueError, "one valid SHA-1"):
                    verify(self.root, "GALE01", "ninja")

        self.run.assert_not_called()

    def test_cli_returns_failure_without_traceback(self):
        errors = (
            subprocess.CalledProcessError(2, "ninja"),
            FileNotFoundError("ninja is missing"),
            ValueError("SHA-1 mismatch"),
        )
        for error in errors:
            with self.subTest(error=error):
                with (
                    patch("tools.verify.verify", side_effect=error),
                    patch("sys.argv", ["verify.py"]),
                    patch("sys.stderr", new_callable=io.StringIO) as stderr,
                ):
                    self.assertEqual(main(), 1)
                    self.assertIn("Verification failed:", stderr.getvalue())

    def test_cli_uses_script_root_and_selected_ninja(self):
        with (
            patch("tools.verify.__file__", str(self.root / "tools/verify.py")),
            patch("tools.verify.verify") as verify_build,
            patch(
                "sys.argv",
                ["verify.py", "--version", "gale01", "--ninja", "/custom/ninja"],
            ),
        ):
            self.assertEqual(main(), 0)

        verify_build.assert_called_once_with(
            self.root.resolve(), "GALE01", "/custom/ninja"
        )


if __name__ == "__main__":
    unittest.main()
