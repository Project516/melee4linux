import pathlib
import shutil
import subprocess
import tempfile
import unittest


TEXTURES = pathlib.Path(__file__).resolve().parents[1] / "textures"


@unittest.skipUnless(shutil.which("c++"), "A C++ compiler is required")
class TexturePackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.directory = pathlib.Path(cls.temporary.name)
        source = cls.directory / "pack.cpp"
        source.write_text(
            r'''
#include "MeleeTexturePack.h"
#include <iostream>

int main(int argc, char** argv)
{
    if (argc == 2)
    {
        std::cout << MeleeTextures::CacheBudget(std::stoull(argv[1]));
        return 0;
    }
    const auto root = MeleeTextures::FindPackRoot(argv[1], argv[2]);
    if (root)
        std::cout << root->string();
}
'''
        )
        cls.executable = cls.directory / "pack"
        subprocess.run(
            ["c++", "-std=c++17", "-I", str(TEXTURES), str(source), "-o", str(cls.executable)],
            check=True,
        )

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def run_pack(self, *args):
        return subprocess.check_output([str(self.executable), *map(str, args)], text=True)

    def test_bundle_can_move_and_have_spaces(self):
        with tempfile.TemporaryDirectory() as directory:
            bundle = pathlib.Path(directory) / "Sharp Melee.app"
            pack = bundle / "Contents/Resources/Textures"
            (pack / "GALE01").mkdir(parents=True)
            self.assertEqual(self.run_pack("", bundle), str(pack))
            moved = bundle.with_name("Moved Melee.app")
            bundle.rename(moved)
            self.assertEqual(self.run_pack("", moved), str(moved / "Contents/Resources/Textures"))
            self.assertEqual(self.run_pack("", bundle), "")

    def test_explicit_path_takes_priority_without_fallback(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = pathlib.Path(directory)
            bundle = directory / "Melee.app"
            (bundle / "Contents/Resources/Textures/GALE01").mkdir(parents=True)
            explicit = directory / "comparison pack"
            (explicit / "GALE01").mkdir(parents=True)
            self.assertEqual(self.run_pack(explicit, bundle), str(explicit))
            self.assertEqual(self.run_pack(directory / "missing pack", bundle), "")
            self.assertEqual(self.run_pack(explicit / "GALE01", bundle), "")

    def test_game_id_must_be_a_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            (root / "GALE01").touch()
            self.assertEqual(self.run_pack(root, ""), "")
            self.assertEqual(self.run_pack("", ""), "")

    def test_cache_leaves_room_for_gpu_and_game(self):
        mib = 1024 * 1024
        self.assertEqual(int(self.run_pack(2 * 1024 * mib)), 256 * mib)
        self.assertEqual(int(self.run_pack(8 * 1024 * mib)), 512 * mib)
        self.assertEqual(int(self.run_pack(128 * 1024 * mib)), 512 * mib)
        self.assertEqual(int(self.run_pack(0)), 0)
