import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from tools.texture_upscale.pipeline import build, recipe


def texture(
    name="tex1_test", size=16, format_id=14, kind="hsd_image", file="PlFxNr.dat"
):
    return {
        "name": name,
        "path": "original.png",
        "width": size,
        "height": size,
        "format": format_id,
        "sources": [{"kind": kind, "file": file, "wrap_s": 2, "wrap_t": 0}],
    }


class PipelineTests(unittest.TestCase):
    def test_portrait_tables_use_ai_but_effects_and_tiny_data_do_not(self):
        self.assertEqual(
            recipe(texture(size=128, kind="hsd_animation", file="MnSlChr.usd"))[
                "method"
            ],
            "esrgan",
        )
        self.assertEqual(
            recipe(texture(size=128, file="EfCoData.dat"))["method"], "channels"
        )
        self.assertEqual(recipe(texture(size=128, format_id=0))["method"], "channels")
        self.assertEqual(recipe(texture(size=16))["method"], "channels")
        self.assertEqual(recipe(texture())["wrap_s"], 2)

    def test_resume_repairs_damaged_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            image = Image.new("RGBA", (16, 16), (20, 70, 90, 255))
            image.save(root / "original.png")
            entry = texture()
            entry["rgba_sha256"] = hashlib.sha256(image.tobytes()).hexdigest()
            manifest = root / "manifest.json"
            manifest.write_text(json.dumps({"textures": [entry]}))
            output = root / "pack"
            build(manifest, output, root / "unused-models")
            png = output / "images/tex1_test.png"
            expected = png.read_bytes()
            png.write_bytes(b"interrupted output")
            build(manifest, output, root / "unused-models")
            self.assertEqual(png.read_bytes(), expected)
            self.assertEqual(
                json.loads((output / "summary.json").read_text())["errors"], []
            )


if __name__ == "__main__":
    unittest.main()
