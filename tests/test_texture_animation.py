"""Texture palette pairing checks with synthetic HSD animation bytes."""

import struct
import unittest

from tools.texture_upscale.extract_animation import animation_pairs


def _integer(value):
    result = bytearray()
    while value >= 128:
        result.append((value & 127) | 128)
        value >>= 7
    result.append(value)
    return bytes(result)


def _stream(keys, encoding=128):
    count = len(keys) - 1
    result = bytearray([1 | (count & 7) << 4 | (128 if count >= 8 else 0)])
    if count >= 8:
        result.extend(_integer(count >> 3))
    for value, wait in keys:
        if encoding == 0:
            result.extend(struct.pack("<f", value))
        else:
            kind = encoding & 224
            size = 2 if kind in (32, 64) else 1
            result.extend(int(value * (1 << (encoding & 31))).to_bytes(
                size, "little", signed=kind in (32, 96)
            ))
        if wait is not None:
            result.extend(_integer(wait))
    return bytes(result)


def _archive(image, palette, image_encoding=128, palette_encoding=128, start=0):
    data = bytearray(192)
    struct.pack_into(">I", data, 24, 48)  # TexAnim.aobjdesc
    struct.pack_into(">I", data, 56, 80)  # AObjDesc.fobjdesc
    struct.pack_into(">IIf4BI", data, 80, 112, len(image), start,
                     1, image_encoding, 0, 0, 192)
    struct.pack_into(">IIf4BI", data, 112, 0, len(palette), 0,
                     10, palette_encoding, 0, 0, 192 + len(image))
    return data + image + palette


class TextureAnimationTests(unittest.TestCase):
    def test_packed_tracks_pair_indices_instead_of_cross_product(self):
        keys = [(i, 1) for i in range(20)] + [(19, None)]
        data = _archive(_stream(keys), _stream(keys, 65), palette_encoding=65)
        self.assertEqual(animation_pairs(data, 16, 20, 20), [(i, i) for i in range(20)])

    def test_independent_changes_and_final_held_palette(self):
        image = _stream([(0, 2), (1, 2), (2, 2), (2, None)])
        palette = _stream([(0, 3), (1, 1), (1, None)])
        self.assertEqual(animation_pairs(_archive(image, palette), 16, 3, 2),
                         [(0, 0), (1, 0), (1, 1), (2, 1)])

    def test_float_indices_truncate_and_start_frame_seeks(self):
        image = _stream([(0.9, 1), (1.9, 1), (2.9, 1), (2.9, None)], 0)
        palette = _stream([(0, 1), (1, 1), (1, None)])
        data = _archive(image, palette, image_encoding=0, start=1.9)
        self.assertEqual(animation_pairs(data, 16, 3, 2), [(1, 0), (2, 1)])

    def test_zero_wait_uses_last_value_at_shared_timestamp(self):
        image = _stream([(0, 0), (1, 200), (1, None)])
        palette = _stream([(0, 200), (1, 0), (1, None)])
        self.assertEqual(animation_pairs(_archive(image, palette), 16, 2, 2),
                         [(1, 0), (1, 1)])

    def test_unknown_or_missing_tracks_do_not_guess(self):
        stream = _stream([(0, 1), (1, None)])
        data = _archive(stream, stream)
        data[124] = 2
        self.assertIsNone(animation_pairs(data, 16, 2, 2))
        data = _archive(bytes([stream[0] + 1]) + stream[1:], stream)
        self.assertIsNone(animation_pairs(data, 16, 2, 2))

    def test_bad_bounds_cycles_and_indices_fail_closed(self):
        stream = _stream([(0, 1), (1, None)])
        data = _archive(stream, stream)
        self.assertIsNone(animation_pairs(data[:-1], 16, 2, 2))
        self.assertIsNone(animation_pairs(data, 16, 1, 2))
        self.assertIsNone(animation_pairs(data, -1, 2, 2))
        struct.pack_into(">I", data, 112, 80)
        self.assertIsNone(animation_pairs(data, 16, 2, 2))

    def test_truncated_packed_integer_and_nonfinite_value(self):
        valid = _stream([(0, 1), (1, None)])
        self.assertIsNone(animation_pairs(_archive(b"\x81\x80", valid), 16, 2, 2))
        invalid = _stream([(float("nan"), 1), (1, None)], 0)
        self.assertIsNone(animation_pairs(
            _archive(invalid, valid, image_encoding=0), 16, 2, 2
        ))


if __name__ == "__main__":
    unittest.main()
