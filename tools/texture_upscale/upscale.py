"""Alpha-aware local texture super-resolution with explicit AI model selection."""

import argparse
import json
import time
from pathlib import Path

import numpy as np
from PIL import Image
from scipy.ndimage import distance_transform_edt

try:
    from .download_models import MODELS, model_path
except ImportError:
    from download_models import MODELS, model_path

METHODS = ("lanczos", "bicubic", "nearest", *MODELS)


def bleed_transparent_rgb(
    rgba: np.ndarray, wrap_s: int = 0, wrap_t: int = 0
) -> np.ndarray:
    """Extend visible RGB into transparent texels before filtering straight alpha."""
    height, width = rgba.shape[:2]
    # A repeated texture can have a nearer visible texel across the boundary.
    # Include one neighboring repeat before finding nearest visible colors.
    horizontal = width if wrap_s == 1 else 0
    vertical = height if wrap_t == 1 else 0
    if horizontal or vertical:
        rgba = np.pad(
            rgba, ((vertical, vertical), (horizontal, horizontal), (0, 0)), mode="wrap"
        )
    rgb = rgba[:, :, :3].copy()
    visible = rgba[:, :, 3] > 0
    if not visible.any():
        rgb.fill(0)
    elif not visible.all():
        indices = distance_transform_edt(
            ~visible, return_distances=False, return_indices=True
        )
        rgb[~visible] = rgb[tuple(axis[~visible] for axis in indices)]
    return rgb[vertical : vertical + height, horizontal : horizontal + width]


def pad_rgb(rgb: np.ndarray, amount: int, wrap_s: int, wrap_t: int) -> np.ndarray:
    """Pad each axis with its sampler mode so repeat textures retain edge context."""
    modes = {0: "edge", 1: "wrap", 2: "symmetric"}
    if wrap_s not in modes or wrap_t not in modes:
        raise ValueError("Sampler mode must be 0 (clamp), 1 (repeat), or 2 (mirror)")
    result = np.pad(rgb, ((amount, amount), (0, 0), (0, 0)), mode=modes[wrap_t])
    return np.pad(result, ((0, 0), (amount, amount), (0, 0)), mode=modes[wrap_s])


def resize_channel(
    channel: Image.Image, size: tuple[int, int], resample, wrap_s: int, wrap_t: int
) -> Image.Image:
    # Lanczos reaches three source texels beyond the image. Apply sampler context
    # to the reference filters too, including alpha, then remove the border.
    border = 4
    array = np.asarray(channel)
    if array.ndim == 2:
        array = array[:, :, None]
    padded = pad_rgb(array, border, wrap_s, wrap_t)
    if padded.shape[2] == 1:
        padded = padded[:, :, 0]
    scale_x, scale_y = size[0] / channel.width, size[1] / channel.height
    output = Image.fromarray(padded).resize(
        (round(padded.shape[1] * scale_x), round(padded.shape[0] * scale_y)), resample
    )
    left, top = round(border * scale_x), round(border * scale_y)
    return output.crop((left, top, left + size[0], top + size[1]))


class Upscaler:
    """Reuse loaded networks across a texture pack. AI inference uses fixed weights."""

    def __init__(
        self,
        model_directory: Path = Path("build/texture-upscale/models"),
        device: str = "auto",
        tile_size: int = 192,
    ):
        if tile_size < 16:
            raise ValueError("Tile size must be at least 16")
        self.model_directory = model_directory
        self.device = device
        self.tile_size = tile_size
        self.networks = {}

    def _network(self, method: str):
        if method in self.networks:
            return self.networks[method]
        import torch

        try:
            from .models import RRDBNet, SRVGGNetCompact
        except ImportError:
            from models import RRDBNet, SRVGGNetCompact
        if self.device == "auto":
            self.device = "mps" if torch.backends.mps.is_available() else "cpu"
        if self.device == "mps" and not torch.backends.mps.is_available():
            raise RuntimeError("The MPS device is not available")
        path = model_path(method, self.model_directory)
        checkpoint = torch.load(path, map_location="cpu", weights_only=True)
        network = (
            RRDBNet()
            if method == "esrgan"
            else SRVGGNetCompact(MODELS[method]["convolutions"])
        )
        network.load_state_dict(
            checkpoint.get("params_ema", checkpoint.get("params", checkpoint)),
            strict=True,
        )
        network.eval().requires_grad_(False)
        # Use the same float32 precision on CPU and MPS.
        network.to(self.device)
        self.networks[method] = network
        return network

    def _infer(
        self, rgb: np.ndarray, method: str, wrap_s: int, wrap_t: int
    ) -> np.ndarray:
        import torch

        network = self._network(method)
        height, width = rgb.shape[:2]
        border = int(MODELS[method]["padding"])
        padded = pad_rgb(rgb, border, wrap_s, wrap_t)
        result = np.empty((height * 4, width * 4, 3), dtype=np.uint8)
        with torch.inference_mode():
            for top in range(0, height, self.tile_size):
                for left in range(0, width, self.tile_size):
                    bottom, right = (
                        min(top + self.tile_size, height),
                        min(left + self.tile_size, width),
                    )
                    tile = padded[top : bottom + border * 2, left : right + border * 2]
                    tensor = (
                        torch.from_numpy(tile.transpose(2, 0, 1).copy())
                        .unsqueeze(0)
                        .to(self.device, dtype=torch.float32)
                        / 255
                    )
                    output = network(tensor)
                    output = output[
                        0,
                        :,
                        border * 4 : (border + bottom - top) * 4,
                        border * 4 : (border + right - left) * 4,
                    ]
                    pixels = (
                        output.clamp(0, 1)
                        .mul(255)
                        .round()
                        .to(torch.uint8)
                        .cpu()
                        .numpy()
                        .transpose(1, 2, 0)
                    )
                    result[top * 4 : bottom * 4, left * 4 : right * 4] = pixels
        return result

    def upscale_image(
        self,
        image: Image.Image,
        method: str = "general",
        scale: int = 4,
        *,
        wrap_s: int = 0,
        wrap_t: int = 0,
    ) -> Image.Image:
        if method not in METHODS:
            raise ValueError(f"Unknown method: {method}")
        if scale not in (1, 2, 4):
            raise ValueError("Scale must be 1, 2, or 4")
        rgba = image.convert("RGBA")
        if scale == 1:
            return rgba.copy()
        pixels = np.asarray(rgba)
        size = (image.width * scale, image.height * scale)
        if not pixels[:, :, 3].any():
            return Image.new("RGBA", size)
        rgb = Image.fromarray(bleed_transparent_rgb(pixels, wrap_s, wrap_t))
        if method in MODELS:
            enlarged = Image.fromarray(
                self._infer(np.asarray(rgb), method, wrap_s, wrap_t)
            )
            if scale != 4:
                enlarged = resize_channel(
                    enlarged, size, Image.Resampling.LANCZOS, wrap_s, wrap_t
                )
        else:
            resample = {
                "lanczos": Image.Resampling.LANCZOS,
                "bicubic": Image.Resampling.BICUBIC,
                "nearest": Image.Resampling.NEAREST,
            }[method]
            enlarged = resize_channel(rgb, size, resample, wrap_s, wrap_t)
        # Alpha is coverage, not a color photograph. Do not infer new mask detail.
        alpha_filter = (
            Image.Resampling.NEAREST
            if method == "nearest"
            else Image.Resampling.BICUBIC
        )
        alpha = resize_channel(rgba.getchannel("A"), size, alpha_filter, wrap_s, wrap_t)
        enlarged.putalpha(alpha)
        return enlarged


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--method", choices=METHODS, default="general")
    parser.add_argument("--scale", type=int, choices=(1, 2, 4), default=4)
    parser.add_argument(
        "--models", type=Path, default=Path("build/texture-upscale/models")
    )
    parser.add_argument("--device", choices=("auto", "cpu", "mps"), default="auto")
    parser.add_argument("--tile-size", type=int, default=192)
    for axis in ("s", "t"):
        group = parser.add_mutually_exclusive_group()
        group.add_argument(
            f"--wrap-{axis}",
            dest=f"wrap_{axis}",
            action="store_const",
            const=1,
            default=0,
        )
        group.add_argument(
            f"--mirror-{axis}", dest=f"wrap_{axis}", action="store_const", const=2
        )
    args = parser.parse_args()
    start = time.perf_counter()
    engine = Upscaler(args.models, args.device, args.tile_size)
    with Image.open(args.input) as source:
        result = engine.upscale_image(
            source, args.method, args.scale, wrap_s=args.wrap_s, wrap_t=args.wrap_t
        )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    result.save(args.output)
    print(
        json.dumps(
            {
                "method": args.method,
                "device": engine.device,
                "seconds": round(time.perf_counter() - start, 4),
                "width": result.width,
                "height": result.height,
            }
        )
    )


if __name__ == "__main__":
    main()
