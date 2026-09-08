#!/usr/bin/env python3
"""Build and verify the original executable using the current configuration."""

import argparse
import hashlib
import re
import subprocess
import sys
from pathlib import Path


def verify(root: Path, version: str, ninja: str) -> None:
    if not (root / "build.ninja").is_file():
        raise ValueError(
            "build.ninja is missing. Run configure.py with your build options first."
        )

    dol = Path("build") / version / "main.dol"
    report = dol.with_name("report.json")
    manifest = Path("config") / version / "build.sha1"
    entries = [
        line.split()
        for line in (root / manifest).read_text(encoding="utf-8").splitlines()
    ]
    hashes = [
        entry[0]
        for entry in entries
        if len(entry) == 2 and entry[1].removeprefix("*") == dol.as_posix()
    ]
    if len(hashes) != 1 or re.fullmatch(r"[0-9a-fA-F]{40}", hashes[0]) is None:
        raise ValueError(f"{manifest} must contain one valid SHA-1 for {dol}.")
    expected = hashes[0].lower()

    # The default Ninja target can report progress without linking main.dol.
    subprocess.run([ninja, dol.as_posix(), report.as_posix()], cwd=root, check=True)
    subprocess.run([ninja, "diff"], cwd=root, check=True)

    for artifact in (dol, report):
        if not (root / artifact).is_file():
            raise ValueError(f"Required build artifact is missing: {artifact}")

    actual = hashlib.sha1((root / dol).read_bytes()).hexdigest()
    if actual != expected:
        raise ValueError(
            f"SHA-1 mismatch for {dol}\nExpected: {expected}\nActual:   {actual}"
        )
    print(f"Verified {dol}: SHA-1 {actual}")
    print(f"Ninja diff passed. Build report: {report}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--version", type=str.upper, choices=["GALE01"], default="GALE01"
    )
    parser.add_argument("--ninja", default="ninja", help="Ninja executable or path")
    args = parser.parse_args()
    root = Path(__file__).resolve().parent.parent

    try:
        verify(root, args.version, args.ninja)
    except subprocess.CalledProcessError as error:
        print(
            f"Verification failed: Ninja exited with {error.returncode}.",
            file=sys.stderr,
        )
        return 1
    except (OSError, ValueError) as error:
        print(f"Verification failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
