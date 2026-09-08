# SPDX-License-Identifier: GPL-3.0-or-later
"""Verify that repeat builds do not silently use another disc image."""

import importlib.util
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location(
    "macos_build", Path(__file__).resolve().parents[1] / "build.py"
)
build = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build)


class SourceImageTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        (self.root / "private").mkdir()
        self.iso = self.root / "source.iso"
        self.iso.write_bytes(b"first local image")

    def test_accepts_same_content_after_path_change(self):
        checksum = build.check_source_image(self.root, self.iso)
        (self.root / "private/source-image.sha256").write_text(checksum + "\n")
        moved = self.root / "moved.iso"
        self.iso.rename(moved)
        self.assertEqual(build.check_source_image(self.root, moved), checksum)

    def test_rejects_changed_content_at_same_path(self):
        checksum = build.check_source_image(self.root, self.iso)
        (self.root / "private/source-image.sha256").write_text(checksum + "\n")
        self.iso.write_bytes(b"different local image")
        with self.assertRaisesRegex(RuntimeError, "different disc image"):
            build.check_source_image(self.root, self.iso)
        self.assertEqual((self.root / "private/source-image.sha256").read_text(), checksum + "\n")


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


if __name__ == "__main__":
    unittest.main()
