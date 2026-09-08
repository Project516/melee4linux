#!/usr/bin/env python3

###
# Transforms .d files, converting Windows paths to Unix paths.
# Allows usage of the mwcc -MMD flag on platforms other than Windows.
#
# Usage:
#   python3 tools/transform_dep.py build/src/file.d build/src/file.d
#
# Based on https://github.com/encounter/dtk-template.
# Changes for this automated fork stay in t3dotgg/melee4mac.
###

import argparse
import os
import re
from platform import uname

wineprefix = os.environ.get("WINEPREFIX", os.path.expanduser("~/.wine"))
winedevices = os.path.join(wineprefix, "dosdevices")


def in_wsl() -> bool:
    return "microsoft-standard" in uname().release


def import_d_file(in_file: str) -> str:
    out_text = ""

    with open(in_file) as file:
        for idx, line in enumerate(file):
            if idx == 0:
                # MWCC escapes spaces with a backslash. Preserve those
                # escapes and the continuation while changing separators.
                if line.endswith(" \\\n"):
                    out_text += re.sub(r"\\(?! )", "/", line[:-3]) + " \\\n"
                else:
                    out_text += re.sub(r"\\(?! )", "/", line)
            else:
                suffix = ""
                if line.endswith(" \\\n"):
                    suffix = " \\"
                    path = line.lstrip()[:-3]
                else:
                    path = line.strip()
                if not path:
                    continue
                # Resolve the real filesystem path before escaping it for make.
                path = path.replace("\\ ", " ")
                # lowercase drive letter
                path = path[0].lower() + path[1:]
                if path[0] == "z":
                    # shortcut for z:
                    path = path[2:].replace("\\", "/")
                elif in_wsl():
                    path = path[0:1] + path[2:]
                    path = os.path.join("/mnt", path.replace("\\", "/"))
                else:
                    # use $WINEPREFIX/dosdevices to resolve path
                    path = os.path.realpath(
                        os.path.join(winedevices, path.replace("\\", "/"))
                    )
                out_text += "\t" + path.replace(" ", "\\ ") + suffix + "\n"

    return out_text


def main() -> None:
    parser = argparse.ArgumentParser(
        description="""Transform a .d file from Wine paths to normal paths"""
    )
    parser.add_argument(
        "d_file",
        help="""Dependency file in""",
    )
    parser.add_argument(
        "d_file_out",
        help="""Dependency file out""",
    )
    args = parser.parse_args()

    output = import_d_file(args.d_file)

    with open(args.d_file_out, "w", encoding="UTF-8") as f:
        f.write(output)


if __name__ == "__main__":
    main()
