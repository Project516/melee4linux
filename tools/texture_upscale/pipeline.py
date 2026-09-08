"""Build every extracted texture with a reviewed policy and resumable records."""

import argparse
import hashlib
import json
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PIL import Image

try:
    from .dds import write_dds
    from .upscale import Upscaler
except ImportError:
    from dds import write_dds
    from upscale import Upscaler


POLICY_VERSION = 1


def recipe(texture):
    sources = texture["sources"]
    kinds = {source["kind"] for source in sources}
    is_effect = "particle" in kinds or any(
        Path(source["file"]).name.startswith("Ef") for source in sources
    )
    is_data = (
        texture["format"] in (0, 1, 2, 3)
        or min(texture["width"], texture["height"]) <= 16
    )
    is_data = is_data or any("font" in kind for kind in kinds) or is_effect
    method = "channels" if is_data else "esrgan"
    reason = (
        "mask, intensity, font, lookup, or effect consistency"
        if is_data
        else "color detail restoration"
    )

    # One hash can be sampled by several materials. Repeat padding is useful at
    # both clamped and repeated seams, so prefer it when any use repeats.
    def sampler(axis):
        values = {source.get(axis) for source in sources}
        return 1 if 1 in values else 2 if 2 in values else 0

    return {
        "method": method,
        "scale": 4,
        "data_channels": is_data,
        "wrap_s": sampler("wrap_s"),
        "wrap_t": sampler("wrap_t"),
        "reason": reason,
    }


def sha256(path):
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def store_result(image, texture, choice, signature, output):
    name = texture["name"]
    png = output / "images" / (name + ".png")
    dds = output / "Textures/GALE01" / (name + ".dds")
    temporary = png.with_suffix(".png.tmp")
    image.save(temporary, format="PNG", compress_level=4)
    temporary.replace(png)
    mip_levels = write_dds(image, dds, choice["data_channels"])
    record = {
        "name": name,
        "signature": signature,
        "source_rgba_sha256": texture["rgba_sha256"],
        "original_size": [texture["width"], texture["height"]],
        "output_size": list(image.size),
        "recipe": choice,
        "png": str(png.relative_to(output)),
        "dds": str(dds.relative_to(output)),
        "png_sha256": sha256(png),
        "dds_sha256": sha256(dds),
        "mip_levels": mip_levels,
        "sources": texture["sources"],
        "png_bytes": png.stat().st_size,
        "dds_bytes": dds.stat().st_size,
    }
    path = output / "records" / (name + ".json")
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(record, separators=(",", ":")) + "\n")
    temporary.replace(path)
    return record


def build(manifest_path, output, models, limit=None, prune=False):
    manifest = json.loads(manifest_path.read_text())
    for directory in ("images", "Textures/GALE01", "records"):
        (output / directory).mkdir(parents=True, exist_ok=True)
    entries = manifest["textures"][:limit]
    if prune and limit is not None:
        raise ValueError("Do not prune a partial manifest run")
    if prune:
        expected = {texture["name"] for texture in entries}
        for path in (output / "records").glob("*.json"):
            if path.stem not in expected:
                # Preserve earlier generated candidates outside the active pack.
                for relative in (
                    Path("records") / path.name,
                    Path("images") / (path.stem + ".png"),
                    Path("Textures/GALE01") / (path.stem + ".dds"),
                ):
                    source = output / relative
                    if source.exists():
                        target = output / "unused-candidates" / relative
                        target.parent.mkdir(parents=True, exist_ok=True)
                        source.replace(target)
    engine = Upscaler(models, tile_size=384)
    pending = []
    reused = 0
    errors = []
    started = time.monotonic()
    # Keep at most four encoded images in flight. GPU inference is sequential
    # to avoid MPS memory spikes, while image compression overlaps inference.
    with ThreadPoolExecutor(max_workers=2) as writers:
        for index, texture in enumerate(entries):
            choice = recipe(texture)
            signature = hashlib.sha256(
                json.dumps(
                    [POLICY_VERSION, texture["rgba_sha256"], choice], sort_keys=True
                ).encode()
            ).hexdigest()
            record_path = output / "records" / (texture["name"] + ".json")
            if record_path.is_file():
                record = json.loads(record_path.read_text())
                if record.get("signature") == signature and all(
                    (output / record[key]).is_file()
                    and sha256(output / record[key]) == record[key + "_sha256"]
                    for key in ("png", "dds")
                ):
                    reused += 1
                    continue
            try:
                with Image.open(manifest_path.parent / texture["path"]) as source:
                    image = engine.upscale_image(
                        source,
                        choice["method"],
                        choice["scale"],
                        wrap_s=choice["wrap_s"],
                        wrap_t=choice["wrap_t"],
                    )
                pending.append(
                    writers.submit(
                        store_result, image, texture, choice, signature, output
                    )
                )
                if len(pending) >= 4:
                    pending.pop(0).result()
            except (OSError, ValueError, RuntimeError) as error:
                errors.append({"name": texture["name"], "error": str(error)})
            if index % 100 == 0 or index + 1 == len(entries):
                print(
                    f"Textures {index + 1}/{len(entries)}, reused {reused}, errors {len(errors)}, {time.monotonic() - started:.1f}s",
                    flush=True,
                )
        for work in pending:
            try:
                work.result()
            except (OSError, ValueError, RuntimeError) as error:
                errors.append({"error": str(error)})
    records = []
    for texture in entries:
        path = output / "records" / (texture["name"] + ".json")
        if path.is_file():
            records.append(json.loads(path.read_text()))
    summary = {
        "policy_version": POLICY_VERSION,
        "source_manifest_sha256": sha256(manifest_path),
        "expected_textures": len(entries),
        "generated_textures": len(records),
        "errors": errors,
        "methods": dict(Counter(record["recipe"]["method"] for record in records)),
        "png_bytes": sum(record["png_bytes"] for record in records),
        "dds_bytes": sum(record["dds_bytes"] for record in records),
        "elapsed_seconds": time.monotonic() - started,
        "extraction_summary": manifest.get("summary"),
        "extraction_warnings": manifest.get("warnings", []),
    }
    (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    (output / "manifest.json").write_text(
        json.dumps(
            {"schema_version": 1, "summary": summary, "textures": records},
            separators=(",", ":"),
        )
        + "\n"
    )
    if errors or len(records) != len(entries):
        raise RuntimeError("Texture build is incomplete. See summary.json.")
    print(
        json.dumps(
            {
                key: value
                for key, value in summary.items()
                if key != "extraction_warnings"
            },
            indent=2,
        ),
        flush=True,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--models", type=Path, required=True)
    parser.add_argument("--limit", type=int)
    parser.add_argument(
        "--prune",
        action="store_true",
        help="Move obsolete generated candidates outside the active pack",
    )
    args = parser.parse_args()
    build(args.manifest, args.output, args.models, args.limit, args.prune)


if __name__ == "__main__":
    main()
