#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Add the local disc loader to a DOL used only for native code generation."""

import argparse
import hashlib
from pathlib import Path
import struct


DOL_SHA1 = "08e0bf20134dfcb260699671004527b2d6bb1a45"
LOADER_SHA1 = "fb7839b0d3041bcc39024fe578736bf73e15e6cf"
LOADER_ADDRESS = 0x81200000
LOADER_CODE_SIZE = 0xD80


def compilation_dol(game: bytes, loader: bytes) -> bytes:
    if hashlib.sha1(game).hexdigest() != DOL_SHA1:
        raise ValueError("The game executable must match Melee USA v1.02.")
    if len(loader) < 32:
        raise ValueError("Truncated disc loader header.")
    entry, size, trailer = struct.unpack_from(">III", loader, 0x10)
    payload_size = size + trailer
    if not size or payload_size != len(loader) - 32 or payload_size % 4:
        raise ValueError("Invalid disc loader length.")
    if not LOADER_ADDRESS <= entry < LOADER_ADDRESS + size or entry % 4:
        raise ValueError("Invalid disc loader entry point.")
    # The boot code reserves 0x81300000 for its report callback and read requests.
    if LOADER_ADDRESS + payload_size > 0x81300000:
        raise ValueError("The disc loader overlaps boot scratch memory.")
    if hashlib.sha1(loader).hexdigest() != LOADER_SHA1:
        raise ValueError("The disc loader must match the supported USA v1.02 image.")
    sections = [struct.unpack_from(">I", game, 0x90 + 4 * i)[0] for i in range(18)]
    if any(sections[index] for index in (2, 3, 15)):
        raise ValueError("DOL text slots 2 and 3 and data slot 8 must be unused.")
    for index, length in enumerate(sections):
        address = struct.unpack_from(">I", game, 0x48 + 4 * index)[0]
        if length and address < LOADER_ADDRESS + payload_size and address + length > LOADER_ADDRESS:
            raise ValueError("The disc loader overlaps a game section.")
    result = bytearray(game)
    result.extend(b"\0" * (-len(result) % 32))
    offset = len(result)
    result.extend(loader[32:])
    # The first stage ends in BLR at 0x81200D70, then padding to 0xD80.
    # Its strings and writable state run to the trailer at header.size.
    # Keep these bytes in memory but out of executable code verification.
    for index, start, length in (
        (2, 0, LOADER_CODE_SIZE),
        (15, LOADER_CODE_SIZE, size - LOADER_CODE_SIZE),
        (3, size, trailer),
    ):
        struct.pack_into(">I", result, index * 4, offset + start)
        struct.pack_into(">I", result, 0x48 + index * 4, LOADER_ADDRESS + start)
        struct.pack_into(">I", result, 0x90 + index * 4, length)
    return bytes(result)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dol", type=Path, required=True)
    parser.add_argument("--apploader", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.resolve() in (args.dol.resolve(), args.apploader.resolve()):
        parser.error("The output must be separate from the original inputs.")
    try:
        content = compilation_dol(args.dol.read_bytes(), args.apploader.read_bytes())
    except (OSError, ValueError) as error:
        parser.error(str(error))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if not args.output.exists() or args.output.read_bytes() != content:
        args.output.write_bytes(content)
    print(f"Native compilation input: {args.output}")
    print("The original game executable and disc loader are unchanged.")


if __name__ == "__main__":
    main()
