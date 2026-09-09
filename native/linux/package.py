#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Assemble the Melee for Linux AppDir and AppImage from a built runtime.

The AppImage holds the runtime, launcher, disc translator, module build
tools, and their licenses. It never holds game data or a compiled game
module. The launcher imports the user's own disc on first use.
"""

from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import platform
import re
import shutil
import stat
import struct
import subprocess
import tarfile
import tempfile
import urllib.request
import zipfile
import zlib


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
APP_NAME = "Melee for Linux"
DESKTOP_ID = "melee4linux"
ZIG_VERSION = "0.15.2"
PYTHON_VERSION = "3.12.14+20260901"
NINJA_VERSION = "1.13.2"
# Pinned downloads with the publisher's SHA-256. Change these together.
DOWNLOADS = {
    "aarch64": {
        "zig": (f"https://ziglang.org/download/{ZIG_VERSION}/zig-aarch64-linux-{ZIG_VERSION}.tar.xz",
                "958ed7d1e00d0ea76590d27666efbf7a932281b3d7ba0c6b01b0ff26498f667f"),
        "ninja": (f"https://github.com/ninja-build/ninja/releases/download/v{NINJA_VERSION}/ninja-linux-aarch64.zip",
                  "fd2cacc8050a7f12a16a2e48f9e06fca5c14fc4c2bee2babb67b58be17a607fc"),
        "python": ("https://github.com/astral-sh/python-build-standalone/releases/download/20260901/"
                   "cpython-3.12.14%2B20260901-aarch64-unknown-linux-gnu-install_only_stripped.tar.gz",
                   "577b4bec0793ad1ff0cbff9adbd0df078eddde38a4c41bf5d83ad381a85ee39d"),
        "appimagetool": ("https://github.com/AppImage/appimagetool/releases/download/1.9.1/appimagetool-aarch64.AppImage",
                         "f0837e7448a0c1e4e650a93bb3e85802546e60654ef287576f46c71c126a9158"),
        "appimage-runtime": ("https://github.com/AppImage/type2-runtime/releases/download/20251108/runtime-aarch64",
                             "00cbdfcf917cc6c0ff6d3347d59e0ca1f7f45a6df1a428a0d6d8a78664d87444"),
    },
    "x86_64": {
        "zig": (f"https://ziglang.org/download/{ZIG_VERSION}/zig-x86_64-linux-{ZIG_VERSION}.tar.xz",
                "02aa270f183da276e5b5920b1dac44a63f1a49e55050ebde3aecc9eb82f93239"),
        "ninja": (f"https://github.com/ninja-build/ninja/releases/download/v{NINJA_VERSION}/ninja-linux.zip",
                  "5749cbc4e668273514150a80e387a957f933c6ed3f5f11e03fb30955e2bbead6"),
        "python": ("https://github.com/astral-sh/python-build-standalone/releases/download/20260901/"
                   "cpython-3.12.14%2B20260901-x86_64-unknown-linux-gnu-install_only_stripped.tar.gz",
                   "72748da13197c1fb161e3afeef20a6a385ff24f2165e6e2758e47008e7faba4c"),
        "appimagetool": ("https://github.com/AppImage/appimagetool/releases/download/1.9.1/appimagetool-x86_64.AppImage",
                         "ed4ce84f0d9caff66f50bcca6ff6f35aae54ce8135408b3fa33abfc3cb384eb0"),
        "appimage-runtime": ("https://github.com/AppImage/type2-runtime/releases/download/20251108/runtime-x86_64",
                             "2fca8b443c92510f1483a883f60061ad09b46b978b2631c807cd873a47ec260d"),
    },
}
# Libraries every desktop Linux supplies, or that must match the host's
# graphics driver. Everything else the binaries link is copied into usr/lib.
EXCLUDED_LIBRARIES = re.compile(
    r"^(ld-linux.*|linux-vdso.*|libc\.so.*|libm\.so.*|libdl\.so.*|libpthread\.so.*|librt\.so.*"
    r"|libresolv\.so.*|libutil\.so.*|libnsl\.so.*|libanl\.so.*|libgcc_s\.so.*|libstdc\+\+\.so.*"
    r"|libGL\.so.*|libGLX.*|libGLdispatch.*|libOpenGL.*|libEGL.*|libGLESv.*|libdrm.*|libgbm.*"
    r"|libglapi.*|libvulkan.*|libX11.*|libxcb.*|libXau.*|libXdmcp.*|libXext.*|libXrender.*"
    r"|libXfixes.*|libasound.*|libz\.so.*|libexpat.*|libfontconfig.*|libfreetype.*|libharfbuzz.*"
    r"|libuuid.*|libcom_err.*|libcrypt\.so.*|libgpg-error.*|libusb-1\.0.*|libudev.*|libsystemd.*"
    r"|libbsd.*|libmd\.so.*|libselinux.*|libpcre.*|libffi.*|libgio.*|libglib.*|libgobject.*"
    r"|libgmodule.*|libp11-kit.*|libICE.*|libSM.*|libcap.*|libdbus.*)$"
)
GX_CPU_SOURCES = ("cpu.c", "cpu_exception.c", "cpu_interpreter.c", "cpu_interpreter_table.c",
                  "cpu_interpreter_float.c", "cpu_interpreter_integer.c")


class PackageError(Exception):
    """A build input, download, or output is not usable."""


def run(*args: str | Path, env: dict | None = None) -> str:
    result = subprocess.run([str(arg) for arg in args], capture_output=True, text=True, env=env)
    if result.returncode:
        raise PackageError(f"{args[0]} failed:\n{result.stderr or result.stdout}")
    return result.stdout


def host_arch() -> str:
    machine = platform.machine()
    if machine in ("aarch64", "arm64"):
        return "aarch64"
    if machine in ("x86_64", "amd64"):
        return "x86_64"
    raise PackageError(f"Unsupported CPU architecture: {machine}")


def sha256(path: Path) -> str:
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def fetch(url: str, digest: str, downloads: Path) -> Path:
    """Download once into the cache and verify the pinned hash every time."""
    downloads.mkdir(parents=True, exist_ok=True)
    target = downloads / urllib.request.unquote(url.rsplit("/", 1)[1])
    if not target.is_file():
        print(f"+ fetch {url}", flush=True)
        temporary = target.with_name(target.name + ".partial")
        with urllib.request.urlopen(url, timeout=120) as response, temporary.open("wb") as output:
            shutil.copyfileobj(response, output)
        temporary.replace(target)
    actual = sha256(target)
    if actual != digest:
        target.unlink()
        raise PackageError(f"Checksum mismatch for {url}: {actual}")
    return target


def dependencies(binary: Path) -> list[Path]:
    """Resolved shared libraries the dynamic loader would load for this binary."""
    output = run("ldd", binary)
    if "not a dynamic executable" in output:
        return []
    found = []
    for line in output.splitlines():
        match = re.match(r"\s*(\S+) => (\S+) \(0x[0-9a-f]+\)", line)
        if match is None:
            if "not found" in line:
                raise PackageError(f"Unresolved library for {binary}: {line.strip()}")
            continue
        name, path = match.groups()
        if EXCLUDED_LIBRARIES.match(Path(name).name):
            continue
        found.append(Path(path))
    return found


def bundle_libraries(binaries: list[Path], library_dir: Path) -> list[Path]:
    """Copy non-system dependencies and point every image at usr/lib."""
    library_dir.mkdir(parents=True, exist_ok=True)
    copied: dict[str, Path] = {}
    for binary in binaries:
        for dependency in dependencies(binary):
            name = dependency.name
            source = dependency.resolve()
            if name in copied:
                if copied[name] != source:
                    raise PackageError(f"Two libraries have the same bundle name: {name}")
                continue
            destination = library_dir / name
            shutil.copy2(source, destination)
            destination.chmod(destination.stat().st_mode | stat.S_IWUSR)
            copied[name] = source
        relative = os.path.relpath(library_dir, binary.parent)
        run("patchelf", "--set-rpath", f"$ORIGIN/{relative}", binary)
    for library in library_dir.iterdir():
        run("patchelf", "--set-rpath", "$ORIGIN", library)
    return sorted(library_dir.iterdir())


def write_png(path: Path, size: int = 256, color: tuple[int, int, int] = (26, 32, 52)) -> None:
    """A flat placeholder icon. Real artwork belongs beside the packager, not in Git."""
    row = b"\0" + bytes(color) * size
    raw = row * size

    def chunk(kind: bytes, data: bytes) -> bytes:
        body = kind + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)

    header = struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0)
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) +
                     chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


def validate_inputs(root: Path) -> None:
    for relative in (
        "build/runtime/MeleeRuntime", "build/runtime/MeleeLauncher", "build/dolrecomp/dolrecomp",
        "build/runtime/melee-build-id.txt", "LICENSE", "CREDITS.md",
        "upstream/ModernGekko-Template/lib/ModernGekko/vendor/dolphin/module-template/module_export.c",
        "upstream/ModernGekko-Template/lib/ModernGekko/vendor/dolphin/module-template/module.exports",
        "upstream/ModernGekko-Template/lib/ModernGekko/vendor/dolphin/module-template/gen_module_tables.py",
        "upstream/ModernGekko-Template/lib/ModernGekko/vendor/dolphin/GXRuntime/include/core/cpu.h",
        "upstream/ModernGekko-Template/lib/ModernGekko/vendor/dolphin/Source/Core/Core/PowerPC/StaticRecomp/StaticRecompABI.h",
    ):
        path = root / relative
        if not path.is_file() or path.stat().st_size == 0:
            raise PackageError(f"Missing or empty build input: {path}")
    sys_dir = root / "build/runtime/Sys"
    if not sys_dir.is_dir() or next(sys_dir.iterdir(), None) is None:
        raise PackageError(f"Missing or empty resource directory: {sys_dir}")
    for name in ("import_game.py", "AppRun", "melee-import-game", f"{DESKTOP_ID}.desktop"):
        if not (HERE / name).is_file():
            raise PackageError(f"Missing packager input: {HERE / name}")
    for relative in ("recompile_boot.py", "high_refresh.py", "refresh/MeleeHighRefresh.h"):
        if not (HERE.parent / "macos" / relative).is_file():
            raise PackageError(f"Missing shared tool: {HERE.parent / 'macos' / relative}")


def validate_output(output: Path, replace: bool, appdir: bool) -> None:
    if appdir:
        if output.suffix != ".AppDir":
            raise PackageError("The AppDir output path must end in .AppDir.")
    elif output.suffix != ".AppImage":
        raise PackageError("The output path must end in .AppImage.")
    if output.is_symlink():
        raise PackageError("The output must not be a symbolic link.")
    if output.exists() and not replace:
        raise PackageError(f"The output already exists: {output}. Use --replace to rebuild it.")


def validate_texture_pack(path: Path) -> Path:
    path = path.expanduser().resolve()
    game = path / "GALE01"
    if game.is_symlink():
        raise PackageError("Texture packs must contain real files, not symbolic links.")
    if not game.is_dir() or not any(game.glob("**/*.dds")):
        raise PackageError("The texture pack must contain GALE01 with DDS textures.")
    for item in game.rglob("*"):
        if item.is_symlink():
            raise PackageError("Texture packs must contain real files, not symbolic links.")
    return path


def extract_zig(archive: Path, destination: Path) -> None:
    with tarfile.open(archive) as tar:
        members = tar.getmembers()
        top = members[0].name.split("/", 1)[0]
        wanted = [m for m in members if m.name.split("/", 1)[0] == top and
                  (m.name == f"{top}/zig" or m.name == f"{top}/LICENSE" or m.name.startswith(f"{top}/lib/"))]
        tar.extractall(destination.parent / "zig.extract", members=wanted, filter="data")
    (destination.parent / "zig.extract" / top).rename(destination)
    (destination.parent / "zig.extract").rmdir()
    if not (destination / "zig").is_file():
        raise PackageError("The zig archive did not contain the compiler.")


def extract_python(archive: Path, destination: Path) -> None:
    with tarfile.open(archive) as tar:
        tar.extractall(destination.parent / "python.extract", filter="data")
    (destination.parent / "python.extract" / "python").rename(destination)
    (destination.parent / "python.extract").rmdir()
    if not (destination / "bin/python3").exists():
        raise PackageError("The Python archive did not contain bin/python3.")
    # Tests and headers are not used by the module builder.
    for relative in ("include", "lib/python3.12/test", "lib/python3.12/idlelib", "lib/python3.12/tkinter"):
        shutil.rmtree(destination / relative, ignore_errors=True)


def extract_ninja(archive: Path, destination: Path) -> None:
    with zipfile.ZipFile(archive) as archive_file:
        destination.write_bytes(archive_file.read("ninja"))
    destination.chmod(0o755)


def assemble(root: Path, appdir: Path, downloads: Path, arch: str, texture_pack: Path | None) -> None:
    pins = DOWNLOADS[arch]
    binaries = appdir / "usr/bin"
    share = appdir / "usr/share/melee"
    for directory in (binaries, share / "tools/refresh", share / "module/gxruntime/src/core",
                      share / "module/staticrecomp", share / "licenses",
                      appdir / "usr/share/applications", appdir / "usr/share/icons/hicolor/256x256/apps"):
        directory.mkdir(parents=True)
    executables = []
    for source, name in (("build/runtime/MeleeRuntime", "MeleeRuntime"),
                         ("build/runtime/MeleeLauncher", "MeleeLauncher"),
                         ("build/dolrecomp/dolrecomp", "dolrecomp")):
        target = binaries / name
        shutil.copy2(root / source, target)
        target.chmod(0o755)
        executables.append(target)
    if shutil.which("strip"):
        run("strip", "--strip-unneeded", *executables)
    shutil.copytree(root / "build/runtime/Sys", binaries / "Sys")
    for name in ("melee-import-game",):
        shutil.copy2(HERE / name, binaries / name)
        (binaries / name).chmod(0o755)
    bundle_libraries(executables, appdir / "usr/lib")

    shutil.copy2(HERE / "AppRun", appdir / "AppRun")
    (appdir / "AppRun").chmod(0o755)
    shutil.copy2(HERE / f"{DESKTOP_ID}.desktop", appdir / f"{DESKTOP_ID}.desktop")
    shutil.copy2(HERE / f"{DESKTOP_ID}.desktop", appdir / f"usr/share/applications/{DESKTOP_ID}.desktop")
    icon = appdir / f"{DESKTOP_ID}.png"
    write_png(icon)
    shutil.copy2(icon, appdir / f"usr/share/icons/hicolor/256x256/apps/{DESKTOP_ID}.png")
    (appdir / ".DirIcon").symlink_to(f"{DESKTOP_ID}.png")

    shutil.copy2(root / "build/runtime/melee-build-id.txt", share / "build-id.txt")
    shutil.copy2(HERE / "import_game.py", share / "tools/import_game.py")
    macos = HERE.parent / "macos"
    for relative in ("recompile_boot.py", "high_refresh.py", "refresh/MeleeHighRefresh.h"):
        shutil.copy2(macos / relative, share / "tools" / relative)
    dolphin = root / "upstream/ModernGekko-Template/lib/ModernGekko/vendor/dolphin"
    for name in ("module_export.c", "module.exports", "gen_module_tables.py"):
        shutil.copy2(dolphin / "module-template" / name, share / "module" / name)
    shutil.copytree(dolphin / "GXRuntime/include", share / "module/gxruntime/include")
    for name in GX_CPU_SOURCES:
        shutil.copy2(dolphin / "GXRuntime/src/core" / name, share / "module/gxruntime/src/core" / name)
    for header in (dolphin / "Source/Core/Core/PowerPC/StaticRecomp").glob("*.h"):
        shutil.copy2(header, share / "module/staticrecomp" / header.name)
    if texture_pack is not None:
        shutil.copytree(texture_pack / "GALE01", share / "Textures/GALE01")

    extract_zig(fetch(*pins["zig"], downloads), share / "zig")
    extract_python(fetch(*pins["python"], downloads), share / "python")
    extract_ninja(fetch(*pins["ninja"], downloads), share / "ninja")

    readme = (HERE / "README.md").read_text().replace(
        "../../docs/native-linux.md",
        "https://github.com/Project516/melee4linux/blob/master/docs/native-linux.md")
    (share / "README.md").write_text(readme)
    licenses = share / "licenses"
    for source, name in (
        (root / "LICENSE", "melee-macos-recomp-LICENSE"),
        (root / "CREDITS.md", "melee-macos-recomp-CREDITS.md"),
        (root / "upstream/ModernGekko-Template/lib/ModernGekko/LICENSE", "ModernGekko-LICENSE"),
        (dolphin / "COPYING", "Dolphin-COPYING"),
        (dolphin / "GXRuntime/LICENSE", "GXRuntime-LICENSE"),
        (root / "upstream/ModernGekko-Template/lib/DolRecomp/LICENSE", "DolRecomp-LICENSE"),
        (share / "zig/LICENSE", "zig-LICENSE"),
        (share / "python/lib/python3.12/LICENSE.txt", "Python-LICENSE.txt"),
    ):
        if source.is_file():
            shutil.copy2(source, licenses / name)
    (licenses / "ninja-LICENSE").write_text(
        f"Ninja {NINJA_VERSION} is distributed under the Apache License 2.0.\n"
        "https://github.com/ninja-build/ninja/blob/master/COPYING\n")


def make_appimage(appdir: Path, output: Path, downloads: Path, arch: str) -> None:
    pins = DOWNLOADS[arch]
    tool = fetch(*pins["appimagetool"], downloads)
    tool.chmod(tool.stat().st_mode | stat.S_IXUSR)
    runtime = fetch(*pins["appimage-runtime"], downloads)
    env = {**os.environ, "ARCH": arch}
    run(tool, "--appimage-extract-and-run", "--no-appstream", "--comp", "zstd",
        "--runtime-file", runtime, appdir, output, env=env)
    if not output.is_file():
        raise PackageError(f"appimagetool produced no output at {output}")
    output.chmod(0o755)


def package(root: Path, output: Path, replace: bool = False, texture_pack: Path | None = None,
            downloads: Path | None = None, appdir_only: bool = False, arch: str | None = None) -> Path:
    root = root.expanduser().resolve()
    output = output.expanduser().absolute()
    output = output.parent.resolve() / output.name
    arch = arch or host_arch()
    if arch not in DOWNLOADS:
        raise PackageError(f"No pinned tools for {arch}.")
    downloads = (downloads or root / "downloads").expanduser().resolve()
    validate_inputs(root)
    if texture_pack is not None:
        texture_pack = validate_texture_pack(texture_pack)
    validate_output(output, replace, appdir_only)
    for tool in ("ldd", "patchelf"):
        if shutil.which(tool) is None:
            raise PackageError(f"Missing {tool}. See docs/native-linux.md for build dependencies.")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".melee-package-", dir=output.parent) as temporary:
        staged = Path(temporary) / f"{DESKTOP_ID}.AppDir"
        staged.mkdir()
        assemble(root, staged, downloads, arch, texture_pack)
        if appdir_only:
            result = staged
        else:
            result = Path(temporary) / output.name
            make_appimage(staged, result, downloads, arch)
        backup = Path(temporary) / "previous"
        if output.exists():
            output.rename(backup)
        try:
            result.rename(output)
        except OSError:
            if backup.exists():
                backup.rename(output)
            raise
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-dir", type=Path, required=True, help="Built melee-macos-recomp checkout")
    parser.add_argument("--output", type=Path, required=True, help="Output .AppImage, or .AppDir with --appdir-only")
    parser.add_argument("--replace", action="store_true", help="Replace an earlier output")
    parser.add_argument("--texture-pack", type=Path, help="Replacement texture root containing GALE01")
    parser.add_argument("--downloads", type=Path, help="Cache for pinned tool downloads")
    parser.add_argument("--appdir-only", action="store_true", help="Stop after assembling the AppDir")
    parser.add_argument("--arch", choices=sorted(DOWNLOADS), help="Target architecture (default: host)")
    options = parser.parse_args()
    try:
        result = package(options.runtime_dir, options.output, options.replace, options.texture_pack,
                         options.downloads, options.appdir_only, options.arch)
    except (PackageError, OSError) as error:
        parser.exit(1, f"Packaging failed: {error}\n")
    print(f"Output: {result}\nIt contains no game data. The launcher imports your own disc.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
