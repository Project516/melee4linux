"""GameCube texture layout and Dolphin replacement names.

The naming algorithm follows Dolphin's VideoCommon/TextureInfo.cpp. Hash the
encoded, block-padded base level, then the used range of palette entries.
"""

import numpy as np
import xxhash

FORMATS = {
    0: "I4",
    1: "I8",
    2: "IA4",
    3: "IA8",
    4: "RGB565",
    5: "RGB5A3",
    6: "RGBA8",
    8: "C4",
    9: "C8",
    10: "C14X2",
    14: "CMPR",
}
BLOCKS = {
    0: (8, 8, 32),
    1: (8, 4, 32),
    2: (8, 4, 32),
    3: (4, 4, 32),
    4: (4, 4, 32),
    5: (4, 4, 32),
    6: (4, 4, 64),
    8: (8, 8, 32),
    9: (8, 4, 32),
    10: (4, 4, 32),
    14: (8, 8, 32),
}
PALETTED = {8, 9, 10}


def texture_size(width: int, height: int, fmt: int) -> int:
    if width < 1 or height < 1:
        raise ValueError("Texture dimensions must be positive")
    bw, bh, size = BLOCKS[fmt]
    return ((width + bw - 1) // bw) * ((height + bh - 1) // bh) * size


def palette_range(data: bytes, fmt: int) -> tuple[int, int]:
    values = np.frombuffer(data, dtype=np.uint8)
    if fmt == 8:
        return int(min((values >> 4).min(), (values & 15).min())), int(
            max((values >> 4).max(), (values & 15).max())
        )
    if fmt == 9:
        return int(values.min()), int(values.max())
    if fmt == 10:
        values = np.frombuffer(data, dtype=">u2") & 0x3FFF
        return int(values.min()), int(values.max())
    raise ValueError(f"Format {fmt} does not use a palette")


def dolphin_name(
    data: bytes,
    width: int,
    height: int,
    fmt: int,
    mipmap: bool = False,
    palette: bytes | None = None,
) -> str:
    size = texture_size(width, height, fmt)
    if len(data) < size:
        raise ValueError("Truncated texture")
    data = data[:size]
    name = (
        f"tex1_{width}x{height}{'_m' if mipmap else ''}_{xxhash.xxh64_hexdigest(data)}"
    )
    if fmt in PALETTED:
        if palette is None:
            raise ValueError("Missing palette")
        low, high = palette_range(data, fmt)
        if fmt == 10:
            # The vendored Dolphin hashes C14X2 palette bounds by swapping
            # every other byte as a u16. Match that bug only for naming.
            # Melee US v1.02 does not contain static C14X2 textures.
            values = (
                np.frombuffer(data, dtype=np.uint8)[::2].astype(np.uint16) << 8
            ) & 0x3FFF
            low, high = int(values.min()), int(values.max())
        if len(palette) < (high + 1) * 2:
            raise ValueError("Palette does not contain all used indices")
        name += "_" + xxhash.xxh64_hexdigest(palette[low * 2 : (high + 1) * 2])
    return f"{name}_{fmt}"
