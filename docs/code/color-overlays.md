# Color overlay commands

[`lb_013B.c`](../../src/melee/lb/lb_013B.c) runs color animation scripts and
provides a few rumble wrappers. The names below describe the checked source.
They do not claim to recover the original function names.

[`ColorOverlay`](../../src/melee/lb/types.h) contains a command cursor, wait
timer, animation selection, and two sets of RGBA channels. Each set has byte
channels for rendering, float channels for accumulation, and float steps for
blending. `x7C_color_enable` controls the first set. `x7C_flag2` controls the
light color set.

## Update order

`lb_80014258` performs these operations on each call:

1. If the cursor is not null, subtract one from a nonzero wait timer.
2. While the cursor is not null and the timer is zero, read the six-bit opcode.
   Pass opcodes below `0x0A` to
   [`Command_Execute`](../../src/melee/lb/lbcommand.c). Dispatch `0x0A` through
   `0x14` through `lb_803BA248`. Pass later opcodes to the caller's callback.
3. Add each enabled color set's steps to its float channels, then convert the
   results to bytes.
4. Subtract one from a nonzero duration. Return true if it reaches zero.

Opcode `0x0A` returns true during step 2. That return skips both the color
update and duration decrement. Shared opcode `0x00` only clears the cursor.
It does not make this function return true. Color blending and the duration
countdown can continue when the cursor is null.

The existing `CommandInfo*` cast gives shared commands and caller callbacks
access to the command cursor and loop storage. It does not convert timer
values. `CommandInfo` declares float timers, while `ColorOverlay` declares
integer timers. Do not assume that the two types are interchangeable for all
shared commands. The overlay has its own integer wait command at `0x0B`.

## Overlay opcode table

Each word is four bytes. "Words consumed" is the amount added to the cursor
by the handler, including its command word. The dispatch table has extra null
entries, but the dispatcher uses only these eleven handlers.

| Opcode | Handler | Words consumed | Operation |
| --- | --- | --- | --- |
| `0x0A` | `lb_80013BB0` | 0 | Return true without advancing the cursor |
| `0x0B` | `lb_80013BB8` | 1 | Add the low 26 bits to the integer wait timer |
| `0x0C` | `lb_80013BE4` | 1 | Disable both color sets |
| `0x0D` | `lb_80013C18` | 2 | Read the light mode and angles, load RGBA, and enable the light color set |
| `0x0E` | `lb_80013D68` | 2 | Load light RGBA without changing its enable flag |
| `0x0F` | `lb_80013E3C` | 2 | Calculate light color blend steps |
| `0x10` | `lb_80013F78` | 1 | Change the light angles |
| `0x11` | `lb_80013FF0` | 1 | Disable the light color set |
| `0x12` | `lb_80014014` | 2 | Load RGBA and enable the first color set |
| `0x13` | `lb_800140F8` | 2 | Calculate blend steps for the first color set |
| `0x14` | `lb_80014234` | 1 | Disable the first color set |

The RGBA load commands copy the next word into the byte channels, copy those
bytes into the float channels, and set all four steps to zero. The private
`readLightColor` helper shares that operation between `0x0D` and `0x0E`.

The blend commands read a duration from the low 26 bits and target RGBA from
the next word. For each channel, the step is:

```text
((0.5 + target byte) - current byte) / blend duration
```

The current value in this formula is the byte channel, not its float
accumulator. Keep the expression order and `0.5f` term. The handler does not
set a wait timer, enable the color set, validate a zero duration, or stop the
blend after that duration. Later commands control those actions. This matters
when reading or changing a script.

Opcode `0x0D` reads signed 12-bit angles. Opcode `0x10` reads signed 13-bit
angles. The fighter light code in
[`ftCo_09F4.c`](../../src/melee/ft/kinds/ftCommon/ftCo_09F4.c) converts the stored
angles from degrees and sets the light position. That code also shows why
`x7C_light_enable` must not be treated as the light set's enable flag. It
selects between light rendering paths after `x7C_flag2` permits the update.
The field names and bit layout remain unchanged.

## Selection, duration, and reset

`lb_800144C8` takes an animation table, an animation index, and a duration.
It compares the selected entry's `unk4` with the candidate entry's `unk4`.
An equal or higher candidate value permits replacement. The entry's `unk`
field supplies the script pointer.

On replacement, the function saves the index and duration, sets the cursor,
clears the wait timer and loop count, and disables both color sets. It leaves
their channel values and steps in place. The script can initialize those
values when it starts.

The stored duration uses the field named `x4_pri`. This field is a countdown
in `lb_80014258`. The replacement priority comes from the table instead.
A zero duration disables the duration countdown. These field names remain
unchanged because they are shared with other files.

`lb_80014498` clears the cursor, duration, animation selection, and both color
enable flags. It does not clear the whole struct. Callers in
[`ftcolanim.c`](../../src/melee/ft/ftcolanim.c) and
[`itanimlist.c`](../../src/melee/it/itanimlist.c) use a true update result to
reset the overlay. Fighter callers can then select another persistent effect.
[`grmaterial.c`](../../src/melee/gr/grmaterial.c) also runs overlay scripts,
but initializes the cursor directly instead of using the animation table.

## Rumble wrappers

`lb_80014534` loads the `lbRumbleData` table from `LbRb.dat`.
`lb_80014574` selects a table entry by `rumble_id` and passes its script and
priority to [`HSD_PadRumbleAdd`](../../src/sysdolphin/baselib/rumble.c).
Its separate `id` argument identifies the queued rumble entry.

A zero duration becomes the rumble interpreter's `-2` value. That value lets
the script run until its end command without restarting it. Other durations
are passed through unchanged. `lb_800145C0` removes queued rumble entries and
sets rumble on for one controller slot. `lb_800145F4` applies that operation
to all controller slots.

## Matching check

The cleanup preserves exported symbols and the shared types. The private
helper expands inline without changing the generated instructions, data,
symbol addresses, or resolved relocations. The compiler changes only some
generated literal names and their symbol-table order in the object file.
Use the [full build verification](../build-and-run.md#build-and-verify-the-original-game)
after integration to check the final executable and source completion.
