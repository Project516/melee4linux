#!/usr/bin/env python3

###
# Generates a ctx.c file, usable for "Context" on https://decomp.me.
#
# Usage:
#   python3 tools/decompctx.py src/file.cpp
#
# Based on https://github.com/encounter/dtk-template.
# Changes for this automated fork stay in t3dotgg/melee.
###

import argparse
import fnmatch
import os
import re
import sys
import tempfile
from typing import List

script_dir = os.path.dirname(os.path.realpath(__file__))
root_dir = os.path.abspath(os.path.join(script_dir, ".."))
include_dirs: List[str] = []  # Set with -I flag
exclude_globs: List[str] = []  # Set with -x flag

include_pattern = re.compile(r'^#\s*include\s*[<"](.+?)[>"]')
guard_pattern = re.compile(r"^#\s*ifndef\s+(.*)$")
once_pattern = re.compile(r"^#\s*pragma\s+once$")

defines = set()
deps = []


def generate_prelude(defines) -> str:
    if len(defines) == 0:
        return ""

    out_text = "/* decompctx prelude */\n"
    for define in defines:
        parts = define.split("=", 1)
        if len(parts) == 2:
            macro_name, macro_val = parts
            out_text += f"#define {macro_name} {macro_val}\n"
        else:
            out_text += f"#define {parts[0]}\n"
    out_text += "/* end decompctx prelude */\n\n"

    return out_text


def import_h_file(in_file: str, parent_file: str, line_number: int) -> str:
    rel_path = os.path.join(root_dir, os.path.dirname(parent_file), in_file)
    if os.path.isfile(rel_path):
        return import_c_file(rel_path)
    for include_dir in include_dirs:
        inc_path = os.path.join(include_dir, in_file)
        if os.path.isfile(inc_path):
            return import_c_file(inc_path)
    raise FileNotFoundError(
        f'{parent_file}:{line_number}: cannot find include "{in_file}"'
    )


def import_c_file(in_file: str) -> str:
    source_path = os.path.abspath(in_file)
    in_file = os.path.relpath(source_path, root_dir)
    deps.append(in_file)

    # Retry only decoding. Processing can already have added include guards.
    try:
        with open(source_path, encoding="utf-8") as file:
            lines = list(file)
    except UnicodeDecodeError:
        with open(source_path) as file:
            lines = list(file)
    return process_file(in_file, lines)


def process_file(in_file: str, lines: List[str]) -> str:
    out_text = ""
    for idx, line in enumerate(lines):
        if idx == 0:
            guard_match = guard_pattern.match(line.strip())
            if guard_match:
                if guard_match[1] in defines:
                    break
                defines.add(guard_match[1])
            else:
                once_match = once_pattern.match(line.strip())
                if once_match:
                    if in_file in defines:
                        break
                    defines.add(in_file)
            print("Processing file", in_file)
        include_match = include_pattern.match(line.strip())
        if include_match and not include_match[1].endswith(".s"):
            excluded = False
            for glob in exclude_globs:
                if fnmatch.fnmatch(include_match[1], glob):
                    excluded = True
                    break

            out_text += f'/* "{in_file}" line {idx} "{include_match[1]}" */\n'
            if excluded:
                out_text += "/* Skipped excluded file */\n"
            else:
                out_text += import_h_file(include_match[1], in_file, idx + 1)
            out_text += f'/* end "{include_match[1]}" */\n'
        else:
            out_text += line

    return out_text


def sanitize_path(path: str) -> str:
    return path.replace("\\", "/").replace(" ", "\\ ")


def write_output(path: str, text: str) -> None:
    """Replace a generated file only after its contents have been written."""
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=os.path.dirname(path), delete=False
        ) as file:
            temporary_path = file.name
            file.write(text)
        os.replace(temporary_path, path)
    finally:
        if temporary_path is not None and os.path.exists(temporary_path):
            os.unlink(temporary_path)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="""Create a context file which can be used for decomp.me"""
    )
    parser.add_argument(
        "c_file",
        help="""File from which to create context""",
    )
    parser.add_argument(
        "-o",
        "--output",
        help="""Output file""",
        default="ctx.c",
    )
    parser.add_argument(
        "-d",
        "--depfile",
        help="""Dependency file""",
    )
    parser.add_argument(
        "-I",
        "--include",
        help="""Include directory""",
        action="append",
    )
    parser.add_argument(
        "-x",
        "--exclude",
        help="""Excluded file name glob""",
        action="append",
    )
    parser.add_argument(
        "-D",
        "--define",
        help="""Macro definition""",
        action="append",
    )
    args = parser.parse_args()

    if args.include is None:
        parser.error("No include directories specified")
    global include_dirs
    include_dirs = args.include
    global exclude_globs
    exclude_globs = args.exclude or []
    # Each invocation must expand its own headers, including after a failed run.
    defines.clear()
    deps.clear()

    try:
        output = generate_prelude(args.define or [])
        output += import_c_file(args.c_file)

        if args.depfile:
            depfile = sanitize_path(args.output) + ":"
            for dep in deps:
                depfile += f" \\\n\t{sanitize_path(dep)}"
            write_output(os.path.join(root_dir, args.depfile), depfile)

        write_output(os.path.join(root_dir, args.output), output)
    except (OSError, UnicodeError) as error:
        print(f"decompctx: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
