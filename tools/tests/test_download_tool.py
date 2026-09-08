import contextlib
import io
import stat
import tempfile
import unittest
import urllib.error
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from tools import download_tool


class DownloadToolTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.output = self.root / "nested/tool"
        self.stdout = self.enterContext(contextlib.redirect_stdout(io.StringIO()))
        self.stderr = self.enterContext(contextlib.redirect_stderr(io.StringIO()))
        self.enterContext(
            patch(
                "sys.argv",
                ["download_tool.py", "sjiswrap", str(self.output), "--tag", "v1.2.2"],
            )
        )

    def test_success_creates_an_executable_and_reports_success(self):
        with patch("tools.download_tool.urllib.request.urlopen", return_value=io.BytesIO(b"tool")):
            self.assertEqual(download_tool.main(), 0)
        self.assertEqual(self.output.read_bytes(), b"tool")
        self.assertTrue(self.output.stat().st_mode & stat.S_IXUSR)
        self.assertEqual(list(self.output.parent.iterdir()), [self.output])

    def test_interrupted_download_preserves_the_existing_tool(self):
        self.output.parent.mkdir()
        self.output.write_bytes(b"working tool")

        def interrupted_copy(response, destination):
            destination.write(b"partial replacement")
            raise OSError("connection interrupted")

        with patch("tools.download_tool.shutil.copyfileobj", side_effect=interrupted_copy):
            with self.assertRaisesRegex(OSError, "connection interrupted"):
                download_tool.download("https://example.test/tool", io.BytesIO(), self.output)

        self.assertEqual(self.output.read_bytes(), b"working tool")
        self.assertEqual(list(self.output.parent.iterdir()), [self.output])

    def test_completed_download_replaces_the_existing_tool(self):
        self.output.parent.mkdir()
        self.output.write_bytes(b"old tool")

        download_tool.download("https://example.test/tool", io.BytesIO(b"new tool"), self.output)

        self.assertEqual(self.output.read_bytes(), b"new tool")
        self.assertEqual(list(self.output.parent.iterdir()), [self.output])

    def test_zip_download_still_extracts_tools_into_a_directory(self):
        contents = io.BytesIO()
        with zipfile.ZipFile(contents, "w") as archive:
            archive.writestr("bin/compiler", b"compiler")
        contents.seek(0)

        download_tool.download("https://example.test/tools.zip", contents, self.output)

        self.assertEqual((self.output / "bin/compiler").read_bytes(), b"compiler")
        self.assertTrue((self.output / "bin/compiler").stat().st_mode & stat.S_IXUSR)

    def test_missing_certificate_package_returns_failure(self):
        error = urllib.error.URLError("CERTIFICATE_VERIFY_FAILED")
        with (
            patch("tools.download_tool.urllib.request.urlopen", side_effect=error),
            patch.dict("sys.modules", {"certifi": None}),
        ):
            self.assertEqual(download_tool.main(), 1)

        self.assertIn("python -m pip install certifi", self.stderr.getvalue())
        self.assertFalse(self.output.exists())

    def test_certificate_retry_uses_the_supplied_trust_store(self):
        context = object()
        certificate_package = SimpleNamespace(where=lambda: "trusted.pem")
        error = urllib.error.URLError("CERTIFICATE_VERIFY_FAILED")
        with (
            patch.dict("sys.modules", {"certifi": certificate_package}),
            patch("ssl.create_default_context", return_value=context) as create_context,
            patch(
                "tools.download_tool.urllib.request.urlopen",
                side_effect=[error, io.BytesIO(b"tool")],
            ) as open_url,
        ):
            self.assertEqual(download_tool.main(), 0)

        create_context.assert_called_once_with(cafile="trusted.pem")
        self.assertIs(open_url.call_args.kwargs["context"], context)
        self.assertIs(open_url.call_args.args[0], open_url.call_args_list[0].args[0])
        self.assertEqual(self.output.read_bytes(), b"tool")


if __name__ == "__main__":
    unittest.main()
