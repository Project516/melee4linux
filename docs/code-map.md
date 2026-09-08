# Code map

Start with the behavior you want to understand. Most game code is under
`src/melee`. HAL's object and graphics library is under
`src/sysdolphin/baselib`. The GameCube SDK is in `extern/dolphin`, with headers
under `extern/dolphin/include/dolphin`. It is separate from the Dolphin emulator.

Use the [build and run guide](build-and-run.md) to verify a matching build
before editing C code. A successful decompilation gives us equivalent
instructions. It does not recover every original name or explain every
field.

## Find a starting point

| Task | Start here | What to follow |
| --- | --- | --- |
| Game startup | [`gm/gmmain.c`](../src/melee/gm/gmmain.c) | `main` initializes hardware, memory, input, and libraries, then calls `gm_801A4510` in [`gm_1A3F.c`](../src/melee/gm/gm_1A3F.c). |
| Fighter creation and frame processing | [`ft/fighter.c`](../src/melee/ft/fighter.c) | `Fighter_Create` registers the ordered callbacks. `Fighter_ChangeMotionState` installs state behavior. `Fighter_procUpdate` and `Fighter_procMap` are useful frame entry points. |
| Jump input and movement | [`ft/kinds/ftCommon/ftCo_Jump.c`](../src/melee/ft/kinds/ftCommon/ftCo_Jump.c) | `ftCo_Jump_GetInput` checks tap jump and X/Y. Follow `ftCo_KneeBend_Enter` for jump startup. |
| A character's special move | [`ft/kinds`](../src/melee/ft/kinds) | Start in that character's directory. For example, [`ftFox/ftfoxspecialn.c`](../src/melee/ft/kinds/ftFox/ftfoxspecialn.c) controls Fox and Falco's blasters. |
| Fighter hits and collision | [`ft/ftcoll.c`](../src/melee/ft/ftcoll.c) | Follow callers in `fighter.c` and the shared types in [`ft/types.h`](../src/melee/ft/types.h). Stage geometry queries live in `mp`. |
| Stage collision geometry | [`mp/mplib.c`](../src/melee/mp/mplib.c) and [`mp/mpcoll.c`](../src/melee/mp/mpcoll.c) | `mpCheckFloor`, `mpCheckCeiling`, and wall queries operate on stage lines. [`mp/types.h`](../src/melee/mp/types.h) defines the collision data. |
| Stage behavior and hazards | [`gr/ground.c`](../src/melee/gr/ground.c) and [`gr`](../src/melee/gr) | Each stage has its own code. [`gronett.c`](../src/melee/gr/gronett.c) is an example. Geometry and models also come from disc assets. |
| Player slots and stale moves | [`pl/player.c`](../src/melee/pl/player.c) and [`pl/plstale.c`](../src/melee/pl/plstale.c) | `plStale_UpdateStaleMovesFromFighter` records attacks. The item path records attacks for the item's owner. |
| Items and projectiles | [`it/item.c`](../src/melee/it/item.c), [`it/itspawn.c`](../src/melee/it/itspawn.c), and [`it/kinds`](../src/melee/it/kinds) | Shared item creation and updates are separate from each item's behavior. Fighter-created projectiles also use this system. |
| Menus and unlock rules | [`mn/mnmain.c`](../src/melee/mn/mnmain.c) and [`gm/gm_1601.c`](../src/melee/gm/gm_1601.c) | Menu code lives in `mn`. `gm_IsCKindUnlocked` answers whether a character is available. |
| Cameras and on-screen interface | [`cm/camera.c`](../src/melee/cm/camera.c) and [`if`](../src/melee/if) | Start here for camera rules and in-game interface changes. Menus use `mn`. |
| Disc files and asset loading | [`lb/lbdvd.c`](../src/melee/lb/lbdvd.c) and [`baselib/archive.c`](../src/sysdolphin/baselib/archive.c) | `HSD_ArchiveParse` reads an archive and relocates its internal references. `HSD_ArchiveGetPublicAddress` finds a named root. |

## Follow a fighter state

Fighters use callback tables. A function can run through a table entry even
when a search finds no direct call. Shared motion states are registered in
[`ftmotionstates.c`](../src/melee/ft/ftmotionstates.c). Their layout is
`MotionState` in [`ft/types.h`](../src/melee/ft/types.h).

Many state functions use these suffixes:

| Suffix | Usual role |
| --- | --- |
| `_Enter` | Set up a transition into the state |
| `_Anim` | Check animation progress and completion |
| `_IASA` | Check input and permitted state interruptions |
| `_Phys` | Update movement |
| `_Coll` | Handle collision for this state |

For a small reading exercise, follow the jump path:

1. Read `ftCo_Jump_GetInput` and its callers.
2. Open [`ftCo_KneeBend.c`](../src/melee/ft/kinds/ftCommon/ftCo_KneeBend.c)
   to see how the game starts a jump.
3. Return to `ftCo_Jump_Enter`. It selects a forward or backward jump and
   calls `Fighter_ChangeMotionState`.
4. Find `ftCo_Jump_Anim` in `ftmotionstates.c`. Read the adjacent input,
   physics, and collision callbacks as a group.

Search both source and the symbol list when following an unfamiliar name:

```sh
rg -n 'ftCo_Jump_GetInput' src config/GALE01/symbols.txt
rg -n 'ftCo_Jump_Anim' src/melee/ft
rg -n 'tap_jump_threshold|tap_jump_window' src/melee/ft
```

To find candidate headers, run:

```sh
python tools/find_include.py Fighter_ChangeMotionState
```

The tool lists headers under `src` with a whole-word match, in path order. Read the
candidates to find the declaration. A match can also be a use or a comment.

The callback order matters. For example, the jump input check tests the
stick before X/Y. A cleanup must preserve that order unless it deliberately
changes gameplay.

## Read the types before guessing names

Modules usually put structure definitions in `types.h`, forward declarations
in `forward.h`, and shared inline helpers in `inlines.h`. Fighter-specific
types also live under `ft/kinds/<character>`.

`HSD_GObj` is the common game object. Its user data holds objects such as a
`Fighter` or `Item`. The existing `GET_FIGHTER` and `GET_ITEM` helpers express
those conversions. HAL's `JObj`, `DObj`, and `TObj` code handles joints,
draw objects, and textures.

Names such as `x671_timer_lstick_tilt_y` retain a structure offset. Names
such as `fn_800CAF78` retain an original code address. These are clues for
research, not placeholders to replace with a guess. Check every read and
write, the caller's behavior, and the data layout before assigning a more
specific meaning. A final executable match proves the instructions stayed
the same. It does not prove a new name is accurate.

[`config/GALE01/symbols.txt`](../config/GALE01/symbols.txt) maps names to
original addresses. [`splits.txt`](../config/GALE01/splits.txt) describes
the original object boundaries. [`configure.py`](../configure.py) selects
source files, compiler settings, and which objects are linked. Use these
files when a source file's role in the build is unclear.

## Separate source behavior from disc data

C code controls game rules, callbacks, state transitions, and asset loading.
Disc archives also contain models, textures, animations, fighter attributes,
and animation commands. A move can combine C callbacks with values loaded
from a `.dat` file.

For example, `ftCo_Jump_GetInput` reads thresholds through
`p_ftCommonData`. Jump velocity uses `fp->co_attrs`. Follow
`Fighter_LoadCommonData` in `fighter.c` and the loading code in
[`ftdata.c`](../src/melee/ft/ftdata.c) before assuming a tuning value is a
C constant.

Source edits require a rebuild and a new `main.dol`. Asset edits require
updated files in the extracted disc directory. This repository does not
generate every disc asset from source.

## Preserve matching controls during cleanup

The matching compiler is sensitive to source structure. Local variable
order, casts, inline functions, stack size, and string contents can change
the output. Even adding lines before an assertion can change a compiled
line number.

[`placeholder.h`](../src/placeholder.h) defines `PAD_STACK` and
`FORCE_PAD_STACK`. They influence compilation. Fox's blaster helper has a
comment explaining why it initializes `fp` twice. Removing these patterns
because they look redundant can break the match.

Keep cleanup small. Explain non-obvious control flow, give a proven local
value a clearer name, or replace a verified offset access with an existing
type. Run the [matching checks](build-and-run.md#make-and-inspect-a-source-change)
after each C change. If the match fails, inspect the changed object before
expanding the edit.
