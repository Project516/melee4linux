import importlib.util
import struct
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

spec = importlib.util.spec_from_file_location(
    "texture_dds", Path(__file__).parents[1] / "texture_upscale/dds.py"
)
dds = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dds)


class DdsTests(unittest.TestCase):
    def test_non_power_of_two_full_chain_and_channel_masks(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "test.dds"
            levels = dds.write_dds(Image.new("RGBA", (7, 3), (5, 9, 13, 255)), output)
            data = output.read_bytes()
            self.assertEqual(data[:4], b"DDS ")
            header = struct.unpack("<31I", data[4:128])
            self.assertEqual((header[2], header[3], header[6]), (3, 7, 3))
            self.assertEqual(header[21:26], (32, 0xFF, 0xFF00, 0xFF0000, 0xFF000000))
            self.assertEqual(levels, 3)
            self.assertEqual(len(data), 128 + (7 * 3 + 3 * 1 + 1) * 4)

    def test_color_mips_ignore_hidden_rgb(self):
        source = Image.fromarray(
            np.array([[[255, 0, 0, 255], [0, 255, 0, 0]]], dtype=np.uint8)
        )
        self.assertEqual(dds.next_mip(source).getpixel((0, 0)), (255, 0, 0, 128))

    def test_data_mips_preserve_intensity_alpha_identity(self):
        source = np.array([[[0] * 4, [255] * 4]], dtype=np.uint8)
        self.assertEqual(
            dds.next_mip(Image.fromarray(source), True).getpixel((0, 0)), (128,) * 4
        )


if __name__ == "__main__":
    unittest.main()
