# Animation tracks

[`fobj.c`](../../src/sysdolphin/baselib/fobj.c) decodes one animation channel
per `HSD_FObj`. [`aobj.c`](../../src/sysdolphin/baselib/aobj.c) controls the
frame step and loop boundaries for a chain of these tracks. See
[animation playback](animation-playback.md) for that timeline behavior.

## Track storage

`HSD_FObjLoadDesc` allocates a linked chain of track records and copies each
descriptor's settings. It borrows the stream at `desc->ad` rather than
copying its bytes. `ad_head` keeps the stream start, `ad` is the decoder's
current position, and `length` is the stream size in bytes.

The descriptor's floating `startframe` is stored in the track's signed
16-bit `startframe`. `HSD_FObjReqAnimAll` resets each decoder and sets its
time to the requested frame plus this stored offset. It selects
`FOBJ_LOAD_DATA0`, the first data-loading state. A negative time delays
parsing until an interpret call advances it to zero or above.

`HSD_FObjRemove` and `HSD_FObjFree` release one track record.
`HSD_FObjRemoveAll` releases the whole chain. None of these free stream
bytes. The archive or animation buffer that owns the bytes must remain
valid while its tracks use them. Removing a single track does not update
the head or predecessor that points to it.

## Value encoding

`parseFloat` decodes both floating and scaled integer values. Values use the
least significant byte first. This differs from the GameCube byte order
used by [archive metadata](archive-loading.md).

| Format | Bytes consumed | Decoded value |
| --- | --- | --- |
| `HSD_A_FRAC_FLOAT` | 4 | Bits of a 32-bit float |
| `HSD_A_FRAC_S8` | 1 | Signed 8-bit value divided by the scale divisor |
| `HSD_A_FRAC_U8` | 1 | Unsigned 8-bit value divided by the scale divisor |
| `HSD_A_FRAC_S16` | 2 | Signed 16-bit value divided by the scale divisor |
| `HSD_A_FRAC_U16` | 2 | Unsigned 16-bit value divided by the scale divisor |

For integer formats, the high three bits select the type. The low five
bits select the divisor as `1 << (format & 0x1F)`. The signed 16-bit path
sign-extends the high byte before joining it with the low byte.
For example, format `HSD_A_FRAC_S16 | 3` and bytes `F0 FF` decode as
`-16 / 8`, which is `-2.0`. Float bytes `00 00 80 3F` decode as `1.0`.
The track has separate formats for values and slopes in `frac_value`
and `frac_slope`.

## Opcodes and repeat counts

A new group starts with a shared opcode/count byte:

- Bits 0 through 3 select the opcode.
- Bits 4 through 6 contain the low three bits of the repeat count minus one.
- Bit 7 says that another count byte follows.

Each following count byte supplies seven more bits, least significant
group first. Its high bit indicates another continuation byte.
`parseOpCode` reads the opcode without advancing the cursor.
`parsePackInfo` then consumes the shared byte and its count continuation.
For example, `12` selects `HSD_A_OP_LIN` with two repetitions. `F2 01`
selects the same opcode with sixteen repetitions.

`FObjLoadData` stores the count in `nb_pack`, then subtracts one for each
data operation. It reads another opcode/count group when that field is
zero. `HSD_A_OP_CON`, `HSD_A_OP_LIN`, `HSD_A_OP_SPL0`, `HSD_A_OP_SPL`,
`HSD_A_OP_SLP`, and `HSD_A_OP_KEY` select the existing data handlers.
The slope handler reads a slope without advancing the decoder state.
The other handlers select the next state after reading their value data.

## Wait values and updates

`parseWait` uses seven value bits per byte, least significant group first.
Bit 7 means another byte follows. Unlike the repeat count, it starts with
seven value bits and does not add one. Bytes `96 01`, for example, encode
150 frames. `FObjLoadWait` stores this value in the 16-bit `fterm` field
and selects `FOBJ_LOAD_DATA`.

The decoder keeps values in `p0` and `p1` and slopes in `d0` and `d1`.
`FObjUpdateAnim` selects a value according to `op_intrp`, then calls
`obj_update(obj, fobj->obj_type, &update_data)`. The callback uses `obj_type`
to identify the property to change. `update_data` is local to that call.

The interpolation paths in `FObjUpdateAnim` are:

| Opcode | Value sent to the callback |
| --- | --- |
| `HSD_A_OP_CON` | `p0` before `fterm`, then `p1` at or beyond that boundary. |
| `HSD_A_OP_LIN` | `d0 * time + p0`. When flag `0x20` is set, it recalculates the slope. A zero duration sets the slope to zero and replaces `p0` with `p1`. |
| `HSD_A_OP_SPL0`, `HSD_A_OP_SPL`, `HSD_A_OP_SLP` | Hermite interpolation of the values and slopes. A zero duration uses `p1` directly. |
| `HSD_A_OP_KEY` | `p0` when flag `0x80` is set. It clears that flag before the callback. Without the flag, it returns without a callback. |

A NULL update callback returns before this selection and leaves the pending
key flag unchanged. It does not stop the track decoder. A stop call can
flush key data before setting the state to zero. `mn_8022F360` in
[`mn_22EC.c`](../../src/melee/mn/mn_22EC.c) uses this API with a NULL callback
to stop tracks selected by `obj_type`.

## Decoder limits and matching

The low four bits of `flags` hold the decoder state. The state setter
preserves the high four bits. The cleanup uses the existing
`FOBJ_LOAD_DATA0`, `FOBJ_LOAD_DATA`, and `FOBJ_LOAD_WAIT` names and keeps
the other state values unchanged.

The data and wait loaders check the cursor against `length` before they
start parsing. The byte readers do not check each read or limit the number
of continuation bytes. This is a reader for the game's known animation
streams, not a validator for arbitrary input.

The cleanup retains assertion operands and the `MUST_MATCH` assignments
in the interpreter. Its complete object, including data and relocations,
matches the local baseline byte for byte. The integrated batch still needs
the [full executable check](../build-and-run.md#build-and-verify-the-original-game).
