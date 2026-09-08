import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools import changes_fmt


# Shape emitted by objdiff-cli report changes, including added/removed functions.
CHANGES = {
    "from": {"fuzzy_match_percent": 90.0},
    "to": {"fuzzy_match_percent": 80.0},
    "units": [
        {
            "name": "unit",
            "from": {"fuzzy_match_percent": 90.0},
            "to": {"fuzzy_match_percent": 80.0},
            "functions": [
                {
                    "name": "regression",
                    "from": {"fuzzy_match_percent": 100.0},
                    "to": {"fuzzy_match_percent": 50.0},
                },
                {
                    "name": "progression",
                    "from": {"fuzzy_match_percent": 50.0},
                    "to": {"fuzzy_match_percent": 100.0},
                },
                {"name": "removed", "from": {"fuzzy_match_percent": 100.0}},
                {"name": "added", "to": {"fuzzy_match_percent": 100.0}},
            ],
        },
    ],
}


class ChangesFormatterTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.input = self.directory / "changes.json"
        self.input.write_text(json.dumps(CHANGES), encoding="utf-8")

    def run_cli(self, source, *options):
        return subprocess.run(
            [sys.executable, str(Path(changes_fmt.__file__).resolve()), str(source), *options],
            cwd=self.directory, capture_output=True, text=True, check=False,
        )

    def test_relative_and_absolute_inputs_work_outside_the_checkout(self):
        for source in ("changes.json", self.input):
            with self.subTest(source=source):
                result = self.run_cli(source)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("regression | fuzzy_match", result.stdout)
                self.assertIn("removed | fuzzy_match", result.stdout)
                self.assertNotIn("progression", result.stdout)
                self.assertEqual(result.stderr, "")

    def test_input_does_not_require_a_relative_path_between_drives(self):
        # Windows cannot compute a relative path between the checkout and a
        # report on another drive. Reading the supplied path does not need one.
        with patch("os.path.relpath", side_effect=ValueError("different drives")):
            regressions, progressions = changes_fmt.get_changes(self.input)
        self.assertEqual(regressions, [
            (None, "fuzzy_match", 90.0, 80.0),
            ("unit", "fuzzy_match", 90.0, 80.0),
            ("regression", "fuzzy_match", 100.0, 50.0),
            ("removed", "fuzzy_match", 100.0, 0.0),
        ])
        self.assertEqual(progressions, [
            ("progression", "fuzzy_match", 50.0, 100.0),
            ("added", "fuzzy_match", 0.0, 100.0),
        ])

    def test_markdown_sections_have_a_blank_line_between_details_blocks(self):
        result = self.run_cli("changes.json", "--all", "-o", "changes.md")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "")
        markdown = (self.directory / "changes.md").read_text(encoding="utf-8")
        self.assertEqual(markdown.count("<details>"), 2)
        self.assertIn("Detected 4 regressions", markdown)
        self.assertIn("Detected 2 progressions", markdown)
        self.assertIn("</details>\n\n<details>", markdown)
        self.assertIn("| `removed` | Fuzzy match | 100.00% |   0.00% |", markdown)
        self.assertIn("| `added` | Fuzzy match |   0.00% | 100.00% |", markdown)

    def test_empty_sections_do_not_add_blank_output(self):
        for change in (
            {},
            {"from": {"fuzzy_match_percent": 100.0}},
            {"to": {"fuzzy_match_percent": 100.0}},
        ):
            with self.subTest(change=change):
                self.input.write_text(json.dumps(change), encoding="utf-8")
                result = self.run_cli("changes.json", "--all", "-o", "changes.md")
                self.assertEqual(result.returncode, 0, result.stderr)
                markdown = (self.directory / "changes.md").read_text(encoding="utf-8")
                self.assertEqual(markdown, markdown.strip())
                self.assertEqual(markdown.count("<details>"), bool(change))

    def test_plaintext_all_keeps_progressions_before_regressions(self):
        result = self.run_cli("changes.json", "--all")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertLess(result.stdout.index("progression"), result.stdout.index("regression"))


if __name__ == "__main__":
    unittest.main()
