import contextlib
import io
import unittest
from unittest.mock import patch

from tools import dep_graph
from tools.dep_graph import ObjectFile, find_leaves, find_unlock_chain


class DependencyPlanningTests(unittest.TestCase):
    def test_matching_flag_adds_candidates_and_counts_their_references(self):
        objects = {
            "library.c": ObjectFile("library.c", "NonMatching"),
            "caller.c": ObjectFile("caller.c", "Matching"),
            "unused.c": ObjectFile("unused.c", "Matching"),
        }
        rdeps = {"library.c": {"caller.c"}}
        self.assertEqual(find_leaves(objects, rdeps), [("library.c", 0)])
        self.assertEqual(
            find_leaves(objects, rdeps, include_matching=True),
            [("caller.c", 0), ("unused.c", 0)],
        )

    def test_leaf_order_uses_reference_counts_then_paths(self):
        objects = {
            name: ObjectFile(name, "NonMatching")
            for name in ("b.c", "c.c", "a.c")
        }
        objects["c.c"].undefined_symbols = {"one", "two"}
        self.assertEqual(find_leaves(objects, {}), [("a.c", 0), ("b.c", 0), ("c.c", 2)])

    def test_conversion_unlocks_the_files_used_by_the_converted_caller(self):
        objects = {
            name: ObjectFile(name, "NonMatching")
            for name in ("app.c", "library.c", "storage.c")
        }
        rdeps = {"library.c": {"app.c"}, "storage.c": {"library.c"}}
        self.assertEqual(
            find_unlock_chain(objects, rdeps),
            [("app.c", ["library.c"]), ("library.c", ["storage.c"])],
        )

    def test_shared_dependency_stays_blocked_after_one_conversion(self):
        objects = {
            name: ObjectFile(name, "NonMatching")
            for name in ("first.c", "second.c", "shared.c")
        }
        self.assertEqual(
            find_unlock_chain(objects, {"shared.c": {"first.c", "second.c"}}), []
        )

    def test_predictions_agree_with_leaves_after_each_conversion(self):
        objects = {
            name: ObjectFile(name, "NonMatching")
            for name in ("z.c", "a.c", "b.c", "c.c", "d.c")
        }
        # Include a cycle, a shared dependency, and an already unblocked file.
        rdeps = {"a.c": {"b.c"}, "b.c": {"a.c"}, "c.c": {"a.c", "d.c"}}
        before = {name for name, _ in find_leaves(objects, rdeps)}
        predictions = dict(find_unlock_chain(objects, rdeps))
        for converted in objects:
            with self.subTest(converted=converted):
                objects[converted].status = "Matching"
                after = {name for name, _ in find_leaves(objects, rdeps)}
                self.assertEqual(set(predictions.get(converted, [])), after - before)
                objects[converted].status = "NonMatching"
        self.assertEqual(list(predictions), ["a.c", "b.c"])
        self.assertEqual(
            find_unlock_chain(dict(reversed(list(objects.items()))), rdeps),
            list(predictions.items()),
        )

    def test_matching_cli_reports_matching_leaves(self):
        objects = {"leaf.c": ObjectFile("leaf.c", "Matching")}
        output = io.StringIO()
        with (
            patch("sys.argv", ["dep_graph.py", "--matching"]),
            patch.object(dep_graph, "find_nm_tool", return_value="nm"),
            patch.object(dep_graph, "parse_configure", return_value=objects),
            patch.object(dep_graph, "load_report", return_value={}),
            patch.object(dep_graph, "build_dependency_graph", return_value=({}, {})),
            contextlib.redirect_stdout(output),
        ):
            self.assertEqual(dep_graph.main(), 0)
        self.assertIn("leaf.c (Matching)", output.getvalue())
        self.assertIn("No other Matching or NonMatching file", output.getvalue())


if __name__ == "__main__":
    unittest.main()
