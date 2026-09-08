"""Focused checks for coverage, sampler borders, and model integrity."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

try:
    import numpy as np
    from PIL import Image

    from tools.texture_upscale.upscale import Upscaler, bleed_transparent_rgb, pad_rgb
except ModuleNotFoundError as error:
    raise unittest.SkipTest(
        "Install tools/texture_upscale/requirements.txt for texture checks"
    ) from error

from tools.texture_upscale.download_models import MODELS, model_path


class UpscaleTests(unittest.TestCase):
    def test_transparent_garbage_does_not_bleed_into_visible_edges(self):
        pixels = np.full((4, 4, 4), (0, 255, 0, 0), dtype=np.uint8)
        pixels[1:3, 1:3] = (240, 30, 10, 255)
        result = np.asarray(
            Upscaler().upscale_image(Image.fromarray(pixels), "lanczos")
        )
        self.assertEqual(result.shape, (16, 16, 4))
        self.assertTrue(np.all(result[:, :, :3] == (240, 30, 10)))
        self.assertEqual(int(result[0, 0, 3]), 0)
        self.assertEqual(int(result[8, 8, 3]), 255)

    def test_empty_texture_stays_empty_and_does_not_load_a_model(self):
        engine = Upscaler()
        with patch.object(
            engine, "_network", side_effect=AssertionError("unexpected inference")
        ):
            result = engine.upscale_image(
                Image.new("RGBA", (3, 5), (90, 180, 240, 0)), "general"
            )
        self.assertEqual(result.size, (12, 20))
        self.assertEqual(np.asarray(result).sum(), 0)

    def test_alpha_does_not_depend_on_ai_color_model(self):
        pixels = np.zeros((6, 7, 4), dtype=np.uint8)
        pixels[1:5, 1:6] = (255, 80, 40, 170)
        source = Image.fromarray(pixels)
        engine = Upscaler()
        reference = engine.upscale_image(source, "bicubic")
        with patch.object(
            engine, "_infer", return_value=np.zeros((24, 28, 3), dtype=np.uint8)
        ):
            inferred = engine.upscale_image(source, "general")
        np.testing.assert_array_equal(
            np.asarray(inferred)[:, :, 3], np.asarray(reference)[:, :, 3]
        )

    def test_repeat_border_uses_other_edge_on_each_axis(self):
        rgb = np.arange(18, dtype=np.uint8).reshape((2, 3, 3))
        padded = pad_rgb(rgb, 1, True, False)
        np.testing.assert_array_equal(padded[1, 0], rgb[0, -1])
        np.testing.assert_array_equal(padded[1, -1], rgb[0, 0])
        np.testing.assert_array_equal(padded[0, 1:-1], rgb[0])

    def test_mirror_border_reverses_source_texels(self):
        rgb = np.arange(9, dtype=np.uint8).reshape((1, 3, 3))
        padded = pad_rgb(rgb, 2, 2, 0)
        np.testing.assert_array_equal(padded[2, :2], rgb[0, 1::-1])
        np.testing.assert_array_equal(padded[2, -2:], rgb[0, :0:-1])

    def test_rgb_bleed_finds_nearest_color_across_repeat_boundary(self):
        rgba = np.zeros((1, 8, 4), dtype=np.uint8)
        rgba[0, 3] = (255, 0, 0, 255)
        rgba[0, 7] = (0, 0, 255, 255)
        clamped = bleed_transparent_rgb(rgba)
        repeated = bleed_transparent_rgb(rgba, wrap_s=1)
        np.testing.assert_array_equal(clamped[0, 0], (255, 0, 0))
        np.testing.assert_array_equal(repeated[0, 0], (0, 0, 255))

    def test_one_texel_mask_and_nearest_keep_exact_values(self):
        image = Image.new("RGBA", (1, 2))
        image.putdata([(10, 20, 30, 0), (50, 60, 70, 255)])
        result = Upscaler().upscale_image(image, "nearest", 2, wrap_s=True, wrap_t=True)
        self.assertEqual(result.size, (2, 4))
        self.assertEqual(set(np.asarray(result)[:, :, 3].flat), {0, 255})

    def test_invalid_scale_or_method_fails(self):
        engine = Upscaler()
        image = Image.new("RGB", (2, 2))
        with self.assertRaises(ValueError):
            engine.upscale_image(image, "invented")
        with self.assertRaises(ValueError):
            engine.upscale_image(image, "nearest", 3)

    def test_altered_model_is_rejected_before_deserialization(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / MODELS["anime"]["file"]).write_bytes(b"not the pinned checkpoint")
            with self.assertRaisesRegex(ValueError, "checksum mismatch"):
                model_path("anime", root)

    def test_missing_model_is_not_downloaded_implicitly(self):
        with (
            tempfile.TemporaryDirectory() as directory,
            patch(
                "urllib.request.urlretrieve",
                side_effect=AssertionError("unexpected download"),
            ),
            self.assertRaises(FileNotFoundError),
        ):
            model_path("general", Path(directory))


if __name__ == "__main__":
    unittest.main()
