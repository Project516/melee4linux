# Shared commands and counter helpers

## Command streams

[`lbcommand.c`](../../src/melee/lb/lbcommand.c) handles opcodes 0 through 9
for both fighter and item animation scripts. `Command_Execute` returns
`false` for higher opcodes without changing the command state. The caller
then dispatches or skips its own commands. See
[`ftaction.c`](../../src/melee/ft/ftaction.c) and
[`itanimlist.c`](../../src/melee/it/itanimlist.c).

`CommandInfo.u` is the stream cursor. `NEXT_CMD` moves it by one command
word. Commands 5 and 7 read a target address from the word after their
opcode. Command 5 also saves the address after that target word so that
command 6 can return to it.

`loop_count` acts as a stack index for `event_return`. A loop pushes two
entries, the body address followed by the remaining count. A subroutine
pushes one return address onto the same stack. The count is stored in a
pointer-typed slot, but command 4 subtracts one from its numeric value.
Pointer subtraction would instead subtract the size of a command word.
The declared stack size in [`types.h`](../../src/melee/lb/types.h) is still
marked as uncertain. These handlers do not check stack bounds.

The caller owns the timer loop. It reduces `timer` by the animation speed
and processes commands while the result is non-positive. Command 1 adds a
relative delay, so any overshoot remains in the timer. Command 2 sets the
timer to an absolute target frame minus `frame_count`.

Command 8 advances the cursor and sets `timer` to `F32_MAX`. The callers
treat this as a special wait state. They resume when `frame_count` is below
one animation-speed step, then set the timer to `-frame_count`. `F32_MAX`
is a marker here, not a long countdown.

## Counter arithmetic and OS time

Despite its name, [`lbtime.c`](../../src/melee/lb/lbtime.c) also updates
bounded counters. Calls in
[`gmvsmelee.c`](../../src/melee/gm/gmvsmelee.c) use the 8-bit helper for KO
counts. [`gm_17C0.c`](../../src/melee/gm/gm_17C0.c) uses the 32-bit helper
when accumulating match results.

| Function | Operation |
| --- | --- |
| `lbTime_8000AEC8` | Add an unsigned increment, stopping at `U32_MAX`. |
| `lbTime_8000AEE4` | Add a signed delta, stopping at zero or `U32_MAX`. |
| `lbTime_8000AF24` | Apply a signed delta to a 16-bit counter, stopping at zero or `U16_MAX`. |
| `lbTime_8000AF74` | Apply a signed delta to an 8-bit counter, stopping at zero or `U8_MAX`. |
| `lbTime_GetTimeInSeconds` | Convert `OSGetTime()` ticks to seconds and cap the result at `U32_MAX`. |
| `lbTime_8000B028` | Convert seconds to ticks, then fill an `OSCalendarTime`. |

The narrow counter helpers check the low 16 or 8 bits of `value`, but return
the full `value + delta` when no limit is reached. Their input must already
fit the counter width. They do not normalize arbitrary 32-bit input.
The signed-delta expressions also negate negative values. Negating
`INT_MIN` is not portable C. This cleanup preserves the original operations
and does not add support for that input.

`lbTime_8000B028` casts seconds to 64 bits before multiplying by the tick
rate. Keep that conversion order. Moving the cast after the multiplication
would let a 32-bit intermediate overflow.
