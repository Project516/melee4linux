"""Decode tiled GameCube textures without changing transparent RGB values."""

import numpy as np
from PIL import Image

from .texture_formats import BLOCKS, PALETTED, texture_size


def _expand(value, bits):
    if bits == 3:
        return (value << 5) | (value << 2) | (value >> 1)
    if bits == 4:
        return value * 17
    if bits == 5:
        return (value << 3) | (value >> 2)
    return (value << 2) | (value >> 4)


def _rgb565(values):
    return np.stack(
        (
            _expand(values >> 11, 5),
            _expand((values >> 5) & 63, 6),
            _expand(values & 31, 5),
            np.full_like(values, 255),
        ),
        -1,
    )


def _rgb5a3(values):
    opaque = values & 0x8000 != 0
    return np.stack(
        (
            np.where(
                opaque, _expand((values >> 10) & 31, 5), _expand((values >> 8) & 15, 4)
            ),
            np.where(
                opaque, _expand((values >> 5) & 31, 5), _expand((values >> 4) & 15, 4)
            ),
            np.where(opaque, _expand(values & 31, 5), _expand(values & 15, 4)),
            np.where(opaque, 255, _expand((values >> 12) & 7, 3)),
        ),
        -1,
    )


def decode_texture(
    data: bytes,
    width: int,
    height: int,
    fmt: int,
    palette: bytes | None = None,
    palette_format: int = 2,
) -> Image.Image:
    """Return RGBA pixels. CMPR uses the GameCube's 3/8 color interpolation."""
    size = texture_size(width, height, fmt)
    if len(data) < size:
        raise ValueError("Truncated texture")
    bw, bh, block_size = BLOCKS[fmt]
    nx, ny = (width + bw - 1) // bw, (height + bh - 1) // bh
    source = np.frombuffer(data[:size], dtype=np.uint8).reshape(-1, block_size)
    if fmt in (0, 8):
        values = np.stack((source >> 4, source & 15), -1).reshape(-1, bw * bh)
    elif fmt in (3, 4, 5, 10):
        values = np.frombuffer(data[:size], dtype=">u2").reshape(-1, bw * bh)
    else:
        values = source

    if fmt in (0, 1):
        intensity = values * 17 if fmt == 0 else values
        pixels = np.repeat(intensity[..., None], 4, -1)
    elif fmt == 2:
        intensity, alpha = (values & 15) * 17, (values >> 4) * 17
        pixels = np.stack((intensity, intensity, intensity, alpha), -1)
    elif fmt == 3:
        intensity, alpha = values & 255, values >> 8
        pixels = np.stack((intensity, intensity, intensity, alpha), -1)
    elif fmt == 4:
        pixels = _rgb565(values)
    elif fmt == 5:
        pixels = _rgb5a3(values)
    elif fmt == 6:
        planes = source.reshape(-1, 2, 16, 2)
        pixels = np.stack(
            (
                planes[:, 0, :, 1],
                planes[:, 1, :, 0],
                planes[:, 1, :, 1],
                planes[:, 0, :, 0],
            ),
            -1,
        )
    elif fmt in PALETTED:
        if palette is None or len(palette) % 2:
            raise ValueError("Missing or invalid palette")
        entries = np.frombuffer(palette, dtype=">u2")
        if palette_format == 0:
            intensity, alpha = entries & 255, entries >> 8
            colors = np.stack((intensity, intensity, intensity, alpha), -1)
        elif palette_format == 1:
            colors = _rgb565(entries)
        elif palette_format == 2:
            colors = _rgb5a3(entries)
        else:
            raise ValueError(f"Unknown palette format {palette_format}")
        if fmt == 10:
            values = values & 0x3FFF
        if values.max() >= len(colors):
            raise ValueError("Palette does not contain all used indices")
        pixels = colors[values]
    elif fmt == 14:
        subblocks = source.reshape(-1, 4, 8)
        first = subblocks[:, :, 0].astype(np.uint16) * 256 + subblocks[:, :, 1]
        second = subblocks[:, :, 2].astype(np.uint16) * 256 + subblocks[:, :, 3]
        c0, c1 = _rgb565(first), _rgb565(second)
        opaque = (first > second)[..., None]
        c2 = np.where(opaque, (c0 * 5 + c1 * 3) >> 3, (c0 + c1) // 2)
        c3 = np.where(opaque, (c0 * 3 + c1 * 5) >> 3, (c0 + c1) // 2)
        c3[:, :, 3] = np.where(first > second, 255, 0)
        colors = np.stack((c0, c1, c2, c3), 2)
        indices = (
            subblocks[:, :, 4:, None] >> np.array([6, 4, 2, 0], dtype=np.uint8)
        ) & 3
        pixels = colors[
            np.arange(len(source))[:, None, None, None],
            np.arange(4)[None, :, None, None],
            indices,
        ]
        pixels = pixels.reshape(-1, 2, 2, 4, 4, 4).transpose(0, 1, 3, 2, 4, 5)
    else:
        raise ValueError(f"Unknown texture format {fmt}")
    pixels = pixels.reshape(ny, nx, bh, bw, 4).transpose(0, 2, 1, 3, 4)
    pixels = pixels.reshape(ny * bh, nx * bw, 4)[:height, :width].astype(np.uint8)
    return Image.fromarray(pixels)
