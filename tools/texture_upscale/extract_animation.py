"""Resolve HSD texture animation indices without inventing palette variants.

The descriptor layout and stream encoding come from baselib/tobj.h, fobj.h
and fobj.c. Constant tracks and a repeated terminal SPL0 key are accepted.
Other interpolation modes, missing tracks and malformed data return None.
"""

from bisect import bisect_right
import math
import struct


class _Unsupported(ValueError):
    pass


class _Stream:
    def __init__(self, data: bytes):
        self.data = data
        self.offset = 0

    def byte(self) -> int:
        if self.offset >= len(self.data):
            raise _Unsupported("Truncated animation stream")
        value = self.data[self.offset]
        self.offset += 1
        return value

    def integer(self, value: int = 0, shift: int = 0) -> int:
        while shift < 32:
            byte = self.byte()
            value |= (byte & 127) << shift
            if not byte & 128:
                return value
            shift += 7
        raise _Unsupported("Animation integer is too large")

    def number(self, encoding: int) -> float:
        if encoding == 0:
            value = struct.unpack("<f", bytes(self.byte() for _ in range(4)))[0]
        else:
            kind = encoding & 224
            if kind not in (32, 64, 96, 128):
                raise _Unsupported("Unknown animation number encoding")
            size = 2 if kind in (32, 64) else 1
            raw = bytes(self.byte() for _ in range(size))
            value = int.from_bytes(raw, "little", signed=kind in (32, 96))
            value /= 1 << (encoding & 31)
        if not math.isfinite(value):
            raise _Unsupported("Nonfinite animation value")
        return value


def _constant_keys(data: bytes, offset: int, count: int) -> list[tuple[int, int]]:
    _, length, start, _, encoding, _, _, stream_at = struct.unpack_from(
        ">IIf4BI", data, offset
    )
    # HSD_FObjLoadDesc stores the descriptor float in a signed 16-bit field.
    # A negative start leaves the prior TObj index active for an unknown time.
    if not math.isfinite(start) or not 0 <= start < 32768:
        raise _Unsupported("Unknown initial animation index")
    if not length or stream_at + length > len(data):
        raise _Unsupported("Invalid animation stream bounds")
    stream = _Stream(data[stream_at:stream_at + length])
    time = -int(start)
    remaining = 0
    keys = []
    previous_value = None
    while stream.offset < length:
        if not remaining:
            header = stream.byte()
            if header == 3 and len(keys) >= 2:  # One terminal HSD_A_OP_SPL0 key.
                value = stream.number(encoding)
                wait = stream.integer() if stream.offset < length else 0
                if value == previous_value and wait == 0 and stream.offset == length:
                    # FObjLoadData keeps the prior CON in op_intrp. End of
                    # stream returns before the terminal SPL0 can replace it.
                    return keys
                raise _Unsupported("Spline key is not a terminal constant repeat")
            if header & 15 != 1:  # HSD_A_OP_CON
                raise _Unsupported("Texture index track is not constant")
            packed = (header >> 4) & 7
            if header & 128:
                packed = stream.integer(packed, 3)
            remaining = packed + 1
            if remaining > 65535:
                raise _Unsupported("Animation repeat count exceeds u16")
        value = stream.number(encoding)
        index = int(value)  # TObjUpdateFunc truncates the float index.
        if not 0 <= index < count:
            raise _Unsupported("Animation index is outside its table")
        keys.append((time, index))
        previous_value = value
        remaining -= 1
        if stream.offset == length:
            break  # HSD permits the final key to omit its wait.
        wait = stream.integer()
        if wait > 65535:
            raise _Unsupported("Animation wait exceeds u16")
        time += wait
    if remaining or len(keys) < 2:
        # Constant interpolation needs the next key to set op_intrp.
        raise _Unsupported("Incomplete constant animation")
    return keys


def animation_pairs(
    data: bytes, anim_offset: int, image_count: int, palette_count: int
) -> list[tuple[int, int]] | None:
    """Return image/palette pairs selected by two constant HSD index tracks.

    Offsets refer to the archive data section, without its 32-byte header.
    The result covers all nonnegative times in the encoded tracks, including
    their final held values. Static TObj palettes need separate extraction.
    None means the pairing cannot be proved with this decoder.
    """
    if anim_offset < 0 or not 1 <= image_count <= 4096 or not 1 <= palette_count <= 256:
        return None
    try:
        aobj = struct.unpack_from(">I", data, anim_offset + 8)[0]
        if not aobj:
            return None
        fobj = struct.unpack_from(">I", data, aobj + 8)[0]
        visited = set()
        tracks = {}
        while fobj:
            if fobj in visited:
                return None
            visited.add(fobj)
            next_fobj, _, _, kind, _, _, _, _ = struct.unpack_from(
                ">IIf4BI", data, fobj
            )
            if kind in (1, 10):  # HSD_A_T_TIMG and HSD_A_T_TCLT
                if kind in tracks:
                    return None
                tracks[kind] = _constant_keys(
                    data, fobj, image_count if kind == 1 else palette_count
                )
            fobj = next_fobj
        if set(tracks) != {1, 10}:
            return None
        image_keys, palette_keys = tracks[1], tracks[10]
        image_times = [time for time, _ in image_keys]
        palette_times = [time for time, _ in palette_keys]
        times = {0, *(time for time in image_times + palette_times if time >= 0)}
        return sorted({
            (
                image_keys[bisect_right(image_times, time) - 1][1],
                palette_keys[bisect_right(palette_times, time) - 1][1],
            )
            for time in times
        })
    except (struct.error, _Unsupported):
        return None
