import importlib.util
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[3]


@unittest.skipUnless(shutil.which("c++"), "A C++ compiler is required")
class EndingDescriptorTests(unittest.TestCase):
    def test_only_the_live_ending_planes_match(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            source = directory / "ending.cpp"
            source.write_text(r'''
#include "MeleeEndingStills.h"
#include <array>
#include <cassert>

int main()
{
    std::array<unsigned char, 0xA0> descriptor{};
    const auto write = [&](unsigned int offset, std::uint32_t value) {
        for (int byte = 0; byte < 4; ++byte)
            descriptor[offset + byte] = value >> (24 - byte * 8);
    };
    write(0x20, 0x81000000);
    write(0x44, 0x81100000);
    write(0x68, 0x81200000);
    write(0x6C, (560 << 16) | 416);
    write(0x94, 0x81300000);
    write(0x98, 91948);
    const auto match = [&](auto address, auto width, auto height) {
        return MeleeTextures::MatchEndingPlane(descriptor, address, width, height);
    };
    const auto y = match(0x01000000, 560, 416);
    assert(y && y->channel == 'y' && y->source_address == 0x81300000);
    assert(y->source_size == 91948);
    assert(match(0x01100000, 280, 208)->channel == 'u');
    assert(match(0x01200000, 280, 208)->channel == 'v');
    assert(!match(0x01300000, 560, 416));
    assert(!match(0x01100000, 560, 416));
    assert(!match(0x01000000, 448, 336));
    assert(!MeleeTextures::MatchEndingPlane({}, 0x01000000, 560, 416));
    write(0x94, 0x817FFFF0);
    assert(!match(0x01000000, 560, 416));
    write(0x94, 0x81300000);
    write(0x98, 0xFFFFFFFF);
    assert(!match(0x01000000, 560, 416));
    write(0x98, 91948);
    write(0x6C, (448 << 16) | 336);
    assert(!match(0x01000000, 560, 416));
}
''')
            executable = directory / "ending"
            subprocess.run(["c++", "-std=c++20", "-I", str(ROOT / "native/macos/textures"), str(source), "-o", str(executable)], check=True)
            result = subprocess.run([str(executable)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)


HAS_IMAGES = all(importlib.util.find_spec(name) is not None for name in ("PIL", "numpy", "xxhash"))


@unittest.skipUnless(HAS_IMAGES, "Install texture upscale requirements for plane conversion tests")
class EndingPlaneTests(unittest.TestCase):
    def test_full_resolution_planes_keep_chroma_and_alpha(self):
        import numpy as np
        from PIL import Image
        from tools.texture_upscale.still_planes import make_planes

        rgb = np.random.default_rng(0).integers(0, 256, (97, 131, 3), dtype=np.uint8)
        planes = make_planes(Image.fromarray(rgb))
        self.assertEqual(set(planes), set("yuv"))
        channels = []
        for channel in "yuv":
            pixels = np.asarray(planes[channel])
            self.assertEqual(pixels.shape, (97, 131, 4))
            for index in range(1, 4):
                np.testing.assert_array_equal(pixels[:, :, 0], pixels[:, :, index])
            channels.append(pixels[:, :, 0])
        yuv = np.stack(channels, axis=2)
        recovered = np.asarray(Image.fromarray(yuv, mode="YCbCr").convert("RGB"))
        error = np.abs(rgb.astype(int) - recovered.astype(int))
        self.assertLessEqual(error.max(), 4)
        self.assertLess(error.mean(), 1.5)

    def test_writer_validates_source_and_dimensions(self):
        from PIL import Image
        from tools.texture_upscale.still_planes import write_still_planes

        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            source = directory / "GmRegendSimpleMario.thp"
            source.write_bytes(b"\xff\xd8\xff\xd9")
            image = directory / "image.png"
            Image.new("RGB", (10, 10)).save(image)
            with self.assertRaisesRegex(ValueError, "integer multiple"):
                write_still_planes(source, image, directory / "out")
            source.write_bytes(b"MTHP")
            with self.assertRaisesRegex(ValueError, "JPEG start"):
                write_still_planes(source, image, directory / "out")
