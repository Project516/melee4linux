# Player attack and hit tracking

[`plattack.c`](../../src/melee/pl/plattack.c) resets player counters and allocates
attack instances for statistics. [`pltrick.c`](../../src/melee/pl/pltrick.c)
records attack use, hits, and information used by the bonus code.

This is separate from the [stale-move queue](stale-moves.md). Fighter statistics
use `x2070` and `x2074.x2088`. Stale moves use `x2068_attackID` and
`x206C_attack_instance`. Both systems allocate 16-bit instance values, but they
have separate counters.

## Types and callers

| Source | What to follow |
| --- | --- |
| [pl/forward.h](../../src/melee/pl/forward.h) | `plStats_Attack` names the attack IDs used by the counters. |
| [pl/types.h](../../src/melee/pl/types.h) | `plActionStats` contains attack counts, hit counts, flags, and hit-player masks. |
| [ft/types.h](../../src/melee/ft/types.h) | `Struct2070` holds the attack ID and category flags. `ft_800898B4_t` holds hit metadata. |
| [ft_0892.c](../../src/melee/ft/ft_0892.c) | `ft_800895E0` assigns fighter attack events and allocates an instance when the attack ID changes or is zero. |
| [ftcoll.c](../../src/melee/ft/ftcoll.c) | `ftColl_8007861C` sets damage-source fields and calls `pl_80038144`. |
| [it_279C.c](../../src/melee/it/it_279C.c) | `it_8027B564` records an item's attack for its fighter owner. Other item paths call `pl_800384DC` to record hits. |
| [plbonus.c](../../src/melee/pl/plbonus.c) | Bonus checks read the counters and query which players an attack has hit. |

## Counting attacks

`pl_80037C60` compares the current attack ID with the previous event supplied by
the caller. It counts a nonzero ID when that ID changes. `pl_80037DF4` records
the supplied event without that comparison.

For attack IDs below `StatsAttack_Count`, each counted event increments the
total and its per-attack counter. Its category flags can also increment
thrown-item, aerial, and special counters. A single event can increment more
than one category. The `count_x1A0` and `count_x1A4` flags still have uncertain
meanings, so their names remain unchanged.

`pl_80037C60` has a separate path for higher attack IDs. It increments
`by_attack_hi` when the fighter's `x221F_b4` flag is clear. That path does not
increment the total or the ordinary per-attack counters.

`plAttack_8003759C` clears the specified player's counter groups and selected
flags. It does not clear every byte in `plActionStats`. For example, it does not
write `x5B8`. Replacing the resets with a whole-structure clear would change this
behavior.

## Recording fighter hits

`pl_80038144` receives the attacker, victim, packed attack event, hit metadata,
attack instance, and previous source player. Its `grounded` argument is passed
by the collision code but is unused in this function.

The function records a new instance when it differs from the victim's last
recorded instance. Instance zero always enters this path. For a tracked attack,
it updates the attacker's `hits` counters and may also update `x358_hits`.
The latter update requires a clear `x10_b7` metadata flag and a per-attack count
below the number of recorded uses. This describes the check without assigning
a broader meaning to the partly understood structure.

The hit-player mask at `x504[attack_id]` records one bit per victim player.
`pl_80037B2C` queries that mask. Its caller must supply an attack ID within
`StatsAttack_Count` and a player index from zero through seven. The function
returns the selected bit, not a normalized boolean.

The private `fn_80037F00` copies hit metadata to the victim and updates its
flags. It reads the attacker through `Fighter*`. `Fighter.gobj` is the first
field, which explains the old cast from `Fighter*` to `HSD_GObj**`.

## Matching constraints

The small `countHitStats` wrapper adds an inline level around `pl_80037BC0`.
Removing it caused the compiler to expand the counter updates at call sites
and changed both hit-recording functions. Keep it during matching cleanup.

The repeated counter updates in the attack-recording functions also remain.
Moving them into one shared helper changed which function the compiler called.
Replacing the packed-event casts with integer-member assignments changed the
compiled output as well. These shapes need a fresh matching check if changed.

Some hit paths test metadata for null and later read it without another check.
Those tests do not establish that null is valid for every call. Keep the
existing call contracts and investigate callers before changing them.
