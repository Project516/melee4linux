"""Check a generated pack against its sources and write sampled contact sheets."""

import argparse
import hashlib
import json
import struct
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw


def file_hash(path):
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def dds_layout(data):
    """Validate the legacy RGBA8 DDS layout independently of the writer."""
    if len(data) < 128 or data[:4] != b"DDS ":
        raise ValueError("Missing DDS header")
    header = struct.unpack_from("<31I", data, 4)
    if header[0] != 124 or header[18] != 32:
        raise ValueError("Invalid DDS header size")
    if header[19:26] != (0x41, 0, 32, 0xFF, 0xFF00, 0xFF0000, 0xFF000000):
        raise ValueError("DDS does not use the expected RGBA8 channel masks")
    height, width, levels = header[2], header[3], header[6]
    if not width or not height or header[4] != width * 4:
        raise ValueError("Invalid DDS dimensions or row pitch")
    expected_levels = max(width, height).bit_length()
    if levels != expected_levels:
        raise ValueError("DDS does not contain a complete mip chain")
    offset = 128
    result = []
    for _ in range(levels):
        size = width * height * 4
        if offset + size > len(data):
            raise ValueError("Truncated DDS mip data")
        result.append(
            np.frombuffer(data, np.uint8, count=size, offset=offset).reshape(
                (height, width, 4)
            )
        )
        offset += size
        width, height = max(1, width // 2), max(1, height // 2)
    if offset != len(data):
        raise ValueError("Unexpected bytes after DDS mip chain")
    return result


def check_texture(texture, source_directory, pack):
    name = texture["name"]
    errors = []
    record_path = pack / "records" / f"{name}.json"
    if not record_path.is_file():
        return {"name": name, "errors": ["Missing generation record"]}
    try:
        record = json.loads(record_path.read_text())
        png_path, dds_path = (pack / record[key] for key in ("png", "dds"))
        for key, path in (("png", png_path), ("dds", dds_path)):
            if file_hash(path) != record[f"{key}_sha256"]:
                errors.append(f"{key.upper()} checksum differs from generation record")
        with Image.open(source_directory / texture["path"]) as image:
            source = np.asarray(image.convert("RGBA"))
        if hashlib.sha256(source.tobytes()).hexdigest() != texture["rgba_sha256"]:
            errors.append("Decoded source checksum differs from extraction manifest")
        with Image.open(png_path) as image:
            if image.mode != "RGBA":
                errors.append("Output PNG is not RGBA")
            output = np.asarray(image.convert("RGBA"))
        expected = (
            texture["height"] * record["recipe"]["scale"],
            texture["width"] * record["recipe"]["scale"],
            4,
        )
        if output.shape != expected:
            errors.append("Output dimensions do not match the selected scale")
        levels = dds_layout(dds_path.read_bytes())
        if levels[0].shape != output.shape or not np.array_equal(levels[0], output):
            errors.append("DDS base pixels differ from PNG")
        if len(levels) != record["mip_levels"]:
            errors.append("DDS mip count differs from generation record")
        if np.all(source[:, :, 3] == 255) and any(
            not np.all(level[:, :, 3] == 255) for level in levels
        ):
            errors.append("Opaque texture acquired transparency")
        if not source[:, :, 3].any() and any(level[:, :, 3].any() for level in levels):
            errors.append("Empty alpha acquired visible pixels")
        if record["recipe"]["data_channels"]:
            for first in range(4):
                for second in range(first + 1, 4):
                    if np.array_equal(
                        source[:, :, first], source[:, :, second]
                    ) and any(
                        not np.array_equal(level[:, :, first], level[:, :, second])
                        for level in levels
                    ):
                        errors.append(
                            f"Equal data channels {first} and {second} diverged"
                        )
        coverage_delta = float(
            np.mean(output[:, :, 3]) / 255 - np.mean(source[:, :, 3]) / 255
        )
        reduced = np.asarray(
            Image.fromarray(output).resize(
                (source.shape[1], source.shape[0]), Image.Resampling.BOX
            ),
            dtype=np.float32,
        )
        source_float = source.astype(np.float32)
        weight = source_float[:, :, 3:4] / 255
        color_mae = float(
            np.sum(np.abs(reduced[:, :, :3] - source_float[:, :, :3]) * weight)
            / max(float(weight.sum() * 3), 1)
        )
        return {
            "name": name,
            "errors": errors,
            "method": record["recipe"]["method"],
            "coverage_delta": round(coverage_delta, 6),
            "color_mae": round(color_mae, 3),
            "mip_levels": len(levels),
        }
    except (OSError, ValueError, KeyError, TypeError) as error:
        return {"name": name, "errors": [*errors, str(error)]}


def category(texture):
    kinds = {source["kind"] for source in texture["sources"]}
    files = [source["file"] for source in texture["sources"]]
    if any("font" in kind for kind in kinds):
        return "font"
    if "particle" in kinds or any(name.startswith("Ef") for name in files):
        return "effect"
    for prefix, label in (
        ("Pl", "fighter"),
        ("Gr", "stage"),
        ("Mn", "menu"),
        ("Ty", "trophy"),
        ("If", "hud"),
        ("It", "item"),
    ):
        if any(name.startswith(prefix) for name in files):
            return label
    return "other"


def sample_textures(textures, per_category):
    groups = defaultdict(list)
    for texture in textures:
        groups[category(texture)].append(texture)
    selection = {}
    for label, entries in sorted(groups.items()):
        # A fixed hash order makes repeated audits select the same source assets.
        entries.sort(
            key=lambda texture: hashlib.sha256(texture["name"].encode()).digest()
        )
        selection[label] = entries[:per_category]
    return selection


def contacts(selection, source_directory, pack, destination):
    recorded = {}
    for label, textures in selection.items():
        cell = 256
        columns = 2
        rows = (len(textures) + columns - 1) // columns
        sheet = Image.new("RGB", (cell * 2 * columns, (cell + 42) * rows), "black")
        draw = ImageDraw.Draw(sheet)
        for index, texture in enumerate(textures):
            x = (index % columns) * cell * 2
            y = (index // columns) * (cell + 42)
            record_path = pack / "records" / f"{texture['name']}.json"
            record = (
                json.loads(record_path.read_text()) if record_path.exists() else None
            )
            output = pack / record["png"] if record else None
            paths = [source_directory / texture["path"], output]
            for half, path in enumerate(paths):
                if path is None or not path.exists():
                    continue
                with Image.open(path) as image:
                    image = image.convert("RGBA")
                    factor = min(cell / image.width, cell / image.height)
                    image = image.resize(
                        (round(image.width * factor), round(image.height * factor)),
                        Image.Resampling.NEAREST
                        if half == 0
                        else Image.Resampling.LANCZOS,
                    )
                    sheet.paste(
                        image,
                        (
                            x + half * cell + (cell - image.width) // 2,
                            y + (cell - image.height) // 2,
                        ),
                        image,
                    )
            source_name = texture["sources"][0]["file"]
            draw.text(
                (x + 4, y + cell + 4),
                f"{source_name}  {texture['width']}x{texture['height']} {texture['format_name']}",
                fill="white",
            )
            draw.text(
                (x + 4, y + cell + 20),
                f"Original | {record['recipe']['method'] if record else 'missing'}  {texture['name'][5:37]}",
                fill="white",
            )
        sheet.save(destination / f"contact-{label}.png")
        recorded[label] = [texture["name"] for texture in textures]
    return recorded


def audit(manifest_path, pack, destination, per_category=12, workers=4):
    manifest = json.loads(manifest_path.read_text())
    textures = manifest["textures"]
    destination.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(
            pool.map(
                lambda texture: check_texture(texture, manifest_path.parent, pack),
                textures,
            )
        )
    failures = [result for result in results if result["errors"]]
    measured = [result for result in results if "coverage_delta" in result]
    report = {
        "expected_textures": len(textures),
        "checked_textures": len(measured),
        "failed_textures": len(failures),
        "failures": failures,
        "methods": dict(Counter(result["method"] for result in measured)),
        "largest_color_changes": sorted(
            measured, key=lambda result: result["color_mae"], reverse=True
        )[:32],
        "largest_alpha_changes": sorted(
            measured, key=lambda result: abs(result["coverage_delta"]), reverse=True
        )[:32],
    }
    report["contact_samples"] = contacts(
        sample_textures(textures, per_category), manifest_path.parent, pack, destination
    )
    (destination / "quality.json").write_text(json.dumps(report, indent=2) + "\n")
    print(
        json.dumps(
            {
                key: report[key]
                for key in (
                    "expected_textures",
                    "checked_textures",
                    "failed_textures",
                    "methods",
                )
            },
            indent=2,
        )
    )
    return not failures


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--pack", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--samples-per-category", type=int, default=12)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    raise SystemExit(
        0
        if audit(
            args.manifest,
            args.pack,
            args.output,
            args.samples_per_category,
            args.workers,
        )
        else 1
    )


if __name__ == "__main__":
    main()
