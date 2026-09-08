# Controller rumble

[`rumble.c`](../../src/sysdolphin/baselib/rumble.c) keeps one script list for
each controller. `HSD_PadRenewRawStatus` in
[`controller.c`](../../src/sysdolphin/baselib/controller.c) runs the rumble
interpreter before reading controller input. Wait counts measure interpreter
updates. This code does not convert them to seconds.

## Entries and priorities

`HSD_PadRumbleInit` receives an array of entries and links it into one shared
free list. The game supplies 12 entries in
[`gmmain.c`](../../src/melee/gm/gmmain.c). No entry allocation occurs during
playback.

`HSD_PadRumbleAdd` takes one free entry, assigns its ID, priority, duration,
and script pointers, then inserts it into the controller's list. It returns
1 on success and 0 when no entry is available or the controller's list is
at its limit. It does not replace an existing script to make room.
The script buffer remains owned by the caller.

`func_80378430_inline` inserts after entries with the same or lower stored
priority. The interpreter visits entries in this order. Each entry that
writes a status replaces the preceding output, so higher numeric priorities
win. Among equal priorities, the newer entry writes last. Lower-priority
scripts still advance while their output is overridden.

`HSD_PadRumbleFree` unlinks an entry and returns it to the shared free list.
Its caller must supply an entry already in that controller's list.
`HSD_PadRumbleRemoveId` removes every matching ID on the selected controller.
The removal loops save the next active entry before returning the current
one to the free list, because the free operation changes its `next` pointer.

## Script words

The parser consumes big-endian 16-bit words. The opcode is the top three
bits of the first byte. The low 13 bits hold a wait or loop count.
The current byte read and halfword read assume GameCube byte order.
The `RumbleCommand` struct in
[`rumble.h`](../../src/sysdolphin/baselib/rumble.h) has separate `u16` fields
and does not describe this packed input format.

| Opcode | Action |
| --- | --- |
| 0 | Finish when `frame == -2`. Otherwise restart at `headp`. |
| 1 | Select rumble and load the wait count. |
| 2 | Select normal stop and load the wait count. |
| 3 | Select hard stop and load the wait count. |
| 4 | Load the loop count and save the next word as the loop start. |
| 5 | Decrement the loop count. Repeat while it is nonzero, otherwise advance. |

Commands are read until `wait` becomes nonzero. The interpreter then writes
the entry's status and decrements `wait`. The single `stack` pointer and
`loop_count` provide one loop state. The parser has no nested loop stack.

Positive `frame` values limit the number of updates that write a status.
`frame == -1` skips that limit and restarts at opcode 0. `frame == -2` skips
the limit but finishes at opcode 0. An entry that reaches a positive frame
limit writes its final status before removal. An entry that finishes at
opcode 0 returns before writing a status.

For an input example, [`mnvibration.c`](../../src/melee/mn/mnvibration.c)
stores `0x20010000` and passes its address with a duration of 14. On GameCube,
those bytes encode a one-update rumble command followed by opcode 0.
[`lb_013B.c`](../../src/melee/lb/lb_013B.c) loads other scripts from the
`lbRumbleData` symbol in `LbRb.dat`. Its wrapper converts a duration of zero
to `-2` before calling `HSD_PadRumbleAdd`.

## Status, pause, and motor output

The internal status values differ from SDK motor commands:

| Internal status | SDK command |
| --- | --- |
| 0 | `PAD_MOTOR_STOP_HARD`, value 2 |
| 1 | `PAD_MOTOR_STOP`, value 0 |
| 2 | `PAD_MOTOR_RUMBLE`, value 1 |

The SDK definitions are in
[`pad.h`](../../extern/dolphin/include/dolphin/pad.h).
`HSD_PadRumbleOn` sets the direct status to normal stop.
`HSD_PadRumbleOffN` sets it to hard stop. Scripts can replace this direct
status during interpretation. `PADControlMotor` is called only when the
final status differs from the previous update.

An entry with `pause == 1` leaves its timers, cursor, and output unchanged.
Other entries can still provide the controller's output.
`HSD_Rumble_80378524` controls the global `unk2` byte. While it is nonzero,
the interpreter skips all scripts and selects hard stop for each controller.
It keeps the entries so playback can resume when the byte becomes zero.
