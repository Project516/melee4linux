import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools import find_include


class FindIncludeTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.source = self.root / "src"
        self.source.mkdir()
        self.enterContext(
            patch.object(find_include, "__file__", str(self.root / "tools/find_include.py"))
        )
        self.stdout = self.enterContext(contextlib.redirect_stdout(io.StringIO()))
        self.stderr = self.enterContext(contextlib.redirect_stderr(io.StringIO()))

    def run_cli(self, symbol):
        with patch("sys.argv", ["find_include.py", symbol]):
            return find_include.main()

    def test_all_headers_are_listed_in_path_order_with_whole_word_matches(self):
        # Create the use before the declaration, as happens in a real checkout.
        (self.source / "z_use.h").write_text("void update(Fighter* fighter);")
        (self.source / "a_type.h").write_text("typedef struct Fighter Fighter;")
        (self.source / "partial.h").write_text("struct FighterData;")
        (self.source / "source.c").write_text("struct Fighter {};")

        self.assertEqual(self.run_cli("Fighter"), 0)
        self.assertEqual(
            self.stdout.getvalue(),
            '#include "a_type.h"\n#include "z_use.h"\n',
        )
        self.assertEqual(self.stderr.getvalue(), "")

    def test_missing_symbol_fails_without_printing_an_include(self):
        self.assertEqual(self.run_cli("MissingSymbol"), 1)
        self.assertEqual(self.stdout.getvalue(), "")
        self.assertIn("No header contains 'MissingSymbol'.", self.stderr.getvalue())

    def test_nested_header_paths_use_include_syntax(self):
        (self.source / "melee/ft").mkdir(parents=True)
        (self.source / "melee/ft/fighter.h").write_text("void Fighter_Update(void);")

        self.assertEqual(self.run_cli("Fighter_Update"), 0)
        self.assertEqual(self.stdout.getvalue(), '#include "melee/ft/fighter.h"\n')


if __name__ == "__main__":
    unittest.main()
