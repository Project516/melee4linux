"""Synthetic pixels and archives verify extraction without game data."""

import struct
import tempfile
import unittest
from pathlib import Path

import xxhash

from tools.texture_upscale.decode import decode_texture
from tools.texture_upscale.extract import (
    archive_chunks,
    extract_disc,
    hsd_textures,
    parse_archive,
    particle_textures,
)
from tools.texture_upscale.texture_formats import dolphin_name, texture_size


def archive(body, relocations, symbols=((0, "test"),)):
    names = bytearray()
    publics = bytearray()
    for offset, name in symbols:
        publics.extend(struct.pack(">II", offset, len(names)))
        names.extend(name.encode() + b"\0")
    relocations = struct.pack(f">{len(relocations)}I", *relocations)
    size = 32 + len(body) + len(relocations) + len(publics) + len(names)
    return (
        struct.pack(
            ">8I", size, len(body), len(relocations) // 4, len(symbols), 0, 0, 0, 0
        )
        + body
        + relocations
        + publics
        + names
    )


class TextureDecodeTests(unittest.TestCase):
    def test_intensity_is_also_alpha(self):
        self.assertEqual(
            decode_texture(bytes([0x38]) * 32, 8, 8, 0).getpixel((0, 0)),
            (51, 51, 51, 51),
        )
        self.assertEqual(
            decode_texture(bytes([0x38]) * 32, 8, 8, 0).getpixel((1, 0)),
            (136, 136, 136, 136),
        )
        self.assertEqual(
            decode_texture(bytes([73]) * 32, 8, 4, 1).getpixel((0, 0)), (73, 73, 73, 73)
        )

    def test_ia_channel_order(self):
        self.assertEqual(
            decode_texture(bytes([0x38]) * 32, 8, 4, 2).getpixel((0, 0)),
            (136, 136, 136, 51),
        )
        self.assertEqual(
            decode_texture(bytes([31, 123]) * 16, 4, 4, 3).getpixel((0, 0)),
            (123, 123, 123, 31),
        )

    def test_rgba_planes_and_non_block_dimensions(self):
        encoded = bytes([31, 42]) * 16 + bytes([53, 64]) * 16
        image = decode_texture(encoded, 3, 2, 6)
        self.assertEqual(image.size, (3, 2))
        self.assertEqual(image.getpixel((2, 1)), (42, 53, 64, 31))
        self.assertEqual(texture_size(3, 2, 6), 64)

    def test_rgb16_bit_expansion(self):
        self.assertEqual(
            decode_texture(bytes.fromhex("f800") * 16, 4, 4, 4).getpixel((0, 0)),
            (255, 0, 0, 255),
        )
        self.assertEqual(
            decode_texture(bytes.fromhex("ffff") * 16, 4, 4, 5).getpixel((0, 0)),
            (255, 255, 255, 255),
        )
        self.assertEqual(
            decode_texture(bytes.fromhex("3123") * 16, 4, 4, 5).getpixel((0, 0)),
            (17, 34, 51, 109),
        )

    def test_cmpr_uses_console_blend_and_transparent_rgb(self):
        opaque = bytes.fromhex("f800001faaaaaaaa")
        transparent = bytes.fromhex("001ff800ffffffff")
        image = decode_texture(opaque + transparent + opaque + transparent, 8, 8, 14)
        self.assertEqual(image.getpixel((0, 0)), (159, 0, 95, 255))
        self.assertEqual(image.getpixel((4, 0)), (127, 0, 127, 0))
        self.assertEqual(image.getpixel((0, 4)), (159, 0, 95, 255))

    def test_palette_formats(self):
        cases = [
            (0, bytes([41, 79]), (79, 79, 79, 41)),
            (1, bytes.fromhex("f800"), (255, 0, 0, 255)),
            (2, bytes.fromhex("3123"), (17, 34, 51, 109)),
        ]
        for fmt, palette, expected in cases:
            with self.subTest(fmt=fmt):
                self.assertEqual(
                    decode_texture(bytes(32), 8, 8, 8, palette, fmt).getpixel((0, 0)),
                    expected,
                )

    def test_c14_ignores_unused_high_bits(self):
        self.assertEqual(
            decode_texture(
                bytes.fromhex("c001") * 16, 4, 4, 10, bytes.fromhex("0000ffff"), 2
            ).getpixel((0, 0)),
            (255, 255, 255, 255),
        )

    def test_short_texture_and_missing_palette_fail(self):
        with self.assertRaisesRegex(ValueError, "Truncated"):
            decode_texture(bytes(31), 8, 8, 0)
        with self.assertRaisesRegex(ValueError, "palette"):
            decode_texture(bytes(32), 8, 8, 8)

    def test_dolphin_name_hashes_padded_pixels_and_used_palette_span(self):
        pixels = bytes([0x45]) * 32
        palette = bytes(range(32))
        expected = f"tex1_3x2_m_{xxhash.xxh64_hexdigest(pixels)}_{xxhash.xxh64_hexdigest(palette[8:12])}_8"
        self.assertEqual(
            dolphin_name(pixels + bytes(32), 3, 2, 8, True, palette), expected
        )
        unused_changed = bytes([255]) * 8 + palette[8:12] + bytes(20)
        self.assertEqual(dolphin_name(pixels, 3, 2, 8, True, unused_changed), expected)

    def test_c14_name_matches_vendored_dolphin_byte_swap_bug(self):
        pixels = bytes.fromhex("0001") * 16
        palette = bytes.fromhex("12345678")
        expected = f"tex1_4x4_{xxhash.xxh64_hexdigest(pixels)}_{xxhash.xxh64_hexdigest(palette[:2])}_10"
        self.assertEqual(dolphin_name(pixels, 4, 4, 10, palette=palette), expected)


class TextureArchiveTests(unittest.TestCase):
    def test_pointer_owner_required_for_descriptor(self):
        body = bytearray(128)
        struct.pack_into(">IHHIIff", body, 0, 96, 8, 8, 0, 0, 0, 0)
        self.assertEqual(len(hsd_textures(parse_archive(archive(body, [0])))[0]), 1)
        self.assertEqual(
            hsd_textures(parse_archive(archive(body, [0], ((64, "other"),))))[0], []
        )

    def test_sprite_palette_and_unaligned_relocation(self):
        body = bytearray(160)
        struct.pack_into(">II", body, 0, 32, 56)
        struct.pack_into(">IHHIIff", body, 32, 96, 8, 8, 8, 0, 0, 0)
        struct.pack_into(">IIIH", body, 56, 128, 2, 0, 16)
        struct.pack_into(">I", body, 81, 96)
        images, warnings = hsd_textures(
            parse_archive(archive(body, [0, 4, 32, 56, 81]))
        )
        self.assertEqual(warnings, [])
        self.assertEqual(len(images), 1)
        self.assertEqual(images[0]["palette_offset"], 128)

    def test_archive_sequence_and_bad_bounds(self):
        single = archive(bytes(32), [])
        padded = single + bytes((-len(single)) % 32)
        self.assertEqual(len(archive_chunks(padded + single)), 2)
        with self.assertRaisesRegex(ValueError, "bounds"):
            parse_archive(single[:-1])

    def test_particle_relative_pointers_and_low_byte_palette_format(self):
        body = bytearray(160)
        struct.pack_into(">II", body, 0, 1, 32)
        struct.pack_into(">5IHHII", body, 32, 1, 8, 0x1000002, 8, 8, 1, 1, 96, 128)
        images, warnings = particle_textures(
            parse_archive(archive(body, [], ((0, "map_texg"),)))
        )
        self.assertEqual(warnings, [])
        self.assertEqual(len(images), 1)
        self.assertEqual(images[0]["image_offset"], 96)
        self.assertEqual(images[0]["palette_format"], 2)

    def test_extract_reports_failure_and_writes_unique_original_once(self):
        body = bytearray(128)
        struct.pack_into(">IHHIIff", body, 0, 96, 8, 8, 0, 0, 0, 0)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            files = root / "files"
            files.mkdir()
            for name in ("one.dat", "two.dat"):
                (files / name).write_bytes(archive(body, [0]))
            (files / "bad.dat").write_bytes(b"bad")
            manifest = extract_disc(files, root / "output")
            self.assertEqual(manifest["summary"]["unique_textures"], 1)
            self.assertEqual(len(manifest["textures"][0]["sources"]), 2)
            self.assertEqual(manifest["files"][0]["status"], "parse_error")
            self.assertEqual(len(list((root / "output/originals").glob("*.png"))), 1)

    def test_mip_chain_uses_each_padded_level(self):
        body = bytearray(192)
        struct.pack_into(">IHHIIff", body, 0, 96, 8, 8, 0, 1, 0, 2)
        body[96:128] = bytes([0x11]) * 32
        body[128:160] = bytes([0x22]) * 32
        body[160:192] = bytes([0x33]) * 32
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            files = root / "files"
            files.mkdir()
            (files / "mips.dat").write_bytes(archive(body, [0]))
            manifest = extract_disc(files, root / "output")
            self.assertEqual(manifest["warnings"], [])
            levels = manifest["textures"][0]["mip_levels"]
            self.assertEqual(
                [(i["width"], i["height"], i["encoded_offset"]) for i in levels],
                [(4, 4, 160), (2, 2, 192)],
            )
            from PIL import Image

            self.assertEqual(
                Image.open(root / "output" / levels[1]["path"]).getpixel((0, 0)),
                (51, 51, 51, 51),
            )


if __name__ == "__main__":
    unittest.main()
