#!/usr/bin/env python3

import argparse
import re
import sys
from pathlib import Path


def search_string_in_files(search_string: str) -> bool:
    src_dir = Path(__file__).resolve().parents[1] / "src"
    pattern = re.compile(r"\b" + re.escape(search_string) + r"\b")
    found = False
    # A use of a symbol can precede its declaration. Show every candidate so
    # filesystem order does not silently select an unrelated header.
    for header in sorted(src_dir.rglob("*.h")):
        if pattern.search(header.read_text(encoding="utf-8")):
            print(f'#include "{header.relative_to(src_dir).as_posix()}"')
            found = True
    return found


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "List headers under src containing a whole-word match, in path order. "
            "Matches can be declarations, uses, or comments."
        )
    )
    parser.add_argument("search_string", help="The string to search for.")
    args = parser.parse_args()

    if search_string_in_files(args.search_string):
        return 0
    print(f"No header contains {args.search_string!r}.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
