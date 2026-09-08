# Stale moves

The stale-move code records attacks for each player. The damage code uses that
history to reduce damage when a move appears in recent entries.

## Where to start

| File | Responsibility |
| --- | --- |
| [plstale.c](../../src/melee/pl/plstale.c) | Allocate attack instances, clear the queue, and record hits. |
| [pl/types.h](../../src/melee/pl/types.h) | Define `StaleMoveTable` and its ten stored entries. |
| [player.c](../../src/melee/pl/player.c) | Return the player's table through `Player_GetStaleMoveTableIndexPtr`. |
| [ft_0881.c](../../src/melee/ft/ft_0881.c) | Assign fighter attack IDs and instances, then calculate the damage multiplier. |
| [ftcoll.c](../../src/melee/ft/ftcoll.c) | Call the queue writers during hit processing. |

## Recording a hit

Each queue entry has two values. `move_id` identifies the move.
`attack_instance` distinguishes uses of a move. The queue rejects an entry only
when both values match an entry already stored.

`plStale_IncrementAttackInstance` returns the current 16-bit counter, then
advances it. It skips zero when the counter wraps. Clearing the queue sets both
values in every entry to zero and resets `current_index` to zero.

The two public queue writers choose the player and attack values:

- `plStale_UpdateStaleMovesFromFighter` reads the attacking fighter. It skips
  calls where attacker and victim are the same object.
- `plStale_UpdateStaleMovesFromItem` reads the item attack values, but records
  them in its owner's queue. The owner must be a fighter and must differ from
  the victim. `ftLib_80086960` checks that the owner is a non-null fighter object.

Both writers use the private `recordStaleMove` helper. Attack ID `1` does not
enter the queue. For other IDs, the helper checks all ten entries for a duplicate.
If none matches, it writes at `current_index`, then advances that index with
wraparound. `current_index` is the next write position, not the newest entry.

## Ten stored entries, nine damage checks

The storage and damage loops use different limits. Keep that distinction when
reading or changing this code.

`StaleMoveTable.StaleMoves` has ten entries, and the queue writer checks all ten.
The damage helper `ft_80089118` starts one entry before `current_index` and walks
back through at most nine entries. For each matching move ID, it subtracts
`Fighter_804D6548[i]` from a multiplier that starts at `1.0F`. It stops early at
an entry with move ID zero. Attack ID `1` returns `1.0F` directly.

The damage calculation compares move IDs only. Attack instances prevent
duplicate queue writes. They do not affect the damage multiplier directly.

`ft_80089228` applies the multiplier to the supplied damage. It bypasses the
calculation when `DbLevel` is at least `DbLKind_DebugRom`.

These facts describe the current source. They do not establish why the original
game stores a tenth entry, so do not reduce the array or duplicate check to nine
as a cleanup.
