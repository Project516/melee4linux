"""Upscale the 75 ending stills and build their full-resolution YUV planes."""

import argparse
import hashlib
import json
import sys
from pathlib import Path

from PIL import Image

if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools.texture_upscale.extract_special import decode_thp_still
from tools.texture_upscale.still_planes import write_still_planes
from tools.texture_upscale.upscale import Upscaler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--disc-files", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--models", type=Path, required=True)
    args = parser.parse_args()
    images = args.output / "stills"
    planes = args.output / "Textures/GALE01/ending-stills"
    images.mkdir(parents=True, exist_ok=True)
    planes.mkdir(parents=True, exist_ok=True)
    sources = sorted(args.disc_files.glob("GmRegend*.thp"))
    if len(sources) != 75:
        raise RuntimeError("Expected the 75 USA v1.02 ending stills.")
    engine = Upscaler(args.models, tile_size=384)
    records = []
    for index, source in enumerate(sources):
        target = images / (source.stem + ".png")
        if not target.is_file():
            decoded = decode_thp_still(source.read_bytes())
            image = (
                Image.fromarray(decoded)
                if not isinstance(decoded, Image.Image)
                else decoded
            )
            result = engine.upscale_image(image, "esrgan", 4)
            temporary = target.with_suffix(".png.tmp")
            result.save(temporary, format="PNG", compress_level=4)
            temporary.replace(target)
        record = write_still_planes(source, target, planes)
        record.update(
            png=str(target.relative_to(args.output)),
            png_sha256=hashlib.sha256(target.read_bytes()).hexdigest(),
            recipe={"method": "esrgan", "scale": 4},
        )
        records.append(record)
        print(f"Ending stills {index + 1}/{len(sources)}", flush=True)
    (args.output / "ending-stills.json").write_text(
        json.dumps({"stills": records}, indent=2) + "\n"
    )


if __name__ == "__main__":
    main()
