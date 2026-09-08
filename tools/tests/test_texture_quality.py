"""Reject corrupt texture packs and unexpected alpha or channel changes."""

import hashlib
import json
import struct
import tempfile
import unittest
from pathlib import Path

try:
    import numpy as np
    from PIL import Image

    from tools.texture_upscale.quality_report import check_texture, dds_layout
except ModuleNotFoundError as error:
    raise unittest.SkipTest(
        "Install the texture requirements for quality checks"
    ) from error


def sample_dds(pixels):
    height, width = pixels.shape[:2]
    levels = max(width, height).bit_length()
    header = [
        124,
        0x2100F,
        height,
        width,
        width * 4,
        0,
        levels,
        *([0] * 11),
        32,
        0x41,
        0,
        32,
        0xFF,
        0xFF00,
        0xFF0000,
        0xFF000000,
        0x401008,
        0,
        0,
        0,
        0,
    ]
    payload = bytearray(b"DDS " + struct.pack("<31I", *header))
    for _ in range(levels):
        payload.extend(pixels.tobytes())
        width, height = max(1, width // 2), max(1, height // 2)
        pixels = np.broadcast_to(pixels[0, 0], (height, width, 4)).copy()
    return payload


class TextureQualityTests(unittest.TestCase):
    def test_accepts_complete_rectangular_mip_chain(self):
        levels = dds_layout(sample_dds(np.zeros((3, 8, 4), np.uint8)))
        self.assertEqual(
            [level.shape[:2] for level in levels], [(3, 8), (1, 4), (1, 2), (1, 1)]
        )

    def test_rejects_truncated_payload_and_trailing_data(self):
        valid = sample_dds(np.zeros((4, 4, 4), np.uint8))
        with self.assertRaisesRegex(ValueError, "Truncated"):
            dds_layout(valid[:-1])
        with self.assertRaisesRegex(ValueError, "Unexpected bytes"):
            dds_layout(valid + b"extra")

    def test_rejects_wrong_channel_masks(self):
        data = sample_dds(np.zeros((2, 2, 4), np.uint8))
        struct.pack_into("<I", data, 4 + 22 * 4, 0xFF0000)
        with self.assertRaisesRegex(ValueError, "channel masks"):
            dds_layout(data)

    def test_rejects_incomplete_chain(self):
        data = sample_dds(np.zeros((4, 4, 4), np.uint8))
        struct.pack_into("<I", data, 4 + 6 * 4, 1)
        with self.assertRaisesRegex(ValueError, "complete mip chain"):
            dds_layout(data)

    def test_detects_opaque_source_becoming_transparent(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "records").mkdir()
            source = np.full((2, 2, 4), 255, np.uint8)
            output = source.copy()
            output[:, :, 3] = 100
            Image.fromarray(source).save(root / "original.png")
            Image.fromarray(output).save(root / "out.png")
            (root / "out.dds").write_bytes(sample_dds(output))
            digest = hashlib.sha256(source.tobytes()).hexdigest()
            record = {
                "png": "out.png",
                "dds": "out.dds",
                "png_sha256": hashlib.sha256(
                    (root / "out.png").read_bytes()
                ).hexdigest(),
                "dds_sha256": hashlib.sha256(
                    (root / "out.dds").read_bytes()
                ).hexdigest(),
                "mip_levels": 2,
                "recipe": {"scale": 1, "method": "channels", "data_channels": True},
            }
            (root / "records/texture.json").write_text(json.dumps(record))
            texture = {
                "name": "texture",
                "path": "original.png",
                "height": 2,
                "width": 2,
                "rgba_sha256": digest,
            }
            result = check_texture(texture, root, root)
            self.assertIn("Opaque texture acquired transparency", result["errors"])
            self.assertIn("Equal data channels 0 and 3 diverged", result["errors"])


if __name__ == "__main__":
    unittest.main()
