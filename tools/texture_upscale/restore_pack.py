"""Rebuild loadable DDS files from the private repository's generated PNGs."""

import argparse
import hashlib
import json
import tempfile
import zipfile
from pathlib import Path

from PIL import Image

try:
    from .dds import write_dds
    from .still_planes import make_planes
except ImportError:
    from dds import write_dds
    from still_planes import make_planes


def checked_path(root, relative, checksum):
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError("An asset path leaves the pack directory")
    with path.open("rb") as source:
        if hashlib.file_digest(source, "sha256").hexdigest() != checksum:
            raise ValueError(
                f"Asset checksum failed: {relative}. Run git lfs pull if needed."
            )
    return path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--assets", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    archives_path = args.assets / "archives.json"
    if archives_path.is_file():
        # PNGs are already compressed. A few stored ZIP files avoid thousands
        # of separate Git LFS transfers. Validate each archive before extraction.
        archive_records = json.loads(archives_path.read_text())["archives"]
        with tempfile.TemporaryDirectory(prefix="melee-textures-") as scratch:
            extracted = Path(scratch)
            for record in archive_records:
                archive = checked_path(args.assets, record["file"], record["sha256"])
                with zipfile.ZipFile(archive) as source:
                    for member in source.infolist():
                        target = (extracted / member.filename).resolve()
                        if not target.is_relative_to(extracted.resolve()):
                            raise ValueError(
                                "Archive member leaves the texture directory"
                            )
                        source.extract(member, extracted)
            restore(args.assets, args.output, extracted)
    else:
        restore(args.assets, args.output, args.assets)


def restore(assets, output, image_root):
    manifest = json.loads((assets / "manifest.json").read_text())
    destination = output / "GALE01"
    for index, record in enumerate(manifest["textures"]):
        path = checked_path(image_root, record["png"], record["png_sha256"])
        with Image.open(path) as image:
            write_dds(
                image,
                destination / (record["name"] + ".dds"),
                record["recipe"]["data_channels"],
            )
        if (index + 1) % 500 == 0:
            print(
                f"Restored {index + 1}/{len(manifest['textures'])} textures", flush=True
            )
    still_manifest = assets / "ending-stills.json"
    if still_manifest.is_file():
        stills = json.loads(still_manifest.read_text())["stills"]
        for record in stills:
            path = checked_path(image_root, record["png"], record["png_sha256"])
            with Image.open(path) as image:
                planes = make_planes(image)
            for plane_record in record["planes"]:
                write_dds(
                    planes[plane_record["channel"]],
                    destination / "ending-stills" / plane_record["file"],
                    True,
                )
    print(f"Texture pack ready: {output}", flush=True)


if __name__ == "__main__":
    main()
