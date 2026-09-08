import contextlib
import io
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools import dep_graph


class DependencyGraphTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.build = self.root / "build/GALE01"
        self.build.mkdir(parents=True)
        self.enterContext(patch.object(dep_graph, "ROOT", self.root))
        self.enterContext(patch.object(dep_graph, "BUILD_DIR", self.build))
        self.enterContext(patch.object(dep_graph, "REPORT_PATH", self.build / "report.json"))
        self.stdout = self.enterContext(contextlib.redirect_stdout(io.StringIO()))
        self.stderr = self.enterContext(contextlib.redirect_stderr(io.StringIO()))

    def write_units(self, *names):
        (self.build / "config.json").write_text(
            json.dumps({"units": [{"name": name} for name in names]})
        )

    def write_object(self, name):
        path = dep_graph.get_object_path(name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()
        return path

    def test_bundled_tool_takes_priority_over_host_tools(self):
        for platform, executable in (
            ("darwin", "powerpc-eabi-nm"),
            ("win32", "powerpc-eabi-nm.exe"),
        ):
            with self.subTest(platform=platform):
                tool = self.root / "build/binutils" / executable
                tool.parent.mkdir(parents=True, exist_ok=True)
                tool.touch()
                with (
                    patch.object(dep_graph.sys, "platform", platform),
                    patch.object(dep_graph.shutil, "which", return_value="host-nm"),
                ):
                    self.assertEqual(dep_graph.find_nm_tool(), str(tool))

    def test_llvm_is_used_before_generic_host_nm(self):
        installed = {"llvm-nm": "/tools/llvm-nm", "nm": "/usr/bin/nm"}
        with (
            patch.object(dep_graph.shutil, "which", side_effect=installed.get),
            patch.object(Path, "exists", return_value=False),
        ):
            self.assertEqual(dep_graph.find_nm_tool(), "/tools/llvm-nm")

    def test_only_units_in_the_build_are_analyzed(self):
        self.write_units("present.c")
        (self.root / "configure.py").write_text(
            'Object(Matching, "present.c"),\n'
            'Object(Matching, "unused.c"),\n'
        )
        self.assertEqual(set(dep_graph.parse_configure()), {"present.c"})

    def test_unknown_build_unit_is_an_error(self):
        self.write_units("unknown.c")
        (self.root / "configure.py").write_text("")
        with self.assertRaisesRegex(RuntimeError, "unknown.c"):
            dep_graph.parse_configure()

    def test_static_names_do_not_replace_global_providers(self):
        objects = {
            name: dep_graph.ObjectFile(name, "Matching")
            for name in ("provider.c", "local.c", "caller.c")
        }
        output = {
            self.write_object("provider.c"): "shared T 0 4\n",
            self.write_object("local.c"): "shared t 0 4\nstate d 0 4\ncache b 0 4\n",
            self.write_object("caller.c"): "shared U\n",
        }

        def run_nm(command, **kwargs):
            self.assertIn("-g", command)
            return subprocess.CompletedProcess(command, 0, output[Path(command[-1])])

        with patch.object(dep_graph.subprocess, "run", side_effect=run_nm):
            deps, rdeps = dep_graph.build_dependency_graph(objects, "nm")

        self.assertEqual(deps["caller.c"], {"provider.c"})
        self.assertEqual(rdeps["provider.c"], {"caller.c"})
        self.assertEqual(objects["local.c"].defined_symbols, {})

    def test_weak_definitions_and_undefined_references_are_distinct(self):
        path = self.write_object("weak.c")
        output = (
            "weak_function W 0 4\nweak_data V 4 4\n"
            "optional_function w\noptional_data v\nrequired U\n"
            "small_data G 8 4\nabsolute A 10 0\nunique u c 4\n"
        )
        with patch.object(
            dep_graph.subprocess,
            "run",
            return_value=subprocess.CompletedProcess([], 0, output),
        ):
            defined, undefined = dep_graph.analyze_symbols("nm", path)
        self.assertEqual(
            set(defined), {"weak_function", "weak_data", "small_data", "absolute", "unique"}
        )
        self.assertEqual(undefined, {"optional_function", "optional_data", "required"})

    def test_strong_provider_wins_in_both_input_orders(self):
        output = {
            self.write_object("strong.c"): "exit T 0 4\n",
            self.write_object("weak.c"): "exit W 0 4\n",
            self.write_object("caller.c"): "exit U\n",
        }

        def run_nm(command, **kwargs):
            return subprocess.CompletedProcess(command, 0, output[Path(command[-1])])

        for names in (
            ("strong.c", "weak.c", "caller.c"),
            ("weak.c", "strong.c", "caller.c"),
        ):
            with self.subTest(names=names):
                objects = {
                    name: dep_graph.ObjectFile(name, "Matching") for name in names
                }
                with patch.object(dep_graph.subprocess, "run", side_effect=run_nm):
                    deps, rdeps = dep_graph.build_dependency_graph(objects, "nm")
                self.assertEqual(deps["caller.c"], {"strong.c"})
                self.assertEqual(rdeps["strong.c"], {"caller.c"})
                self.assertNotIn("caller.c", rdeps.get("weak.c", set()))

    def test_multiple_weak_definitions_remain_possible_providers(self):
        output = {
            self.write_object("first.c"): "shared W 0 4\n",
            self.write_object("second.c"): "shared W 0 4\n",
            self.write_object("caller.c"): "shared U\n",
        }
        objects = {
            name: dep_graph.ObjectFile(name, "Matching")
            for name in ("first.c", "second.c", "caller.c")
        }

        def run_nm(command, **kwargs):
            return subprocess.CompletedProcess(command, 0, output[Path(command[-1])])

        with patch.object(dep_graph.subprocess, "run", side_effect=run_nm):
            deps, _ = dep_graph.build_dependency_graph(objects, "nm")
        self.assertEqual(deps["caller.c"], {"first.c", "second.c"})

    def test_nm_failure_reports_the_object_and_stderr(self):
        path = self.write_object("bad.c")
        failure = subprocess.CalledProcessError(
            1, ["nm"], stderr="file format not recognized\n"
        )
        with patch.object(dep_graph.subprocess, "run", side_effect=failure):
            with self.assertRaises(RuntimeError) as caught:
                dep_graph.analyze_symbols("nm", path)
        self.assertIn(str(path), str(caught.exception))
        self.assertIn("file format not recognized", str(caught.exception))

    def test_unavailable_nm_is_an_error(self):
        path = self.write_object("present.c")
        with patch.object(
            dep_graph.subprocess, "run", side_effect=FileNotFoundError("missing nm")
        ):
            with self.assertRaisesRegex(RuntimeError, "Cannot run custom-nm"):
                dep_graph.analyze_symbols("custom-nm", path)

    def test_missing_object_stops_cli_before_printing_results(self):
        self.write_units("missing.c")
        (self.root / "configure.py").write_text('Object(NonMatching, "missing.c")')
        with (
            patch.object(dep_graph.sys, "argv", ["dep_graph.py"]),
            patch.object(dep_graph, "find_nm_tool", return_value="nm"),
        ):
            self.assertEqual(dep_graph.main(), 1)
        self.assertEqual(self.stdout.getvalue(), "")
        self.assertIn("missing.o", self.stderr.getvalue())
        self.assertIn("ninja all_source", self.stderr.getvalue())

    def test_unknown_dependency_path_fails_before_analysis(self):
        self.write_units("present.c")
        (self.root / "configure.py").write_text('Object(Matching, "present.c")')
        for option in ("--deps", "--rdeps"):
            with self.subTest(option=option):
                with (
                    patch.object(dep_graph.sys, "argv", ["dep_graph.py", option, "unknown.c"]),
                    patch.object(dep_graph, "find_nm_tool", return_value="nm"),
                    patch.object(dep_graph, "build_dependency_graph") as analyze,
                ):
                    self.assertEqual(dep_graph.main(), 1)
                analyze.assert_not_called()
        self.assertEqual(self.stdout.getvalue(), "")
        self.assertIn("unknown.c is not a build unit", self.stderr.getvalue())
        self.assertIn("without src/", self.stderr.getvalue())

    def test_missing_build_configuration_has_setup_instructions(self):
        with (
            patch.object(dep_graph.sys, "argv", ["dep_graph.py"]),
            patch.object(dep_graph, "find_nm_tool", return_value="nm"),
        ):
            self.assertEqual(dep_graph.main(), 1)
        self.assertEqual(self.stdout.getvalue(), "")
        self.assertIn("Run configure.py and ninja all_source", self.stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
