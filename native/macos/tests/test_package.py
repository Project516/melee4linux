"""Check package failures and run a moved native dependency graph on macOS."""

import importlib.util
from pathlib import Path
import platform
import plistlib
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


SPEC = importlib.util.spec_from_file_location("melee_package", Path(__file__).parents[1] / "package.py")
package = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = package
SPEC.loader.exec_module(package)


class PackageTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="melee-package-test-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def make_input(self):
        for name in (
            "build/runtime/moderngekko-run", "build/game/gGALE01_recomp.dylib",
            "private/GALE01r2/sys/main.dol", "private/GALE01r2/files/asset.dat",
            "build/runtime/Sys/test.ini", "config/GCPadNew.ini", "LICENSE", "CREDITS.md",
        ):
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"test input")

    def test_missing_runtime_stops_before_packaging(self):
        with self.assertRaisesRegex(package.PackageError, "moderngekko-run"):
            package.validate_inputs(self.root)

    def test_wrong_game_revision_is_rejected(self):
        self.make_input()
        with self.assertRaisesRegex(package.PackageError, "USA revision 2"):
            package.validate_inputs(self.root)

    def test_empty_assets_are_rejected(self):
        self.make_input()
        (self.root / "private/GALE01r2/files/asset.dat").unlink()
        with self.assertRaisesRegex(package.PackageError, "resource directory"):
            package.validate_inputs(self.root)

    def test_replace_rejects_an_unrelated_app(self):
        app = self.root / "Other.app"
        (app / "Contents").mkdir(parents=True)
        (app / "Contents/Info.plist").write_bytes(plistlib.dumps({"CFBundleIdentifier": "other.app"}))
        with self.assertRaisesRegex(package.PackageError, "different bundle identifier"):
            package.validate_output(app, replace=True)

    def test_replace_rejects_a_symlink(self):
        app = self.root / "Melee.app"
        app.symlink_to(self.root, target_is_directory=True)
        with self.assertRaisesRegex(package.PackageError, "symbolic link"):
            package.validate_output(app, replace=True)

    def test_build_failure_preserves_existing_app(self):
        app = self.root / "Melee.app"
        (app / "Contents").mkdir(parents=True)
        (app / "Contents/Info.plist").write_bytes(plistlib.dumps({"CFBundleIdentifier": package.APP_ID}))
        marker = app / "existing.txt"
        marker.write_text("keep this app")
        with patch.object(package, "validate_inputs"), \
                patch.object(package.platform, "system", return_value="Darwin"), \
                patch.object(package.platform, "machine", return_value="arm64"), \
                patch.object(package, "assemble", side_effect=package.PackageError("bad dylib")):
            with self.assertRaisesRegex(package.PackageError, "bad dylib"):
                package.package(self.root, app, replace=True)
        self.assertEqual(marker.read_text(), "keep this app")
        self.assertEqual(list(self.root.glob(".melee-package-*")), [])

    def test_rpath_uses_loader_and_preserves_spaces(self):
        loader = self.root / "build/runtime/run"
        loader.parent.mkdir(parents=True)
        dependency = self.root / "build/shared libs/libdep.dylib"
        dependency.parent.mkdir(parents=True)
        dependency.touch()
        rpath = package.expand_path("@loader_path/../shared libs", loader, loader)
        self.assertEqual(
            package.resolve_dependency("@rpath/libdep.dylib", loader, loader, (rpath,)),
            dependency.resolve(),
        )

    def test_missing_transitive_dependency_is_an_error(self):
        with self.assertRaisesRegex(package.PackageError, "libmissing.dylib"):
            package.resolve_dependency(
                "@rpath/libmissing.dylib", self.root / "loader",
                self.root / "runner", (self.root,),
            )

    def test_parse_distinguishes_library_identity_and_dependency(self):
        info = package.parse_load_commands(
            "some library:\n"
            "Load command 1\n"
            "          cmd LC_ID_DYLIB\n"
            "      cmdsize 64\n"
            "         name @rpath/libself.dylib (offset 24)\n"
            "Load command 2\n"
            "          cmd LC_LOAD_WEAK_DYLIB\n"
            "      cmdsize 72\n"
            "         name /build path/libother.dylib (offset 24)\n"
            "Load command 3\n"
            "          cmd LC_RPATH\n"
            "      cmdsize 48\n"
            "         path @loader_path/../lib (offset 12)\n"
        )
        self.assertEqual(info.install_id, "@rpath/libself.dylib")
        self.assertEqual(info.dependencies, ("/build path/libother.dylib",))
        self.assertEqual(info.rpaths, ("@loader_path/../lib",))

    def test_parse_uses_deployment_version_instead_of_sdk_or_tool_version(self):
        info = package.parse_load_commands(
            "library:\n"
            "Load command 1\n"
            "      cmd LC_BUILD_VERSION\n"
            " platform 1\n"
            "    minos 26.0.0\n"
            "      sdk 26.5\n"
            "   ntools 1\n"
            "     tool 3\n"
            "  version 1267.0\n"
        )
        self.assertEqual(info.minimum_macos, (26, 0, 0))

    def test_parse_legacy_macos_version(self):
        info = package.parse_load_commands(
            "library:\n"
            "Load command 1\n"
            "      cmd LC_VERSION_MIN_MACOSX\n"
            "  cmdsize 16\n"
            "  version 10.14.6\n"
            "      sdk 11.0\n"
        )
        self.assertEqual(info.minimum_macos, (10, 14, 6))

    def test_minimum_version_includes_newer_library_and_compares_numbers(self):
        runtime = self.root / "runtime"
        library = self.root / "libdependency.dylib"
        outputs = {
            runtime: "Load command 1\n cmd LC_BUILD_VERSION\n platform 1\n minos 14.9\n",
            library: "Load command 1\n cmd LC_BUILD_VERSION\n platform macos\n minos 14.10.2\n",
        }
        with patch.object(package, "run", side_effect=lambda *args: outputs[args[-1]]) as command:
            self.assertEqual(package.minimum_system_version([runtime, library]), "14.10.2")
            self.assertEqual(command.call_count, 2)

    def test_minimum_version_keeps_launcher_floor(self):
        commands = "Load command 1\n cmd LC_VERSION_MIN_MACOSX\n version 10.15\n sdk 26.5\n"
        with patch.object(package, "run", return_value=commands):
            self.assertEqual(package.minimum_system_version([self.root / "legacy.dylib"]), "14.0")

    def test_unknown_binary_requirement_is_an_error(self):
        with patch.object(package, "run", return_value="no deployment command"):
            with self.assertRaisesRegex(package.PackageError, "No minimum macOS version"):
                package.minimum_system_version([self.root / "unknown.dylib"])

    @unittest.skipUnless(platform.system() == "Darwin" and shutil.which("xcrun"), "Needs Apple tools")
    def test_recursive_libraries_run_after_sources_are_removed_and_bundle_moves(self):
        source = self.root / "original build"
        source.mkdir()
        (source / "inner.c").write_text("int inner(void) { return 40; }\n")
        (source / "outer.c").write_text("extern int inner(void); int outer(void) { return inner() + 2; }\n")
        (source / "main.c").write_text("extern int outer(void); int main(void) { return outer() == 42 ? 0 : 1; }\n")
        inner = source / "libinner.dylib"
        outer = source / "libouter.dylib"
        runner = source / "runner"
        package.run("xcrun", "clang", "-dynamiclib", source / "inner.c", "-o", inner,
                    "-Wl,-install_name," + str(inner), "-Wl,-headerpad_max_install_names")
        package.run("xcrun", "clang", "-dynamiclib", source / "outer.c", inner, "-o", outer,
                    "-Wl,-install_name,@rpath/libouter.dylib", "-Wl,-headerpad_max_install_names")
        package.run("xcrun", "clang", source / "main.c", outer, "-o", runner,
                    "-Wl,-rpath," + str(source), "-Wl,-headerpad_max_install_names")
        app = self.root / "Staged.app"
        macos = app / "Contents/MacOS"
        frameworks = app / "Contents/Frameworks"
        macos.mkdir(parents=True)
        frameworks.mkdir()
        bundled_runner = macos / "runner"
        shutil.copy2(runner, bundled_runner)
        binaries = package.bundle_libraries([(runner, bundled_runner)], frameworks)
        self.assertEqual(len(binaries), 3)
        for binary in binaries:
            package.run("codesign", "--force", "--sign", "-", binary)
        shutil.rmtree(source)
        moved = self.root / "Moved app with spaces.app"
        app.rename(moved)
        result = subprocess.run([moved / "Contents/MacOS/runner"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
