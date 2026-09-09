#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Compile the native Melee module for an extracted USA v1.02 game.

The launcher runs this after it extracts the user's own disc. It translates
the verified game executable to C, compiles that C with the bundled
compiler, and installs the module where the runtime looks for it. The
extracted game and the disc image are not modified.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import re
import shlex
import shutil
import subprocess
import sys
import time


DOL_SHA1 = "08e0bf20134dfcb260699671004527b2d6bb1a45"
GAME_ID = "GALE01"
MODULE_NAME = f"g{GAME_ID}_recomp.so"
# Oldest glibc the module links against. The runtime itself needs newer.
GLIBC_TARGET = "2.28"
# Objects per static archive. Keeps every command line far below ARG_MAX.
ARCHIVE_GROUP = 250
HERE = Path(__file__).resolve().parent
CPU_SOURCES = (
    "cpu.c",
    "cpu_exception.c",
    "cpu_interpreter.c",
    "cpu_interpreter_table.c",
    "cpu_interpreter_float.c",
    "cpu_interpreter_integer.c",
)


class ImportError_(Exception):
    """The game or the tools are not usable."""


@dataclass(frozen=True)
class Tools:
    """Bundled tool locations. package.py creates this layout."""

    root: Path
    dolrecomp: Path

    @property
    def zig(self) -> Path:
        return self.root / "zig" / "zig"

    @property
    def ninja(self) -> Path:
        return self.root / "ninja"

    @property
    def module(self) -> Path:
        return self.root / "module"

    @property
    def build_id(self) -> str:
        stamp = self.root / "build-id.txt"
        return stamp.read_text().strip() if stamp.is_file() else "development"

    def check(self) -> None:
        for path in (
                self.dolrecomp, self.zig, self.ninja, self.module / "module_export.c",
                self.module / "module.exports", self.module / "gen_module_tables.py",
                self.module / "gxruntime/include/core/cpu.h",
                self.module / "staticrecomp/StaticRecompABI.h"):
            if not path.is_file():
                raise ImportError_(f"The bundled tools are incomplete: {path}")
        for name in CPU_SOURCES:
            if not (self.module / "gxruntime/src/core" / name).is_file():
                raise ImportError_(f"The bundled tools are incomplete: gxruntime/src/core/{name}")


class Status:
    """Progress for the launcher. One key=value file, replaced atomically."""

    def __init__(self, path: Path | None):
        self.path = path
        self.completed = 0
        self.total = 0
        self.message = ""

    def update(
            self, message: str, completed: int = 0, total: int = 0,
            done: bool = False, error: str = "") -> None:
        self.message, self.completed, self.total = message, completed, total
        line = message if not total else f"{message} ({completed} of {total})"
        print(line, flush=True)
        if self.path is None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(self.path.name + ".tmp")
        temporary.write_text(
            f"message={message}\ncompleted={completed}\ntotal={total}\n"
            f"done={int(done)}\nerror={error}\n"
        )
        temporary.replace(self.path)


def script_path(name: str) -> Path:
    """Sibling tools in the AppImage, or the Mac build's copies in a checkout."""
    for candidate in (HERE / name, HERE.parent / "macos" / name):
        if candidate.is_file():
            return candidate
    raise ImportError_(f"Missing tool script: {name}")


def load_script(name: str):
    path = script_path(name)
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sha1(path: Path) -> str:
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha1").hexdigest()


def module_target() -> str:
    machine = platform.machine()
    if machine in ("aarch64", "arm64"):
        return f"aarch64-linux-gnu.{GLIBC_TARGET}"
    if machine in ("x86_64", "amd64"):
        return f"x86_64-linux-gnu.{GLIBC_TARGET}"
    raise ImportError_(f"Unsupported CPU architecture: {machine}")


def default_jobs() -> int:
    """Leave room for the compiler's memory use on small machines."""
    cpus = os.cpu_count() or 2
    try:
        with open("/proc/meminfo") as source:
            for line in source:
                if line.startswith("MemTotal:"):
                    kib = int(line.split()[1])
                    return max(1, min(cpus, kib // (768 * 1024)))
    except (OSError, ValueError, IndexError):
        pass
    return max(1, cpus)


def stamp_path(module: Path) -> Path:
    return module.with_suffix(".json")


def stamp_identity(tools: Tools, dol_sha1: str) -> dict:
    return {"build_id": tools.build_id, "dol_sha1": dol_sha1, "target": module_target(),
            "module": MODULE_NAME}


def module_current(module: Path, tools: Tools, dol_sha1: str) -> bool:
    stamp = stamp_path(module)
    if not module.is_file() or not stamp.is_file():
        return False
    try:
        recorded = json.loads(stamp.read_text())
    except (OSError, ValueError):
        return False
    identity = stamp_identity(tools, dol_sha1)
    return all(recorded.get(key) == value for key, value in identity.items())


def check_game(game: Path) -> str:
    dol = game / "sys/main.dol"
    apploader = game / "sys/apploader.img"
    if not dol.is_file() or not apploader.is_file():
        raise ImportError_(f"The extracted game is incomplete: {game}")
    digest = sha1(dol)
    if digest != DOL_SHA1:
        raise ImportError_(
            "This build supports Melee USA v1.02 only. The extracted executable has "
            f"SHA-1 {digest}, expected {DOL_SHA1}.")
    return digest


def ninja_path(value: Path | str) -> str:
    """Escape a path for a ninja build statement."""
    return str(value).replace("$", "$$").replace(" ", "$ ").replace(":", "$:")


def ninja_command(arguments: list[str]) -> str:
    """Quote a shell command for a ninja rule. Tokens starting with $ are ninja variables."""
    return " ".join(
        argument if argument.startswith(("$", '"$')) else shlex.quote(argument).replace("$", "$$")
        for argument in arguments
    )


def write_ninja(build: Path, tools: Tools, generated: Path, target: str) -> Path:
    """Mirror RecompCore's module-template CMake rules for the bundled compiler."""
    chunks = sorted((generated / "chunks").glob("*.c"))
    if not chunks:
        raise ImportError_(f"DolRecomp produced no chunks in {generated}")
    header = (generated / "generated.h").read_text()
    defines = ['-DMODULE_GAME_ID="GALE01"', '-DDOLRECOMP_CPU_HEADER="core/cpu.h"']
    if "dolrecomp_call__x86_64_v3" in header:
        defines.append("-DDOLRECOMP_MODULE_HAVE_X86_64_V3=1")
    includes = [generated, tools.module / "gxruntime/include", tools.module / "staticrecomp", build]
    compiler = [str(tools.zig), "cc", "-target", target, "-O2", "-ffp-contract=off",
                "-fno-fast-math", "-fvisibility=hidden", "-fPIC", "-std=gnu11", *defines,
                *(f"-I{path}" for path in includes)]
    lines = [
        "ninja_required_version = 1.5",
        "rule cc",
        "  command = " + ninja_command([*compiler, "-MMD", "-MF", "$out.d", "-c", '"$in"', "-o", '"$out"']),
        "  depfile = $out.d",
        "  deps = gcc",
        "  description = CC $in",
        "rule ar",
        "  command = rm -f \"$out\" && " + ninja_command([str(tools.zig), "ar", "qc", '"$out"']) + " $objects",
        "  description = AR $out",
        "rule link",
        "  command = $link",
        "  description = LINK $out",
    ]
    objects: list[Path] = []
    # module_export.c includes the generated tables, which ninja does not see as a header.
    export = tools.module / "module_export.c"
    for source in [export, *(tools.module / "gxruntime/src/core" / name for name in CPU_SOURCES)]:
        output = build / "runtime" / (source.stem + ".o")
        implicit = f" | {ninja_path(build / 'module_tables.inc')}" if source == export else ""
        lines.append(f"build {ninja_path(output)}: cc {ninja_path(source)}{implicit}")
        objects.append(output)
    archives: list[Path] = []
    for index in range(0, len(chunks), ARCHIVE_GROUP):
        group = chunks[index:index + ARCHIVE_GROUP]
        group_objects = [build / "chunks" / (source.stem + ".o") for source in group]
        for source, output in zip(group, group_objects):
            lines.append(f"build {ninja_path(output)}: cc {ninja_path(source)}")
        archive = build / "chunks" / f"group_{index // ARCHIVE_GROUP:04d}.a"
        lines.append(f"build {ninja_path(archive)}: ar {' '.join(ninja_path(o) for o in group_objects)}")
        lines.append("  objects = " + " ".join(shlex.quote(str(o)).replace("$", "$$") for o in group_objects))
        archives.append(archive)
    module = build / MODULE_NAME
    link = [str(tools.zig), "cc", "-target", target, "-shared", "-fPIC", "-o", str(module),
            *(str(o) for o in objects), "-Wl,--whole-archive", *(str(a) for a in archives),
            "-Wl,--no-whole-archive", f"-Wl,--version-script={tools.module / 'module.exports'}", "-lm"]
    lines.append(
        f"build {ninja_path(module)}: link {' '.join(ninja_path(p) for p in objects + archives)} "
        f"| {ninja_path(tools.module / 'module.exports')}")
    lines.append("  link = " + ninja_command(link))
    lines.append(f"default {ninja_path(module)}")
    (build / "build.ninja").write_text("\n".join(lines) + "\n")
    return module


def run(arguments: list, cwd: Path | None = None, env: dict | None = None, log=None) -> None:
    print("+ " + " ".join(map(str, arguments)), flush=True)
    result = subprocess.run([str(a) for a in arguments], cwd=cwd, env=env, stdout=log, stderr=log)
    if result.returncode:
        raise ImportError_(f"{Path(str(arguments[0])).name} failed with exit status {result.returncode}")


def compile_module(build: Path, tools: Tools, jobs: int, status: Status, env: dict, log_path: Path) -> None:
    progress = re.compile(r"^\[(\d+)/(\d+)\] ")
    command = [str(tools.ninja), "-C", str(build), "-j", str(jobs)]
    print("+ " + " ".join(command), flush=True)
    last_update = 0.0
    with log_path.open("w") as log, subprocess.Popen(
            command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
            env={**env, "NINJA_STATUS": "[%f/%t] "}) as process:
        for line in process.stdout:
            log.write(line)
            match = progress.match(line)
            if match is None:
                continue
            finished, total = int(match.group(1)), int(match.group(2))
            now = time.monotonic()
            if finished == total or now - last_update >= 0.5:
                status.update("Compiling native code", finished, total)
                last_update = now
    if process.returncode:
        tail = "".join(log_path.read_text().splitlines(keepends=True)[-20:])
        raise ImportError_(f"Native compilation failed. Log: {log_path}\n{tail}")


def build_module(game: Path, user: Path, tools: Tools, jobs: int, status: Status, force: bool) -> Path:
    tools.check()
    status.update("Checking the game executable")
    dol_sha1 = check_game(game)
    modules = user / "StaticRecompModules"
    module = modules / MODULE_NAME
    if not force and module_current(module, tools, dol_sha1):
        status.update("Native module is up to date", done=True)
        return module
    target = module_target()
    setup = user / "Setup"
    setup.mkdir(parents=True, exist_ok=True)
    env = {
        **os.environ, "ZIG_GLOBAL_CACHE_DIR": str(setup / "zig-cache"),
        "ZIG_LOCAL_CACHE_DIR": str(setup / "zig-cache")}

    status.update("Preparing the compilation input")
    boot = load_script("recompile_boot.py")
    compilation_dol = setup / "native-boot.dol"
    content = boot.compilation_dol(
        (game / "sys/main.dol").read_bytes(), (game / "sys/apploader.img").read_bytes())
    if not compilation_dol.exists() or compilation_dol.read_bytes() != content:
        compilation_dol.write_bytes(content)

    status.update("Translating the game executable to C")
    scratch = setup / "recompiled-next"
    if scratch.is_symlink():
        raise ImportError_(f"Refusing a symbolic link for generated output: {scratch}")
    shutil.rmtree(scratch, ignore_errors=True)
    with (setup / "dolrecomp.log").open("w") as log:
        run([tools.dolrecomp, f"-j{jobs}", "--cpu", "gekko", "--gamecube", compilation_dol, scratch],
            env=env, log=log)
    generated_next = scratch / "generated"
    for name in ("generated.h", "generated_smc.txt", "chunks"):
        if not (generated_next / name).exists():
            raise ImportError_(f"DolRecomp output is incomplete: {generated_next / name}")
    shutil.copyfile(compilation_dol, generated_next / "main.dol")
    recompiled = setup / "recompiled"
    shutil.rmtree(recompiled, ignore_errors=True)
    recompiled.mkdir()
    generated = recompiled / "generated"
    generated_next.rename(generated)
    shutil.rmtree(scratch, ignore_errors=True)

    status.update("Adding the native render hooks")
    load_script("high_refresh.py").install(generated)

    status.update("Generating module tables")
    build = setup / "module-build"
    shutil.rmtree(build, ignore_errors=True)
    for directory in (build / "runtime", build / "chunks"):
        directory.mkdir(parents=True)
    with (setup / "module-tables.log").open("w") as log:
        run([
            sys.executable, tools.module / "gen_module_tables.py", generated / "generated.h",
            generated / "generated_smc.txt", generated / "main.dol", build / "module_tables.inc"], log=log)

    status.update("Compiling native code", 0, len(list((generated / "chunks").glob("*.c"))))
    built = write_ninja(build, tools, generated, target)
    compile_module(build, tools, jobs, status, env, setup / "module-build.log")
    if not built.is_file():
        raise ImportError_(f"The linker produced no module at {built}")

    status.update("Installing the native module")
    modules.mkdir(parents=True, exist_ok=True)
    staged = modules / (MODULE_NAME + ".tmp")
    shutil.copyfile(built, staged)
    staged.replace(module)
    stamp = stamp_identity(tools, dol_sha1)
    stamp["created"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    stamp["chunks"] = len(list((generated / "chunks").glob("*.c")))
    stamp_path(module).write_text(json.dumps(stamp, indent=2) + "\n")
    status.update("Native module ready", done=True)
    return module


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game", type=Path, required=True, help="Extracted game root with sys/ and files/")
    parser.add_argument("--user-dir", type=Path, required=True, help="Runtime user directory")
    parser.add_argument("--tools", type=Path, required=True, help="Bundled tool root (share/melee)")
    parser.add_argument("--dolrecomp", type=Path, required=True, help="DolRecomp executable")
    parser.add_argument("--status", type=Path, help="Progress file for the launcher")
    parser.add_argument("--jobs", type=int, default=default_jobs())
    parser.add_argument("--force", action="store_true", help="Rebuild an up-to-date module")
    parser.add_argument("--check", action="store_true", help="Exit 0 if the module is current, 3 if not")
    args = parser.parse_args()
    if args.jobs < 1:
        parser.error("--jobs must be positive.")
    tools = Tools(args.tools.expanduser().resolve(), args.dolrecomp.expanduser().resolve())
    game = args.game.expanduser().resolve()
    user = args.user_dir.expanduser().resolve()
    status = Status(args.status.expanduser().resolve() if args.status else None)
    try:
        if args.check:
            module = user / "StaticRecompModules" / MODULE_NAME
            return 0 if module_current(module, tools, check_game(game)) else 3
        module = build_module(game, user, tools, args.jobs, status, args.force)
    except (ImportError_, OSError, ValueError) as error:
        status.update("Native module build failed", done=True, error=str(error).splitlines()[0])
        print(f"Import failed: {error}", file=sys.stderr)
        return 1
    print(f"Native module: {module}\nIt contains code translated from your game. Do not upload it.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
