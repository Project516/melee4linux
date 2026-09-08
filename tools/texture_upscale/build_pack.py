"""Extract, upscale, and audit a complete pack from the user's local disc files."""

import argparse
import subprocess
import sys
from pathlib import Path

from .download_models import model_path
from .extract import extract_disc
from .pipeline import build
from .quality_report import audit


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--disc",
        type=Path,
        required=True,
        help="Extracted disc root containing files and sys/main.dol",
    )
    parser.add_argument("--output", type=Path, default=Path("build/texture-upscale"))
    parser.add_argument(
        "--models", type=Path, default=Path("build/texture-upscale/models")
    )
    args = parser.parse_args()
    if not (args.disc / "sys/main.dol").is_file() or not (args.disc / "files").is_dir():
        parser.error("Use an extracted Melee USA v1.02 disc directory.")
    extracted = args.output / "extracted"
    extracted.mkdir(parents=True, exist_ok=True)
    model_path("esrgan", args.models, download=True)
    extract_disc(args.disc / "files", extracted, args.disc / "sys/main.dol")
    pack = args.output / "pack"
    build(extracted / "manifest.json", pack, args.models, prune=True)
    subprocess.run(
        [
            sys.executable,
            "-m",
            "tools.texture_upscale.upscale_stills",
            "--disc-files",
            str(args.disc / "files"),
            "--output",
            str(pack),
            "--models",
            str(args.models),
        ],
        check=True,
    )
    if not audit(extracted / "manifest.json", pack, args.output / "quality", 12, 4):
        raise SystemExit("Texture audit failed. See quality/quality.json.")
    print(f"Complete texture pack: {pack / 'Textures'}")


if __name__ == "__main__":
    main()
