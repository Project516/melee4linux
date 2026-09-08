"""Write lossless RGBA8 DDS textures with a complete mip chain."""

import math
import struct
from pathlib import Path

import numpy as np
from PIL import Image


def resize_float(array, size):
    return np.asarray(
        Image.fromarray(array.astype(np.float32)).resize(size, Image.Resampling.BOX)
    )


def next_mip(image, data_channels=False):
    size = (max(1, image.width // 2), max(1, image.height // 2))
    pixels = np.asarray(image.convert("RGBA"), dtype=np.float32) / 255
    if data_channels:
        output = np.stack(
            [resize_float(pixels[:, :, channel], size) for channel in range(4)], axis=2
        )
    else:
        alpha = pixels[:, :, 3]
        rgb = pixels[:, :, :3]
        linear = np.where(rgb <= 0.04045, rgb / 12.92, ((rgb + 0.055) / 1.055) ** 2.4)
        reduced_alpha = resize_float(alpha, size)
        reduced = np.stack(
            [resize_float(linear[:, :, channel] * alpha, size) for channel in range(3)],
            axis=2,
        )
        reduced = np.divide(
            reduced,
            reduced_alpha[:, :, None],
            out=np.zeros_like(reduced),
            where=reduced_alpha[:, :, None] > 1e-8,
        )
        srgb = np.where(
            reduced <= 0.0031308,
            reduced * 12.92,
            1.055 * np.maximum(reduced, 0) ** (1 / 2.4) - 0.055,
        )
        output = np.dstack([srgb, reduced_alpha])
    return Image.fromarray(np.clip(np.rint(output * 255), 0, 255).astype(np.uint8))


def write_dds(image, destination, data_channels=False):
    """Dolphin's legacy DDS reader accepts these little-endian RGBA masks."""
    image = image.convert("RGBA")
    width, height = image.size
    levels = int(math.log2(max(width, height))) + 1
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
        0x401008 if levels > 1 else 0x1000,
        0,
        0,
        0,
        0,
    ]
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(".dds.tmp")
    with temporary.open("wb") as output:
        output.write(b"DDS " + struct.pack("<31I", *header))
        for level in range(levels):
            output.write(image.tobytes())
            if level + 1 < levels:
                image = next_mip(image, data_channels)
    temporary.replace(destination)
    return levels
