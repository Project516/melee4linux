import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tools import diff_symbols


SPLITS = """# Section declarations include names without a dot.
Sections:
\t.text       type:code align:32
\textab       type:rodata align:32
\textabindex  type:rodata align:32

melee/lb/lbcommand.c:
\t.text       start:0x80005940 end:0x80005BB0
\t.data       start:0x803B9840 end:0x803B9880

data-only.c: comment:0
    .data       start:0x803B9880 end:0x803B9890

melee/lb/lbcollision.c: // A unit can have a comment.
    .text       start:0x80005BB0 end:0x8000AD8C align:4
"""


class DiffSymbolsTests(unittest.TestCase):
    def run_cli(self, baseline, current, *options, stdin=None):
        with tempfile.TemporaryDirectory() as directory:
            baseline_path = Path(directory) / "baseline.txt"
            current_path = Path(directory) / "current.txt"
            baseline_path.write_text(baseline, encoding="utf-8")
            current_path.write_text(current, encoding="utf-8")
            # -S checks that this tool runs without optional site packages.
            return subprocess.run(
                [
                    sys.executable,
                    "-S",
                    str(Path(diff_symbols.__file__).resolve()),
                    "-" if stdin is not None else str(baseline_path),
                    str(current_path),
                    *options,
                ],
                input=stdin,
                capture_output=True,
                text=True,
                check=False,
            )

    def test_split_units_use_text_addresses_and_keep_the_first_name(self):
        content = SPLITS + "alias.c:\n\t.text start:0x80005940 end:0x80005BB0\n"
        self.assertEqual(
            diff_symbols.parse_text_units(content),
            {
                0x80005940: ("melee/lb/lbcommand.c", None),
                0x80005BB0: ("melee/lb/lbcollision.c", None),
            },
        )

    def test_real_splits_report_a_renamed_unit(self):
        root = Path(__file__).resolve().parents[2]
        baseline = (root / "config/GALE01/splits.txt").read_text(encoding="utf-8")
        current = baseline.replace("melee/lb/lbcommand.c:", "melee/lb/commands.c:")
        result = self.run_cli(baseline, current, "--text", "--units")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "melee/lb/lbcommand.c:melee/lb/commands.c\n")
        self.assertEqual(result.stderr, "")

    def test_symbols_include_local_names_and_skip_labels_before_aliases(self):
        content = """// Symbols can use compiler names and undotted sections.
@219 = extab:0x80005520; // type:object size:0x8 scope:local hidden
entry = .text:0x80005940; // type:label scope:global
Command_00 = .text:0x80005940; // type:function size:0xC scope:local
alias = .text:0x80005940; // type:function
"""
        self.assertEqual(
            diff_symbols.parse_text_symbols(content),
            {0x80005520: ("@219", None), 0x80005940: ("Command_00", None)},
        )

    def test_symbol_rename_can_read_the_baseline_from_stdin(self):
        baseline = "@219 = extab:0x80005520; // type:object\n"
        current = baseline.replace("@219", "exception_table")
        result = self.run_cli("", current, "--text", stdin=baseline)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "@219:exception_table\n")

    def test_invalid_text_is_an_error_with_a_filename_and_line_number(self):
        cases = [
            ("not a symbol", "--text"),
            ("not a header", "--text", "--units"),
            ("\t.text start:0x10 end:0x20", "--text", "--units"),
            ("a.c:\n\t.text start:no end:0x20", "--text", "--units"),
            ("a.c:\n\t.text start:0x20 end:0x10", "--text", "--units"),
        ]
        for invalid, *options in cases:
            with self.subTest(invalid=invalid):
                result = self.run_cli("", invalid, *options)
                self.assertEqual(result.returncode, 1)
                self.assertEqual(result.stdout, "")
                self.assertIn("current.txt: line ", result.stderr)

    def test_invalid_json_does_not_look_like_an_empty_comparison(self):
        for content in ["{", "[]", "{}", '{"units": {}}', '{"units": [1]}']:
            with self.subTest(content=content):
                result = self.run_cli(content, '{"units": []}')
                self.assertEqual(result.returncode, 1)
                self.assertEqual(result.stdout, "")
                self.assertIn("Error parsing", result.stderr)
                self.assertIn("baseline.txt:", result.stderr)

    def test_valid_inputs_without_name_changes_succeed_with_no_output(self):
        for content, options in [
            ("", ["--text"]),
            (SPLITS, ["--text", "--units"]),
            ('{"units": []}', []),
        ]:
            with self.subTest(options=options):
                result = self.run_cli(content, content, *options)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout, "")
                self.assertEqual(result.stderr, "")

    def test_json_units_use_text_section_addresses_and_unit_percentages(self):
        content = json.dumps(
            {
                "units": [
                    {
                        "name": "main/melee/lb/lbcommand",
                        "measures": {"fuzzy_match_percent": 75.5},
                        "sections": [
                            {"name": ".data", "metadata": {"virtual_address": "4096"}},
                            {"name": ".text", "metadata": {"virtual_address": "8192"}},
                        ],
                    },
                    {"name": "data_only", "sections": []},
                ]
            }
        )
        self.assertEqual(
            diff_symbols.parse_json_units(content),
            {8192: ("main/melee/lb/lbcommand", 75.5)},
        )

    def test_percent_filters_compare_changed_added_and_removed_functions(self):
        def report(functions):
            return json.dumps(
                {
                    "units": [
                        {
                            "functions": [
                                {
                                    "name": name,
                                    "metadata": {"virtual_address": str(address)},
                                    "fuzzy_match_percent": percent,
                                }
                                for address, name, percent in functions
                            ]
                        }
                    ]
                }
            )

        baseline = report([(16, "same", 100), (32, "changed", 50), (48, "removed", 90)])
        current = report([(16, "same", 100), (32, "changed", 75), (64, "added", 25)])
        for operator, names in [
            ("eq", ["same"]),
            ("ne", ["changed", "removed", "added"]),
            ("lt", ["removed"]),
            ("gt", ["changed", "added"]),
        ]:
            with self.subTest(operator=operator):
                result = self.run_cli(baseline, current, "--percent", operator)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(
                    [line.split("|")[0].strip() for line in result.stdout.splitlines()],
                    names,
                )
                if operator == "gt":
                    self.assertIn("50.00 -> 75.00", result.stdout)


if __name__ == "__main__":
    unittest.main()
