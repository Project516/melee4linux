# SPDX-License-Identifier: GPL-3.0-or-later
"""Check the Linux build driver's patch plan, identity, and patch handling."""

import importlib.util
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


HERE = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("linux_build", HERE / "build.py")
build = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(build)


class PatchPlanTests(unittest.TestCase):
    def test_fork_patches_exist_and_mac_frontend_patches_are_excluded(self):
        runtime = Path("/runtime")
        plan = build.patch_plan(runtime)
        names = [patch.name for _, patch in plan]
        for name in ("apple-input.patch", "app-bundle.patch", "fast-load.patch", "branding.patch",
                     "fluidity-settings.patch", "texture-pack.patch", "source-dol.patch"):
            self.assertNotIn(name, names)
        for _, patch in plan:
            if patch.is_relative_to(runtime):
                continue
            self.assertTrue(patch.is_file(), patch)
        self.assertEqual(names[-3:], ["linux-runtime.patch", "linux-launcher.patch", "vulkan-present.patch"])
        # Upstream patches are applied before any fork patch touches the same trees.
        self.assertEqual(names[0], "strict-native.patch")
        self.assertLess(names.index("media-settings.patch"), names.index("linux-runtime.patch"))
        self.assertLess(names.index("fluid-render.patch"), names.index("vulkan-present.patch"))

    def test_copied_sources_exist_and_avoid_mac_only_files(self):
        sources = [source for source, _ in build.copied_sources(Path("/runtime"))]
        for source in sources:
            self.assertTrue(source.is_file(), source)
        names = [source.name for source in sources]
        self.assertNotIn("MeleeMetalFrameLog.h", names)
        self.assertIn("MeleeLinuxPreferences.cpp", names)


class IdentityTests(unittest.TestCase):
    def test_identity_records_pins_and_changes_with_linux_patches(self):
        with tempfile.TemporaryDirectory() as temporary:
            runtime = Path(temporary)
            (runtime / "patches").mkdir()
            for _, patch in build.patch_plan(runtime):
                if patch.is_relative_to(runtime):
                    patch.write_text(f"upstream {patch.name}\n")
            first = build.build_identity(runtime)
            self.assertIn(f"runtime={build.RUNTIME_REV}", first)
            self.assertIn(f"template={build.TEMPLATE_REV}", first)
            (runtime / "patches/strict-native.patch").write_text("changed\n")
            self.assertNotEqual(first, build.build_identity(runtime))


class PatchRecoveryTests(unittest.TestCase):
    def test_resumes_before_any_dependent_patches_were_applied(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "value.txt"
            source.write_text("one\n")
            patches = []
            for index, (before, after) in enumerate((("one", "two"), ("two", "three"))):
                path = root / f"{index}.patch"
                path.write_text(f"--- a/value.txt\n+++ b/value.txt\n@@ -1 +1 @@\n-{before}\n+{after}\n")
                patches.append(path)
            for path in reversed(patches):
                build.remove_patch(root, path)
            for path in patches:
                build.apply_patch(root, path)
            self.assertEqual(source.read_text(), "three\n")
            for path in reversed(patches):
                build.remove_patch(root, path)
            self.assertEqual(source.read_text(), "one\n")

    def test_preserves_conflicting_local_source(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "value.txt"
            source.write_text("local change\n")
            patch = root / "change.patch"
            patch.write_text("--- a/value.txt\n+++ b/value.txt\n@@ -1 +1 @@\n-original\n+patched\n")
            with self.assertRaisesRegex(RuntimeError, "Local changes conflict"):
                build.apply_patch(root, patch)
            self.assertEqual(source.read_text(), "local change\n")


class CMakeFlagTests(unittest.TestCase):
    def test_static_runtime_and_optional_ccache(self):
        flags = build.cmake_flags(ccache=False)
        self.assertIn("-DCMAKE_EXE_LINKER_FLAGS=-static-libstdc++ -static-libgcc", flags)
        self.assertNotIn("-DCMAKE_CXX_COMPILER_LAUNCHER=ccache", flags)
        self.assertIn("-DCMAKE_CXX_COMPILER_LAUNCHER=ccache", build.cmake_flags(ccache=True))


@unittest.skipUnless(os.environ.get("MELEE_TEST_RUNTIME_DIR"), "Set MELEE_TEST_RUNTIME_DIR to a runtime checkout")
class RealTreePatchTests(unittest.TestCase):
    """The plan must remove and reapply cleanly on the pinned checkouts, as build.py does."""

    def test_plan_removes_and_reapplies_in_order(self):
        runtime = Path(os.environ["MELEE_TEST_RUNTIME_DIR"]).resolve()
        plan = build.patch_plan(runtime)
        for checkout, patch in reversed(plan):
            with self.subTest(step="remove", patch=patch.name):
                build.remove_patch(checkout, patch)
        for checkout, patch in plan:
            with self.subTest(step="apply", patch=patch.name):
                build.apply_patch(checkout, patch)
        for checkout, patch in plan:
            with self.subTest(step="applied", patch=patch.name):
                self.assertTrue(build.patch_state(checkout, patch, reverse=True) or
                                not build.patch_state(checkout, patch), patch.name)


if __name__ == "__main__":
    unittest.main()
