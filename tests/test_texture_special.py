"""Synthetic containers test texture bounds without storing game assets."""

import struct
import unittest
from io import BytesIO
from pathlib import Path
from random import Random

from PIL import Image

from tools.texture_upscale.extract_special import decode_thp_still, special_textures


def sis_archive(glyph_bytes=1024, extra_block=True):
    image_start = 64
    image_end = image_start + glyph_bytes
    data_size = image_end + (64 if extra_block else 0)
    body = bytearray(data_size)
    struct.pack_into(">III", body, 0, image_start, 32, image_end)
    relocations = (
        struct.pack(">III", 0, 4, 8) if extra_block else struct.pack(">II", 0, 4)
    )
    publics = struct.pack(">II", 0, 0)
    names = b"SIS_Test\0"
    header = struct.pack(
        ">8I",
        32 + len(body + relocations + publics + names),
        data_size,
        len(relocations) // 4,
        1,
        0,
        0,
        0,
        0,
    )
    return header + body + relocations + publics + names


def dol_image(pointer=0x803E6E20):
    data = bytearray(0x100 + 0x900)
    struct.pack_into(">I", data, 7 * 4, 0x100)
    struct.pack_into(">I", data, 0x48 + 7 * 4, 0x803E6E20)
    struct.pack_into(">I", data, 0x90 + 7 * 4, 0x900)
    struct.pack_into(">IHHIIff", data, 0x900, pointer, 32, 32, 4, 0, 0, 0)
    return data


def tpl_image(paletted=False):
    data = bytearray(160)
    struct.pack_into(">III", data, 0, 0x20AF30, 1, 12)
    struct.pack_into(">II", data, 12, 20, 56 if paletted else 0)
    struct.pack_into(">HHII", data, 20, 8, 8, 8 if paletted else 0, 96)
    if paletted:
        struct.pack_into(">HBBII", data, 56, 16, 0, 0, 2, 128)
    return data


class SpecialTextureTests(unittest.TestCase):
    def test_thp_still_restores_entropy_without_changing_header_markers(self):
        # Build a standard JPEG, remove its entropy stuffing as Melee does,
        # then require the same pixels from both decoding paths.
        image = Image.frombytes("RGB", (64, 64), Random(42).randbytes(64 * 64 * 3))
        encoded = BytesIO()
        image.save(encoded, format="JPEG", quality=92, subsampling=2)
        jpeg = encoded.getvalue()
        scan = jpeg.index(b"\xff\xda")
        start = scan + 2 + struct.unpack_from(">H", jpeg, scan + 2)[0]
        self.assertIn(b"\xff\x00", jpeg[start:-2])
        thp = jpeg[:start] + jpeg[start:-2].replace(b"\xff\x00", b"\xff") + jpeg[-2:]
        actual = decode_thp_still(thp)
        expected = Image.open(BytesIO(jpeg)).convert("RGB")
        self.assertEqual(actual.size, (64, 64))
        self.assertEqual(actual.mode, "RGB")
        self.assertEqual(actual.tobytes(), expected.tobytes())

    def test_thp_still_rejects_truncated_and_unsupported_headers(self):
        cases = [
            b"\xff\xd8\xff\xfe\xff\xff\xff\xd9",
            b"\xff\xd8\xff\xc2\x00\x02\xff\xd9",
            b"\xff\xd8\xff\xda\x00\x02\xff\xd9",
            b"\xff\xd8\xff\xd9",
            b"not a JPEG",
        ]
        for data in cases:
            with self.subTest(data=data), self.assertRaises(ValueError):
                decode_thp_still(data)

    def test_sis_stops_at_next_relocated_block(self):
        images, warnings = special_textures(Path("SdTest.dat"), sis_archive())
        self.assertEqual(warnings, [])
        self.assertEqual([image["image_offset"] for image in images], [96, 608])
        self.assertEqual([image["glyph_index"] for image in images], [0, 1])
        self.assertTrue(
            all(image["width"] == image["height"] == 32 for image in images)
        )
        self.assertEqual(images[0]["format"], 0)
        self.assertEqual(images[0]["symbol"], "SIS_Test")

    def test_sis_empty_font_is_valid(self):
        images, warnings = special_textures(Path("SdEmpty.usd"), sis_archive(0, False))
        self.assertEqual((images, warnings), ([], []))

    def test_sis_partial_glyph_is_rejected(self):
        images, warnings = special_textures(Path("SdBad.dat"), sis_archive(513))
        self.assertEqual(images, [])
        self.assertIn("invalid glyph block bounds", warnings[0])

    def test_sis_bad_relocation_is_rejected(self):
        data = bytearray(sis_archive())
        data_size = struct.unpack_from(">I", data, 4)[0]
        struct.pack_into(">I", data, 32 + data_size, data_size + 4)
        images, warnings = special_textures(Path("SdBad.dat"), data)
        self.assertEqual(images, [])
        self.assertIn("out-of-bounds relocation", warnings[0])

    def test_banner_requires_all_tiled_pixels(self):
        data = b"BNR1" + bytes(28 + 96 * 32 * 2)
        images, warnings = special_textures(Path("opening.bnr"), data)
        self.assertEqual(warnings, [])
        self.assertEqual(
            (images[0]["width"], images[0]["height"], images[0]["format"]), (96, 32, 5)
        )
        images, warnings = special_textures(Path("opening.bnr"), data[:-1])
        self.assertEqual(images, [])
        self.assertEqual(warnings, ["Truncated banner pixels"])

    def test_dol_maps_virtual_image_address_to_file(self):
        images, warnings = special_textures(Path("main.dol"), dol_image())
        self.assertEqual(len(images), 1)
        self.assertEqual(images[0]["image_offset"], 0x100)
        self.assertEqual(images[0]["descriptor_offset"], 0x900)
        self.assertEqual(images[0]["symbol"], "HSD_ImageDesc_803e7620")
        self.assertIn("Unknown DOL SHA-1", warnings[0])

    def test_dol_cannot_use_pixels_outside_mapped_section(self):
        images, _ = special_textures(Path("main.dol"), dol_image(0x803E7640))
        self.assertEqual(images, [])

    def test_dol_rejects_truncated_sections(self):
        images, warnings = special_textures(Path("main.dol"), dol_image()[:-1])
        self.assertEqual(images, [])
        self.assertEqual(warnings, ["DOL section is outside the file"])

    def test_tpl_palette_and_mipmap_are_preserved(self):
        data = tpl_image(True)
        data[20 + 34] = 2
        images, warnings = special_textures(Path("indexed.tpl"), data)
        self.assertEqual(warnings, [])
        self.assertEqual(len(images), 1)
        self.assertEqual(images[0]["palette_offset"], 128)
        self.assertEqual(images[0]["palette_entries"], 16)
        self.assertEqual(images[0]["palette_format"], 2)
        self.assertTrue(images[0]["mipmap"])

    def test_tpl_rejects_missing_palette_and_short_pixels(self):
        data = tpl_image(True)
        struct.pack_into(">I", data, 16, 0)
        images, warnings = special_textures(Path("bad.tpl"), data)
        self.assertEqual(images, [])
        self.assertIn("missing palette", warnings[0])
        images, warnings = special_textures(Path("bad.tpl"), tpl_image()[:127])
        self.assertEqual(images, [])
        self.assertIn("truncated pixels", warnings[0])

    def test_tpl_rejects_table_outside_file(self):
        data = tpl_image()
        struct.pack_into(">I", data, 8, 0xFFFFFFFC)
        images, warnings = special_textures(Path("bad.tpl"), data)
        self.assertEqual(images, [])
        self.assertIn("descriptor table", warnings[0])

    def test_unrelated_file_is_not_a_texture_container(self):
        self.assertEqual(special_textures(Path("music.hps"), bytes(100)), ([], []))


if __name__ == "__main__":
    unittest.main()
