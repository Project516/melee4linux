"""Compare extracted pixels and names with the native runtime's Dolphin objects.

This check links the actual TextureInfo and texture decoder object files. It
does not implement a second decoder. Its diagnostic stubs abort on any Dolphin
error. Build the native macOS runtime first, then supply its build directory,
the vendored Dolphin directory, the extracted disc root and a texture manifest.
All generated files stay in the chosen output directory.
"""

import argparse
import hashlib
import json
import random
import shlex
import subprocess
from collections import Counter
from pathlib import Path

from PIL import Image

from .texture_formats import texture_size

_ORACLE = r"""
#include <cstdlib>
#include <fstream>
#include <iostream>
#include <iterator>
#include <vector>
#include "VideoCommon/TextureDecoder.h"
#include "VideoCommon/TextureInfo.h"
#include "Common/Logging/Log.h"
#include "Common/MsgHandler.h"

void _TexDecoder_DecodeImpl(u32*, const u8*, int, int, TextureFormat,
                            const u8*, TLUTFormat);

namespace Common {
bool MsgAlertFmtImpl(bool, MsgType, Log::LogType, const char*, int,
                        fmt::string_view, const fmt::format_args&) {
    std::abort();
}
}

namespace Common::Log {
void GenericLogFmtImpl(LogLevel, LogType, const char*, int,
                        fmt::string_view message, const fmt::format_args&) {
    std::cerr << "Dolphin error: " << std::string(message.data(), message.size())
            << std::endl;
    std::abort();
}
}

std::vector<u8> Read(const char* path) {
    std::ifstream file(path, std::ios::binary);
    return {std::istreambuf_iterator<char>(file), {}};
}

int main(int argc, char** argv) {
    if (argc != 9) return 2;
    auto pixels = Read(argv[1]);
    auto palette = Read(argv[2]);
    const int width = std::stoi(argv[3]), height = std::stoi(argv[4]);
    const auto format = static_cast<TextureFormat>(std::stoi(argv[5]));
    const auto palette_format = static_cast<TLUTFormat>(std::stoi(argv[6]));
    const auto mips = std::stoi(argv[7]) ? std::optional<u32>(1) : std::nullopt;
    TextureInfo info(0, pixels, palette, 0, format, palette_format,
                    width, height, false, {}, {}, mips);
    if (!info.IsDataValid()) return 3;
    std::cout << info.CalculateTextureName().GetFullName() << std::endl;
    const auto expanded_width = info.GetExpandedWidth();
    std::vector<u32> output(expanded_width * info.GetExpandedHeight());
    _TexDecoder_DecodeImpl(output.data(), pixels.data(), expanded_width,
                            info.GetExpandedHeight(), format,
                            palette.data(), palette_format);
    std::ofstream file(argv[8], std::ios::binary);
    for (int y = 0; y < height; y++)
    file.write(reinterpret_cast<char*>(output.data() + y * expanded_width),
                width * 4);
    return 0;
}
"""


def build_oracle(dolphin: Path, runtime: Path, output: Path) -> tuple[Path, dict]:
    output.mkdir(parents=True, exist_ok=True)
    source = output / "oracle.cpp"
    source.write_text(_ORACLE)
    objects = (
        runtime / "vendor/dolphin/Source/Core/VideoCommon/CMakeFiles/videocommon.dir"
    )
    paths = [
        objects / f"{name}.cpp.o"
        for name in ("TextureDecoder_Generic", "TextureDecoder_Common", "TextureInfo")
    ]
    paths.append(runtime / "vendor/dolphin/Externals/xxhash/libxxhash.a")
    for path in paths:
        if not path.is_file():
            raise ValueError(f"Missing native runtime object: {path}")
    fmt_flags = shlex.split(
        subprocess.run(
            ["pkg-config", "--cflags", "--libs", "fmt"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
    )
    executable = output / "oracle"
    subprocess.run(
        [
            "clang++",
            "-std=c++23",
            "-O2",
            "-DNDEBUG",
            "-Wl,-dead_strip",
            "-I" + str(dolphin / "Source/Core"),
            str(source),
            *map(str, paths),
            *fmt_flags,
            "-o",
            str(executable),
        ],
        check=True,
    )
    hashes = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in paths
    }
    return executable, hashes


def select_textures(textures: list[dict], count: int, seed: int) -> list[dict]:
    selected = random.Random(seed).sample(textures, min(count, len(textures)))
    for fmt in sorted({item["format"] for item in textures}):
        if fmt not in {item["format"] for item in selected}:
            selected.append(next(item for item in textures if item["format"] == fmt))
    for predicate in (
        lambda item: item["mipmap"],
        lambda item: item["width"] % 8 != 0,
        lambda item: (
            item["format"] == 8
            and any(
                source.get("palette_entries", 16) < 16 for source in item["sources"]
            )
        ),
    ):
        extra = next((item for item in textures if predicate(item)), None)
        if extra is not None and extra not in selected:
            selected.append(extra)
    return selected


def verify(
    manifest_path: Path,
    disc: Path,
    dolphin: Path,
    runtime: Path,
    output: Path,
    count: int = 50,
    seed: int = 120,
) -> dict:
    manifest = json.loads(manifest_path.read_text())
    selected = select_textures(manifest["textures"], count, seed)
    executable, hashes = build_oracle(dolphin, runtime, output)
    checks = []
    raw_cache = {}
    for item in selected:
        source = item["sources"][0]
        relative = source["file"]
        path = (
            disc / relative
            if relative.startswith("sys/")
            else disc / "files" / relative
        )
        if path not in raw_cache:
            raw_cache[path] = path.read_bytes()
        raw = raw_cache[path]
        width, height, fmt = item["width"], item["height"], item["format"]
        offset = source["image_offset"]
        encoded = raw[offset : offset + texture_size(width, height, fmt)]
        palette = bytes(32768)
        if "palette_offset" in source:
            start = source["palette_offset"]
            length = {8: 32, 9: 512, 10: 32768}[fmt]
            # TextureInfo requires a full palette span, even if the final
            # archive block ends sooner. Only used entries affect the name.
            palette = raw[start : start + length].ljust(length, b"\0")
        palette_path = output / "palette.bin"
        input_path = output / "input.bin"
        result_path = output / "result.rgba"
        palette_path.write_bytes(palette)
        levels = [
            {
                "level": 0,
                "width": width,
                "height": height,
                "path": item["path"],
                "encoded": encoded,
            }
        ]
        for mip in item.get("mip_levels", []):
            levels.append(
                mip
                | {
                    "encoded": raw[
                        mip["encoded_offset"] : mip["encoded_offset"]
                        + mip["encoded_size"]
                    ]
                }
            )
        for level in levels:
            input_path.write_bytes(level["encoded"])
            result = subprocess.run(
                [
                    str(executable),
                    str(input_path),
                    str(palette_path),
                    str(level["width"]),
                    str(level["height"]),
                    str(fmt),
                    str(source.get("palette_format", 2)),
                    str(int(item["mipmap"] and level["level"] == 0)),
                    str(result_path),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            if level["level"] == 0 and result.stdout.strip() != item["name"]:
                raise ValueError(
                    f"Dolphin name differs for {item['name']}: {result.stdout.strip()}"
                )
            with Image.open(manifest_path.parent / level["path"]) as image:
                expected = image.convert("RGBA").tobytes()
            actual = result_path.read_bytes()
            if actual != expected:
                differing = sum(
                    first != second for first, second in zip(actual, expected)
                )
                raise ValueError(
                    f"Dolphin pixels differ for {item['name']} mip {level['level']}: {differing} bytes"
                )
            checks.append(
                {
                    "name": item["name"],
                    "level": level["level"],
                    "format": fmt,
                    "rgba_sha256": hashlib.sha256(actual).hexdigest(),
                }
            )
    report = {
        "schema_version": 1,
        "passed": True,
        "seed": seed,
        "random_count": count,
        "textures": len(selected),
        "mip_levels": sum(check["level"] != 0 for check in checks),
        "formats": dict(Counter(item["format_name"] for item in selected)),
        "oracle_objects": hashes,
        "manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        "checks": checks,
    }
    (output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for option in ("manifest", "disc", "dolphin", "runtime", "output"):
        parser.add_argument("--" + option, type=Path, required=True)
    parser.add_argument("--count", type=int, default=50)
    parser.add_argument("--seed", type=int, default=120)
    args = parser.parse_args()
    report = verify(
        args.manifest.resolve(),
        args.disc.resolve(),
        args.dolphin.resolve(),
        args.runtime.resolve(),
        args.output.resolve(),
        args.count,
        args.seed,
    )
    print(
        json.dumps(
            {
                key: value
                for key, value in report.items()
                if key not in ("checks", "oracle_objects")
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
