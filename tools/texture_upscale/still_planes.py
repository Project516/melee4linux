"""Build full-resolution YUV texture planes for Melee's 75 ending stills."""

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import xxhash
from PIL import Image

try:
    from .dds import write_dds
except ImportError:
    from dds import write_dds


def make_planes(image):
    """Keep full chroma resolution and replicate intensity into alpha for TEV."""
    pixels = np.asarray(image.convert("RGB").convert("YCbCr"))
    return {
        channel: Image.fromarray(np.repeat(pixels[:, :, index, None], 4, axis=2))
        for index, channel in enumerate("yuv")
    }


def write_still_planes(original_thp, upscaled_image, destination):
    """Return a manifest record for three DDS replacements under destination."""
    original_thp = Path(original_thp)
    data = original_thp.read_bytes()
    if not original_thp.name.startswith("GmRegend") or not data.startswith(b"\xff\xd8"):
        raise ValueError("Expected a GmRegend ending still with a JPEG start marker")
    with Image.open(upscaled_image) as source:
        image = source.convert("RGB")
    if (
        image.width % 560
        or image.height % 416
        or image.width // 560 != image.height // 416
    ):
        raise ValueError(
            "The upscaled ending still must be an integer multiple of 560 by 416"
        )
    digest = xxhash.xxh64_hexdigest(data, seed=0)
    files = []
    for channel, plane in make_planes(image).items():
        target = Path(destination) / f"tex1_still_{digest}_{channel}.dds"
        levels = write_dds(plane, target, data_channels=True)
        files.append(
            {
                "channel": channel,
                "file": target.name,
                "width": plane.width,
                "height": plane.height,
                "mip_levels": levels,
                "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
            }
        )
    return {
        "source": original_thp.name,
        "source_xxh64": digest,
        "source_sha256": hashlib.sha256(data).hexdigest(),
        "planes": files,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--disc-files", type=Path, required=True)
    parser.add_argument("--upscaled", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    records = []
    for source in sorted(args.disc_files.glob("GmRegend*.thp")):
        image = args.upscaled / (source.stem + ".png")
        if not image.is_file():
            parser.error(f"Missing upscaled still: {image.name}")
        records.append(write_still_planes(source, image, args.output))
    if not records:
        parser.error("No ending stills found")
    (args.output / "ending-stills.json").write_text(
        json.dumps({"stills": records}, indent=2) + "\n"
    )
    print(
        f"Wrote {len(records)} ending stills as {len(records) * 3} full-resolution planes"
    )


if __name__ == "__main__":
    main()
