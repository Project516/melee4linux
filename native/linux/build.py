#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Build Melee for Linux: pinned runtime, fork patches, and an AppImage.

Without --iso this needs no game data and produces the distributable
AppImage. With --iso it also imports that disc into a local user directory
and compiles the native module, using the same tools the AppImage carries.
"""

import argparse
import hashlib
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
MACOS = HERE.parent / "macos"
RUNTIME_URL = "https://github.com/McDandle/melee-macos-recomp.git"
RUNTIME_REV = "39e30dec9fa7d90fba960ca9189b573a7938e3df"
TEMPLATE_URL = "https://github.com/ExpansionPak/ModernGekko-Template.git"
TEMPLATE_REV = "eedda2b02dde3aefc02796d859f0033b916aad03"
APP_NAME = "Melee for Linux"


def run(*args, cwd=ROOT, env=None):
    print("+ " + " ".join(map(str, args)), flush=True)
    subprocess.run(list(map(str, args)), cwd=cwd, env=env, check=True)


def patch_state(checkout, patch, reverse=False):
    args = ["git", "apply", "--check"]
    if reverse:
        args.append("--reverse")
    return subprocess.run([*args, str(patch)], cwd=checkout, capture_output=True).returncode == 0


def apply_patch(checkout, patch):
    if patch_state(checkout, patch, reverse=True):
        return
    if not patch_state(checkout, patch):
        raise RuntimeError(f"Local changes conflict with {patch.name} in {checkout}")
    run("git", "apply", patch, cwd=checkout)


def remove_patch(checkout, patch):
    if not checkout.is_dir() or not patch.exists():
        return
    if patch_state(checkout, patch, reverse=True):
        run("git", "apply", "--reverse", patch, cwd=checkout)


def patch_plan(runtime):
    """Every patch in application order. Mac-only frontend patches are left out."""
    template = runtime / "upstream/ModernGekko-Template"
    gekko = template / "lib/ModernGekko"
    dolphin = gekko / "vendor/dolphin"
    upstream = runtime / "patches"
    mac = MACOS / "patches"
    linux = HERE / "patches"
    return [
        (dolphin, upstream / "strict-native.patch"),
        (gekko, upstream / "cpu-abi.patch"),
        (template / "lib/DolRecomp", upstream / "native-spr-codegen.patch"),
        (gekko, upstream / "netplay.patch"),
        (gekko, upstream / "media-settings.patch"),
        (gekko, mac / "runtime-sdl.patch"),
        (gekko, mac / "runtime-cache.patch"),
        (gekko, mac / "startup-inspection.patch"),
        (gekko, mac / "benchmark-automation.patch"),
        (dolphin, mac / "strict-cpu.patch"),
        (dolphin, mac / "native-boot.patch"),
        (dolphin, mac / "disc-transfer.patch"),
        (dolphin, mac / "low-latency-input.patch"),
        (dolphin, mac / "native-timebase.patch"),
        (dolphin, mac / "native-idle.patch"),
        (dolphin, mac / "frame-timing.patch"),
        (dolphin, mac / "fluid-render.patch"),
        (dolphin, mac / "benchmark-state.patch"),
        (dolphin, mac / "game-refresh.patch"),
        (dolphin, mac / "texture-cache.patch"),
        (dolphin, mac / "ending-stills.patch"),
        (gekko, linux / "linux-runtime.patch"),
        (gekko, linux / "linux-launcher.patch"),
        (dolphin, linux / "vulkan-present.patch"),
    ]


def copied_sources(runtime):
    """Fork sources placed into the pinned trees. Metal and AppKit files stay out."""
    gekko = runtime / "upstream/ModernGekko-Template/lib/ModernGekko"
    video = gekko / "vendor/dolphin/Source/Core/VideoCommon"
    return [
        (MACOS / "render/MeleeRenderConfig.h", video),
        (MACOS / "textures/MeleeTexturePack.h", video),
        (MACOS / "textures/MeleeEndingStills.h", video),
        (HERE / "runtime/MeleeLinuxPreferences.cpp", gekko / "src/runtime"),
    ]


def build_identity(runtime):
    """Changes here make installed native modules rebuild on the next launch."""
    digest = hashlib.sha256()
    for _, patch in patch_plan(runtime):
        digest.update(patch.name.encode() + b"\0" + patch.read_bytes())
    for source, _ in copied_sources(runtime):
        digest.update(source.name.encode() + b"\0" + source.read_bytes())
    for name in (
            "import_game.py", "../macos/recompile_boot.py", "../macos/high_refresh.py",
            "../macos/refresh/MeleeHighRefresh.h"):
        digest.update((HERE / name).read_bytes())
    fork = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True)
    revision = fork.stdout.strip() if fork.returncode == 0 else "unknown"
    return (f"melee4linux={revision}\nruntime={RUNTIME_REV}\ntemplate={TEMPLATE_REV}\n"
            f"sources={digest.hexdigest()}\narch={platform.machine()}\n")


def cmake_flags(ccache):
    flags = [
        "-G", "Ninja", "-DCMAKE_BUILD_TYPE=Release", "-DBUILD_TESTING=OFF",
        "-DDOLRECOMP_ENABLE_LLVM=OFF",
        # The AppImage runs on hosts with older C++ runtimes.
        "-DCMAKE_EXE_LINKER_FLAGS=-static-libstdc++ -static-libgcc"]
    if ccache:
        flags += ["-DCMAKE_C_COMPILER_LAUNCHER=ccache", "-DCMAKE_CXX_COMPILER_LAUNCHER=ccache"]
    return flags


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iso", type=Path, help="Your Melee USA v1.02 disc image, for a local import")
    parser.add_argument("--jobs", type=int, default=min(os.cpu_count() or 4, 12))
    parser.add_argument("--runtime-dir", type=Path, default=ROOT / "build/native/recomp")
    parser.add_argument("--output", type=Path,
                        default=ROOT / f"build/native/Melee-for-Linux-{platform.machine()}.AppImage")
    parser.add_argument("--user-dir", type=Path, default=ROOT / "build/native/user-data/melee4linux",
                        help="Where --iso imports the game and module. Must end in melee4linux.")
    parser.add_argument("--texture-pack", type=Path, help="Replacement texture root containing GALE01")
    parser.add_argument("--appdir-only", action="store_true", help="Produce an AppDir instead of an AppImage")
    parser.add_argument("--no-ccache", action="store_true", help="Do not use ccache even when installed")
    args = parser.parse_args()
    if platform.system() != "Linux":
        parser.error("This build runs on Linux. Use native/macos/build.py on a Mac.")
    if sys.version_info < (3, 11):
        parser.error("Use Python 3.11 or later.")
    if args.jobs < 1:
        parser.error("--jobs must be positive.")
    if args.appdir_only and args.output.suffix == ".AppImage":
        args.output = args.output.with_suffix(".AppDir")
    for tool in ("git", "cmake", "ninja", "pkg-config", "c++", "patchelf", "ldd"):
        if shutil.which(tool) is None:
            parser.error(f"Missing {tool}. See docs/native-linux.md for build dependencies.")
    iso = None
    if args.iso is not None:
        iso = args.iso.expanduser().resolve()
        if not iso.is_file():
            parser.error(f"Disc image does not exist: {iso}")

    runtime = args.runtime_dir.expanduser().resolve()
    if not runtime.exists():
        runtime.parent.mkdir(parents=True, exist_ok=True)
        run("git", "clone", RUNTIME_URL, runtime)
        run("git", "checkout", "--detach", RUNTIME_REV, cwd=runtime)
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=runtime, text=True).strip()
    if revision != RUNTIME_REV:
        raise RuntimeError(f"Runtime must be pinned to {RUNTIME_REV}, found {revision}.")
    template = runtime / "upstream/ModernGekko-Template"
    if not (template / ".git").exists():
        template.parent.mkdir(parents=True, exist_ok=True)
        run("git", "clone", TEMPLATE_URL, template)
        run("git", "checkout", TEMPLATE_REV, cwd=template)
    template_revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=template, text=True).strip()
    if template_revision != TEMPLATE_REV:
        raise RuntimeError(f"Template must be pinned to {TEMPLATE_REV}, found {template_revision}.")
    run("git", "submodule", "update", "--init", "--recursive", cwd=template)
    gekko = template / "lib/ModernGekko"
    dolphin = gekko / "vendor/dolphin"

    patches = patch_plan(runtime)
    # Restore only known patches first. Repeat builds stay safe when hunks share a file.
    for checkout, patch in reversed(patches):
        remove_patch(checkout, patch)
    for checkout, patch in patches:
        apply_patch(checkout, patch)
    for source, destination in copied_sources(runtime):
        shutil.copy2(source, destination / source.name)

    ccache = not args.no_ccache and shutil.which("ccache") is not None
    build = runtime / "build"
    run("cmake", "-S", template / "lib/DolRecomp", "-B", build / "dolrecomp", *cmake_flags(ccache))
    run("cmake", "--build", build / "dolrecomp", "--target", "dolrecomp", "-j", args.jobs)
    run("cmake", "-S", gekko, "-B", build / "runtime", *cmake_flags(ccache),
        f"-DMODERNGEKKO_FRONTEND_NAME={APP_NAME}",
        "-DMODERNGEKKO_LAUNCHER_OUTPUT_NAME=MeleeLauncher",
        "-DMODERNGEKKO_RUNNER_OUTPUT_NAME=MeleeRuntime",
        "-DMODERNGEKKO_USER_DIRECTORY_NAME=melee4linux",
        "-DMODERNGEKKO_LOG_FILENAME=melee4linux.log",
        "-DMODERNGEKKO_REQUIRED_DISC_ID=GALE01",
        "-DMODERNGEKKO_GAMECUBE_CONTROLLERS=ON",
        f"-DMODERNGEKKO_DEFAULT_WINDOW_TITLE={APP_NAME}")
    run("cmake", "--build", build / "runtime", "--target", "moderngekko-run", "moderngekko-launcher",
        "-j", args.jobs)
    (build / "runtime/melee-build-id.txt").write_text(build_identity(runtime))

    package_options = ["--texture-pack", args.texture_pack] if args.texture_pack else []
    if args.appdir_only:
        package_options.append("--appdir-only")
    run(sys.executable, HERE / "package.py", "--runtime-dir", runtime, "--output", args.output,
        "--downloads", runtime / "downloads", "--replace", *package_options)

    if iso is None:
        return
    # The AppImage's own tools do the import, so this exercises what users run.
    output = args.output.expanduser().resolve()
    if args.appdir_only:
        appdir = output
    else:
        appdir = runtime / "build/appimage-extract"
        shutil.rmtree(appdir, ignore_errors=True)
        appdir.parent.mkdir(parents=True, exist_ok=True)
        run(output, "--appimage-extract", cwd=appdir.parent)
        (appdir.parent / "squashfs-root").rename(appdir)
    user = args.user_dir.expanduser().resolve()
    user.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, "XDG_DATA_HOME": str(user.parent), "MELEE_APP_BUNDLE": "1"}
    # The launcher's user directory is $XDG_DATA_HOME/melee4linux.
    if user.name != "melee4linux":
        raise RuntimeError("--user-dir must end in melee4linux, the launcher's directory name.")
    run(appdir / "usr/bin/MeleeLauncher", "--extract", iso, env=env)
    run(appdir / "usr/bin/melee-import-game", "--game", user / "games/GALE01", "--user-dir", user,
        "--jobs", args.jobs, env=env)
    print(f"Play with: XDG_DATA_HOME={user.parent} {output}")
    print("The user directory contains code translated from your disc. Do not upload it.")


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, subprocess.CalledProcessError) as error:
        raise SystemExit(str(error)) from error
