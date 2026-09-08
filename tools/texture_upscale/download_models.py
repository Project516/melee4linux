"""Download official Real-ESRGAN weights and reject incomplete or changed files."""

import argparse
import hashlib
import urllib.request
from pathlib import Path

MODELS = {
    "general": {
        "file": "realesr-general-x4v3.pth",
        "release": "v0.2.5.0",
        "sha256": "8dc7edb9ac80ccdc30c3a5dca6616509367f05fbc184ad95b731f05bece96292",
        "convolutions": 32,
        "padding": 34,
    },
    "general-clean": {
        "file": "realesr-general-wdn-x4v3.pth",
        "release": "v0.2.5.0",
        "sha256": "1641f8c4464b9f097c9fdda5589273713f67cf59f3d909e0bd688f0cee269dca",
        "convolutions": 32,
        "padding": 34,
    },
    "anime": {
        "file": "realesr-animevideov3.pth",
        "release": "v0.2.5.0",
        "sha256": "b8a8376811077954d82ca3fcf476f1ac3da3e8a68a4f4d71363008000a18b75d",
        "convolutions": 16,
        "padding": 18,
    },
    "esrgan": {
        "file": "RealESRGAN_x4plus.pth",
        "release": "v0.1.0",
        "sha256": "4fa0d38905f75ac06eb49a7951b426670021be3018265fd191d2125df9d682f1",
        "convolutions": None,
        "padding": 32,
    },
}


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def model_path(name: str, directory: Path, *, download: bool = False) -> Path:
    spec = MODELS[name]
    path = directory / str(spec["file"])
    if path.exists():
        if sha256(path) != spec["sha256"]:
            raise ValueError(f"Model checksum mismatch: {path}")
        return path
    if not download:
        raise FileNotFoundError(f"Missing model {path}. Run download_models.py first.")
    directory.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".download")
    url = f"https://github.com/xinntao/Real-ESRGAN/releases/download/{spec['release']}/{spec['file']}"
    try:
        urllib.request.urlretrieve(url, temporary)
        if sha256(temporary) != spec["sha256"]:
            raise ValueError(f"Downloaded model checksum mismatch: {url}")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--models", nargs="+", choices=MODELS, default=["general", "anime"]
    )
    parser.add_argument(
        "--directory", type=Path, default=Path("build/texture-upscale/models")
    )
    args = parser.parse_args()
    for name in args.models:
        print(model_path(name, args.directory, download=True))


if __name__ == "__main__":
    main()
