"""Inventory and decode Melee textures from an extracted disc.

HSD descriptors are found through the archive relocation table, not arbitrary
byte patterns. Palette links use HSD_TObjDesc, HSD_SObjDesc and HSD_TexAnim.
Particle banks have their own relative pointers and are parsed separately.
Original images and manifests belong in an ignored build directory.
"""

import argparse
from collections import Counter, defaultdict
from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import struct

from .decode import decode_texture
from .extract_animation import animation_pairs
from .texture_formats import FORMATS, PALETTED, dolphin_name, texture_size


def u32(data: bytes, offset: int) -> int:
    return struct.unpack_from(">I", data, offset)[0]


@dataclass
class Archive:
    data: bytes
    offset: int
    size: int
    relocations: set[int]
    symbols: dict[int, list[str]]
    references: dict[int, list[int]]


def parse_archive(data: bytes, offset: int = 0) -> Archive:
    if offset + 32 > len(data):
        raise ValueError("Truncated HSD archive header")
    size, data_size, n_reloc, n_public, n_external = struct.unpack_from(
        ">5I", data, offset
    )
    tables_end = 32 + data_size + n_reloc * 4 + (n_public + n_external) * 8
    if size < tables_end or offset + size > len(data):
        raise ValueError("Invalid HSD archive bounds")
    body = data[offset + 32 : offset + 32 + data_size]
    rel_at = offset + 32 + data_size
    relocations = set(struct.unpack_from(f">{n_reloc}I", data, rel_at))
    references = defaultdict(list)
    for pointer in relocations:
        if pointer + 4 > data_size:
            raise ValueError("Invalid HSD relocation position")
        target = u32(body, pointer)
        if target > data_size:
            raise ValueError("HSD relocation points outside archive data")
        references[target].append(pointer)
    public_at = rel_at + n_reloc * 4
    symbols_at = offset + tables_end
    symbols = defaultdict(list)
    for i in range(n_public):
        target, name_offset = struct.unpack_from(">II", data, public_at + i * 8)
        if target > data_size or symbols_at + name_offset >= offset + size:
            raise ValueError("Invalid HSD public symbol")
        end = data.find(b"\0", symbols_at + name_offset, offset + size)
        if end < 0:
            raise ValueError("Unterminated HSD public symbol")
        symbols[target].append(
            data[symbols_at + name_offset : end].decode("ascii", errors="replace")
        )
    return Archive(body, offset, size, relocations, dict(symbols), dict(references))


def archive_chunks(data: bytes) -> list[Archive]:
    """Fighter AJ files contain a sequence of 32-byte-aligned HSD archives."""
    archives = []
    offset = 0
    while offset < len(data):
        if not any(data[offset : offset + 32]):
            if any(data[offset:]):
                raise ValueError(f"Unexpected data after archive at 0x{offset:x}")
            break
        archive = parse_archive(data, offset)
        archives.append(archive)
        offset = (offset + archive.size + 31) & ~31
    return archives


def image_descriptors(archive: Archive) -> dict[int, dict]:
    data = archive.data
    found = {}
    for offset in sorted(archive.relocations):
        if offset + 24 > len(data):
            continue
        image, width, height, fmt, mipmap, low, high = struct.unpack_from(
            ">IHHIIff", data, offset
        )
        if (
            fmt not in FORMATS
            or image % 32
            or not 1 <= width <= 1024
            or not 1 <= height <= 1024
            or mipmap not in (0, 1)
            or not 0 <= low <= high <= 10
            or (not mipmap and high != 0)
        ):
            continue
        size = texture_size(width, height, fmt)
        if image + size > len(data):
            continue
        # Every static descriptor has a pointer owner or an exported symbol.
        if offset not in archive.references and offset not in archive.symbols:
            continue
        found[offset] = dict(
            image_offset=image,
            descriptor_offset=offset,
            width=width,
            height=height,
            format=fmt,
            mipmap=bool(mipmap),
            max_lod=high,
            kind="hsd_image",
            wrap_s=None,
            wrap_t=None,
        )
    return found


def palette_descriptor(archive: Archive, offset: int) -> dict | None:
    if offset not in archive.relocations or offset + 16 > len(archive.data):
        return None
    image, fmt, name, entries = struct.unpack_from(">IIIH", archive.data, offset)
    if (
        fmt not in (0, 1, 2)
        or not 1 <= entries <= 16384
        or image + entries * 2 > len(archive.data)
    ):
        return None
    return dict(palette_offset=image, palette_format=fmt, palette_entries=entries)


def hsd_textures(archive: Archive) -> tuple[list[dict], list[str]]:
    images = image_descriptors(archive)
    palettes = defaultdict(list)
    warnings = []
    data = archive.data
    boundaries = set(archive.references) | set(archive.symbols)
    for offset, image in images.items():
        for ref in archive.references.get(offset, []):
            is_tobj = False
            tobj = ref - 0x4C
            if tobj >= 0 and tobj + 0x5C <= len(data):
                texid, texsrc = struct.unpack_from(">II", data, tobj + 8)
                wrap_s, wrap_t = struct.unpack_from(">II", data, tobj + 0x34)
                mag = u32(data, tobj + 0x48)
                if (
                    texid < 8
                    and texsrc <= 20
                    and wrap_s <= 2
                    and wrap_t <= 2
                    and mag <= 1
                ):
                    is_tobj = True
                    image["wrap_s"], image["wrap_t"] = wrap_s, wrap_t
            # Avoid mistaking adjacent image/palette arrays for a sprite.
            is_sprite = ref in boundaries
            if (is_tobj or is_sprite) and ref + 4 in archive.relocations:
                palette = palette_descriptor(archive, u32(data, ref + 4))
                if palette:
                    palettes[offset].append(palette)

    defaults = defaultdict(list)
    for offset, variants in palettes.items():
        image = images[offset]
        defaults[(image["image_offset"], image["format"])].extend(variants)

    # HSD_TexAnim owns counted image and palette pointer arrays. Animation can
    # select either index independently, so retain every palette variant.
    for owner in sorted(archive.relocations):
        table = u32(data, owner)
        if (
            table + 4 > len(data)
            or u32(data, table) not in images
            or owner < 12
            or owner + 12 > len(data)
        ):
            continue
        n_images, n_palettes = struct.unpack_from(">HH", data, owner + 8)
        anim = owner - 12
        if not 1 <= n_images <= 4096 or n_palettes > 4096 or u32(data, anim + 4) >= 8:
            continue
        if table + n_images * 4 > len(data):
            continue
        image_offsets = [u32(data, table + i * 4) for i in range(n_images)]
        if not all(
            table + i * 4 in archive.relocations and offset in images
            for i, offset in enumerate(image_offsets)
        ):
            continue
        for offset in image_offsets:
            images[offset]["kind"] = "hsd_animation"
        if n_palettes:
            if owner + 4 not in archive.relocations:
                continue
            palette_table = u32(data, owner + 4)
            if palette_table + n_palettes * 4 > len(data):
                continue
            variants = [
                palette_descriptor(archive, u32(data, palette_table + i * 4))
                for i in range(n_palettes)
            ]
            if any(p is None for p in variants):
                continue
            pairs = animation_pairs(data, anim, n_images, n_palettes)
            if pairs is None:
                warnings.append(
                    f"Conservative palette combinations for animation 0x{anim:x}"
                )
                pairs = [(i, p) for i in range(n_images) for p in range(n_palettes)]
            for image_index, palette_index in pairs:
                palettes[image_offsets[image_index]].append(variants[palette_index])
        else:
            # A TexAnim with no palette track retains its TObj's palette. Its
            # default image also occurs in the animation's image table.
            variants = []
            for offset in image_offsets:
                image = images[offset]
                variants.extend(defaults[(image["image_offset"], image["format"])])
            for offset in image_offsets:
                palettes[offset].extend(variants)

    # Several animations contain unused duplicate descriptors. A texture that
    # shares the same encoded image can reuse its already verified palettes.
    shared = defaultdict(list)
    for offset, variants in palettes.items():
        image = images[offset]
        shared[
            (image["image_offset"], image["width"], image["height"], image["format"])
        ].extend(variants)
    results = []
    for offset, image in images.items():
        if image["format"] not in PALETTED:
            results.append(image)
            continue
        variants = {tuple(sorted(p.items())): p for p in palettes[offset]}
        if not variants:
            key = (
                image["image_offset"],
                image["width"],
                image["height"],
                image["format"],
            )
            variants = {tuple(sorted(p.items())): p for p in shared[key]}
            if variants:
                image["palette_link"] = "shared_image"
            else:
                warnings.append(
                    f"No linked palette for HSD image descriptor 0x{offset:x}"
                )
        for palette in variants.values():
            results.append(image | palette)
    return results, warnings


def particle_textures(archive: Archive) -> tuple[list[dict], list[str]]:
    """Read HSD_PSTexGroup tables, including separate animation palettes."""
    data = archive.data
    banks = {}
    for offset, names in archive.symbols.items():
        for name in names:
            if name == "map_texg":
                banks[offset] = name
            elif (
                name.startswith("eff")
                and name.endswith("DataTable")
                and offset + 4 in archive.relocations
            ):
                banks[u32(data, offset + 4)] = name
    results, warnings = [], []
    for base, symbol in banks.items():
        try:
            count = u32(data, base)
            if count > 4096 or base + 4 + count * 4 > len(data):
                raise ValueError("Invalid particle group table")
            for group_index in range(count):
                relative = u32(data, base + 4 + group_index * 4)
                if not relative:
                    continue
                group = base + relative
                num, fmt, palette_format, width, height, palnum, palflag = (
                    struct.unpack_from(">5IHH", data, group)
                )
                # psdisp.c casts this field to u8. Some banks set upper bits.
                palette_format &= 255
                if (
                    num > 4096
                    or fmt not in FORMATS
                    or not 1 <= width <= 1024
                    or not 1 <= height <= 1024
                    or (fmt in PALETTED and palette_format not in (0, 1, 2))
                ):
                    raise ValueError(f"Invalid particle group {group_index}")
                n_palettes = (
                    (1 if palflag & 1 else palnum or num) if fmt in PALETTED else 0
                )
                if group + 24 + (num + n_palettes) * 4 > len(data):
                    raise ValueError("Particle table extends outside archive")
                variants = []
                for i in range(n_palettes):
                    palette_rel = u32(data, group + 24 + (num + i) * 4)
                    if palette_rel:
                        variants.append(
                            dict(
                                palette_offset=base + palette_rel,
                                palette_entries={8: 16, 9: 256, 10: 16384}[fmt],
                                palette_format=palette_format,
                            )
                        )
                if fmt in PALETTED and not variants:
                    warnings.append(
                        f"No particle palettes in {symbol} group {group_index}"
                    )
                for i in range(num):
                    image_rel = u32(data, group + 24 + i * 4)
                    if not image_rel:
                        continue
                    item = dict(
                        image_offset=base + image_rel,
                        descriptor_offset=group,
                        width=width,
                        height=height,
                        format=fmt,
                        mipmap=False,
                        kind="particle",
                        group=group_index,
                        frame=i,
                        wrap_s=None,
                        wrap_t=None,
                        symbols=[symbol],
                    )
                    (
                        results.extend(item | palette for palette in variants)
                        if variants
                        else results.append(item)
                    )
        except (ValueError, struct.error) as error:
            warnings.append(f"{symbol}: {error}")
    return results, warnings


def extract_disc(
    files: Path, output: Path, dol: Path | None = None, include: list[str] | None = None
) -> dict:
    output.mkdir(parents=True, exist_ok=True)
    image_dir = output / "originals"
    image_dir.mkdir(exist_ok=True)
    entries, reports, warnings = {}, [], []
    source_counts = Counter()
    paths = sorted(p for p in files.rglob("*") if p.is_file())
    if include:
        paths = [p for p in paths if any(p.match(pattern) for pattern in include)]
    if dol:
        paths.append(dol)

    def save(
        data: bytes,
        item: dict,
        file: str,
        base: int = 0,
        symbols: list[str] | None = None,
    ):
        width, height, fmt = item["width"], item["height"], item["format"]
        start = item["image_offset"]
        size = texture_size(width, height, fmt)
        encoded = item.get("encoded_data", data[start : start + size])
        palette = None
        if "palette_offset" in item:
            at = item["palette_offset"]
            if not 0 <= at < len(data):
                raise ValueError(f"Palette pointer 0x{at:x} is outside archive data")
            # GXLoadTlut transfers the region size, not n_entries. Padding
            # indices can therefore read entries beyond the declared count.
            capacity = {8: 16, 9: 256, 10: 16384}[fmt]
            palette = data[at : at + capacity * 2]
        name = dolphin_name(
            encoded, width, height, fmt, item.get("mipmap", False), palette
        )
        source = {
            k: v
            for k, v in item.items()
            if k not in ("encoded_data", "width", "height", "format", "mipmap")
        }
        source["file"] = file
        for key in ("image_offset", "descriptor_offset", "palette_offset"):
            if key in source:
                source[key] += base
        source["symbols"] = sorted(set(source.get("symbols", []) + (symbols or [])))
        if name not in entries:
            image = decode_texture(
                encoded, width, height, fmt, palette, item.get("palette_format", 2)
            )
            path = f"originals/{name}.png"
            image.save(output / path, compress_level=4)
            entries[name] = dict(
                name=name,
                path=path,
                width=width,
                height=height,
                format=fmt,
                format_name=FORMATS[fmt],
                mipmap=item.get("mipmap", False),
                rgba_sha256=hashlib.sha256(image.tobytes()).hexdigest(),
                sources=[],
            )
        entries[name]["sources"].append(source)
        if (
            item.get("mipmap")
            and item.get("max_lod", 0)
            and not entries[name].get("mip_levels")
        ):
            mip_start = start + size
            levels = []
            for level in range(
                1,
                min(math.ceil(item["max_lod"]), max(width, height).bit_length() - 1)
                + 1,
            ):
                mip_width, mip_height = max(1, width >> level), max(1, height >> level)
                mip_size = texture_size(mip_width, mip_height, fmt)
                if mip_start + mip_size > len(data):
                    raise ValueError(f"Truncated mip level {level}")
                mip_image = decode_texture(
                    data[mip_start : mip_start + mip_size],
                    mip_width,
                    mip_height,
                    fmt,
                    palette,
                    item.get("palette_format", 2),
                )
                mip_path = f"original_mips/{name}_mip{level}.png"
                (output / "original_mips").mkdir(exist_ok=True)
                mip_image.save(output / mip_path, compress_level=4)
                levels.append(
                    dict(
                        level=level,
                        width=mip_width,
                        height=mip_height,
                        path=mip_path,
                        encoded_offset=mip_start + base,
                        encoded_size=mip_size,
                    )
                )
                mip_start += mip_size
            entries[name]["mip_levels"] = levels
        source_counts[item["kind"]] += 1
        return name

    for index, path in enumerate(paths):
        file = (
            str(path.relative_to(files))
            if path.is_relative_to(files)
            else "sys/" + path.name
        )
        data = path.read_bytes()
        report = dict(
            file=file,
            size=len(data),
            sha256=hashlib.sha256(data).hexdigest(),
            textures=0,
            warnings=[],
        )
        descriptors = []
        try:
            if path.suffix.lower() in (".dat", ".usd"):
                archives = archive_chunks(data)
                report["archives"] = len(archives)
                report["status"] = "parsed_hsd"
                for archive in archives:
                    hsd, hw = hsd_textures(archive)
                    particles, pw = particle_textures(archive)
                    report["warnings"].extend(hw + pw)
                    covered = {i["image_offset"] for i in hsd + particles}
                    for offset, names in archive.symbols.items():
                        if (
                            any(n.endswith("_image") for n in names)
                            and offset not in covered
                        ):
                            report["warnings"].append(
                                f"Exported image lacks descriptor at 0x{offset:x}: {names}"
                            )
                    for item in hsd + particles:
                        symbols = archive.symbols.get(
                            item["image_offset"], []
                        ) + archive.symbols.get(item["descriptor_offset"], [])
                        descriptors.append(
                            (archive.data, item, archive.offset + 32, symbols)
                        )
            elif path.suffix.lower() in (".ssm", ".hps", ".sem", ".ini"):
                report["status"] = "non_texture"
            elif path.suffix.lower() in (".thp", ".mth"):
                report["status"] = "runtime_video_planes"
            else:
                report["status"] = "unrecognized"
            try:
                from .extract_special import special_textures
            except ImportError:
                special_textures = None
            if special_textures:
                special, special_warnings = special_textures(path, data)
                report["warnings"].extend(special_warnings)
                descriptors.extend((data, item, 0, []) for item in special)
                if special and report["status"] == "unrecognized":
                    report["status"] = "parsed_special"
            for source_data, item, base, symbols in descriptors:
                try:
                    save(source_data, item, file, base, symbols)
                    report["textures"] += 1
                except (ValueError, KeyError, IndexError) as error:
                    report["warnings"].append(
                        f"{item['kind']} at 0x{item['image_offset'] + base:x}: {error}"
                    )
        except (ValueError, struct.error) as error:
            report["status"] = "parse_error"
            report["warnings"].append(str(error))
        warnings.extend(
            {"file": file, "message": warning} for warning in report["warnings"]
        )
        reports.append(report)
        if (index + 1) % 50 == 0 or len(paths) < 20:
            print(
                f"Extracted {index + 1}/{len(paths)} files, {len(entries)} unique textures",
                flush=True,
            )
    manifest = dict(
        schema_version=1,
        textures=sorted(entries.values(), key=lambda item: item["name"]),
        files=reports,
        warnings=warnings,
        summary=dict(
            unique_textures=len(entries),
            texture_references=sum(source_counts.values()),
            source_kinds=dict(source_counts),
            file_statuses=dict(Counter(r["status"] for r in reports)),
        ),
    )
    temporary = output / "manifest.json.tmp"
    temporary.write_text(json.dumps(manifest, indent=2) + "\n")
    os.replace(temporary, output / "manifest.json")
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--files", type=Path, required=True, help="Extracted disc files directory"
    )
    parser.add_argument(
        "--output", type=Path, required=True, help="Ignored output directory"
    )
    parser.add_argument("--dol", type=Path)
    parser.add_argument(
        "--include", action="append", help="Optional file glob for a sample pass"
    )
    args = parser.parse_args()
    manifest = extract_disc(args.files, args.output, args.dol, args.include)
    print(json.dumps(manifest["summary"], indent=2))
    print(f"Warnings: {len(manifest['warnings'])}")


if __name__ == "__main__":
    main()
