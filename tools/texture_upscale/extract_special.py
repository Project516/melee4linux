"""Locate GX textures that do not use archive HSD_ImageDesc records.

SIS glyphs follow the uploads in baselib/hsd_3A76.c. TPL records follow
charPipeline/texPalette.h. DOL addresses use the US v1.02 symbol map.
All offsets in returned records are file offsets, not relocated addresses.
"""

import hashlib
import struct
from io import BytesIO
from pathlib import Path

from PIL import Image

from .texture_formats import FORMATS, PALETTED, texture_size

_US_102_SHA1 = "08e0bf20134dfcb260699671004527b2d6bb1a45"
_FONT_ADDRESS = 0x8040CD40
_FONT_GLYPHS = 287
_GLYPH_BYTES = 512


def _u32(data: bytes, offset: int) -> int:
    return struct.unpack_from(">I", data, offset)[0]


def _span(data: bytes, offset: int, size: int) -> bool:
    return 0 <= offset <= len(data) and 0 <= size <= len(data) - offset


def decode_thp_still(data: bytes) -> Image.Image:
    """Decode a Melee ending still, which stores JPEG entropy without stuffing.

    THPDec.c reads one baseline JPEG scan directly. Standard JPEG decoders
    need a zero byte after each FF byte in that scan. Header markers and the
    final end marker must remain unchanged. This is not an MTH movie decoder.
    """
    if not data.startswith(b"\xff\xd8") or not data.endswith(b"\xff\xd9"):
        raise ValueError("THP still needs JPEG start and end markers")
    offset = 2
    has_frame = False
    while offset + 4 <= len(data) - 2:
        if data[offset] != 0xFF:
            raise ValueError("Invalid THP still marker")
        marker = data[offset + 1]
        length = struct.unpack_from(">H", data, offset + 2)[0]
        end = offset + 2 + length
        if length < 2 or end > len(data) - 2:
            raise ValueError("Truncated THP still header")
        if marker == 0xC0:
            if length != 17 or data[offset + 4] != 8 or data[offset + 9] != 3:
                raise ValueError("THP still needs an 8-bit frame with three components")
            has_frame = True
        elif marker == 0xDA:
            if not has_frame or length != 12 or data[offset + 4] != 3:
                raise ValueError("THP still needs one scan with three components")
            if data[end - 3 : end] != b"\x00\x3f\x00":
                raise ValueError("THP still needs a baseline JPEG scan")
            entropy = data[end:-2].replace(b"\xff", b"\xff\x00")
            jpeg = data[:end] + entropy + b"\xff\xd9"
            try:
                with Image.open(BytesIO(jpeg)) as image:
                    return image.convert("RGB")
            except OSError as error:
                raise ValueError(f"Cannot decode THP still: {error}") from error
        elif marker not in (0xC4, 0xDB, 0xFE) and not 0xE0 <= marker <= 0xEF:
            raise ValueError(f"Unsupported THP still marker {marker:#x}")
        offset = end
    raise ValueError("THP still has no scan")


def _glyphs(start: int, count: int, kind: str, symbol: str) -> list[dict]:
    return [
        {
            "image_offset": start + index * _GLYPH_BYTES,
            "width": 32,
            "height": 32,
            "format": 0,
            "mipmap": False,
            "kind": kind,
            "symbol": symbol,
            "glyph_index": index,
        }
        for index in range(count)
    ]


def _sis_textures(data: bytes) -> tuple[list[dict], list[str]]:
    if len(data) < 32:
        return [], []
    size, data_size, reloc_count, public_count, external_count = struct.unpack_from(
        ">5I", data
    )
    reloc_start = 32 + data_size
    public_start = reloc_start + reloc_count * 4
    strings_start = public_start + (public_count + external_count) * 8
    if size != len(data) or not 32 <= strings_start <= len(data):
        return [], []

    roots = []
    for index in range(public_count):
        root, name_offset = struct.unpack_from(">II", data, public_start + index * 8)
        start = strings_start + name_offset
        end = data.find(b"\0", start)
        if start < strings_start or end < start:
            continue
        name = data[start:end]
        if name.startswith(b"SIS_"):
            roots.append((root, name.decode("ascii", errors="replace")))
    if not roots:
        return [], []

    # Every relocated pointer marks a distinct archive block. A glyph block
    # contains only raw I4 pixels, so its next target is its end boundary.
    pointers = {}
    for index in range(reloc_count):
        location = _u32(data, reloc_start + index * 4)
        if location + 4 > data_size:
            return [], ["SIS archive has an out-of-bounds relocation"]
        pointers[location] = _u32(data, 32 + location)
    boundaries = sorted({data_size, *(p for p in pointers.values() if p <= data_size)})
    images, warnings = [], []
    for root, name in roots:
        if root not in pointers or root + 8 > data_size:
            warnings.append(f"{name}: missing glyph pointer")
            continue
        start = pointers[root]
        if start == data_size:
            continue  # Some English archives need only the built-in font.
        end = next((point for point in boundaries if point > start), None)
        if end is None or start % 32 or (end - start) % _GLYPH_BYTES:
            warnings.append(f"{name}: invalid glyph block bounds")
            continue
        images.extend(
            _glyphs(32 + start, (end - start) // _GLYPH_BYTES, "sis-font", name)
        )
    return images, warnings


def _dol_sections(data: bytes) -> list[tuple[int, int, int]]:
    """Return data sections as (file offset, virtual address, size)."""
    if len(data) < 0x100:
        raise ValueError("Truncated DOL header")
    sections = []
    for index in range(18):
        offset = _u32(data, index * 4)
        address = _u32(data, 0x48 + index * 4)
        size = _u32(data, 0x90 + index * 4)
        if not size:
            continue
        if offset < 0x100 or not _span(data, offset, size):
            raise ValueError("DOL section is outside the file")
        if index >= 7:
            sections.append((offset, address, size))
    return sections


def _dol_offset(
    sections: list[tuple[int, int, int]], address: int, size: int
) -> int | None:
    for offset, start, section_size in sections:
        if start <= address and address + size <= start + section_size:
            return offset + address - start
    return None


def _dol_textures(data: bytes) -> tuple[list[dict], list[str]]:
    try:
        sections = _dol_sections(data)
    except ValueError as error:
        return [], [str(error)]
    images, warnings = [], []
    if hashlib.sha1(data).hexdigest() == _US_102_SHA1:
        offset = _dol_offset(sections, _FONT_ADDRESS, _FONT_GLYPHS * _GLYPH_BYTES)
        if offset is not None:
            images.extend(
                _glyphs(offset, _FONT_GLYPHS, "dol-font", "HSD_SisLib_FontAtlas")
            )
    else:
        warnings.append(
            "Unknown DOL SHA-1. Built-in font addresses require Melee US v1.02"
        )

    # Validate full HSD_ImageDesc fields and mapped pixel bounds, rather than
    # accepting arbitrary width/height pairs within executable data. US v1.02
    # has one static record: grPu_803E7620 in grpura.c, a 32x32 RGB565 image.
    for section_offset, address, section_size in sections:
        for offset in range(section_offset, section_offset + section_size - 23, 4):
            pointer, width, height, fmt, mipmap, min_lod, max_lod = struct.unpack_from(
                ">IHHIIff", data, offset
            )
            if (
                pointer % 32
                or fmt not in FORMATS
                or not 1 <= width <= 1024
                or not 1 <= height <= 1024
                or mipmap not in (0, 1)
                or not 0 <= min_lod <= max_lod <= 10
            ):
                continue
            size = texture_size(width, height, fmt)
            image_offset = _dol_offset(sections, pointer, size)
            if image_offset is None:
                continue
            descriptor_address = address + offset - section_offset
            if fmt in PALETTED:
                warnings.append(f"DOL image at {descriptor_address:#x} needs a palette")
                continue
            images.append(
                {
                    "image_offset": image_offset,
                    "descriptor_offset": offset,
                    "width": width,
                    "height": height,
                    "format": fmt,
                    "mipmap": bool(mipmap),
                    "kind": "dol-image",
                    "symbol": f"HSD_ImageDesc_{descriptor_address:08x}",
                }
            )
    return images, warnings


def _tpl_textures(data: bytes) -> tuple[list[dict], list[str]]:
    if len(data) < 12:
        return [], ["Truncated TPL header"]
    count, table = struct.unpack_from(">II", data, 4)
    if table < 12 or not _span(data, table, count * 8):
        return [], ["TPL descriptor table is outside the file"]
    images, warnings = [], []
    for index in range(count):
        header, palette = struct.unpack_from(">II", data, table + index * 8)
        if header == 0:
            continue
        if not _span(data, header, 36):
            warnings.append(f"TPL {index}: truncated texture header")
            continue
        height, width, fmt, image_offset = struct.unpack_from(">HHII", data, header)
        if fmt not in FORMATS or not 1 <= width <= 1024 or not 1 <= height <= 1024:
            warnings.append(f"TPL {index}: unsupported texture layout")
            continue
        if not _span(data, image_offset, texture_size(width, height, fmt)):
            warnings.append(f"TPL {index}: truncated pixels")
            continue
        image = {
            "image_offset": image_offset,
            "descriptor_offset": header,
            "width": width,
            "height": height,
            "format": fmt,
            "mipmap": data[header + 33] != data[header + 34],
            "kind": "tpl",
        }
        if fmt in PALETTED:
            if not palette or not _span(data, palette, 12):
                warnings.append(f"TPL {index}: missing palette header")
                continue
            entries, _, _, palette_format, palette_offset = struct.unpack_from(
                ">HBBII", data, palette
            )
            if (
                palette_format not in (0, 1, 2)
                or entries == 0
                or not _span(data, palette_offset, entries * 2)
            ):
                warnings.append(f"TPL {index}: invalid palette")
                continue
            image.update(
                {
                    "palette_offset": palette_offset,
                    "palette_format": palette_format,
                    "palette_entries": entries,
                }
            )
        images.append(image)
    return images, warnings


def special_textures(path: Path, data: bytes) -> tuple[list[dict], list[str]]:
    """Return texture records and explicit warnings for recognized containers.

    Movie YUV buffers, EFB copies, and the CPU-drawn debug font are runtime
    output. They do not have static GX texture bytes to hash here. The banner
    is disc metadata, so callers can report it separately from gameplay.
    """
    if path.suffix.lower() == ".dol":
        return _dol_textures(data)
    if data[:4] == b"\x00\x20\xaf\x30":
        return _tpl_textures(data)
    if data[:4] in (b"BNR1", b"BNR2"):
        if not _span(data, 32, 96 * 32 * 2):
            return [], ["Truncated banner pixels"]
        return [
            {
                "image_offset": 32,
                "width": 96,
                "height": 32,
                "format": 5,
                "mipmap": False,
                "kind": "banner",
            }
        ], []
    if path.suffix.lower() in (".dat", ".usd"):
        return _sis_textures(data)
    return [], []
