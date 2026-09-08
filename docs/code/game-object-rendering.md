# Game-object rendering

[`gobjgxlink.c`](../../src/sysdolphin/baselib/gobjgxlink.c) maintains the render
lists. [`gobj.c`](../../src/sysdolphin/baselib/gobj.c) runs their callbacks.
The object layout is in [`gobj.h`](../../src/sysdolphin/baselib/gobj.h).

## List membership and order

Each object can belong to one render list. Its `gx_link` selects that list.
`next_gx` and `prev_gx` connect its neighbors. These links are separate from
`next` and `prev`, which connect objects in a `p_link` list.

`HSD_GObjGXLinkHead[gx_link]` is the first object.
`HSD_GObj_804D7820[gx_link]` is the last object. Both arrays have
`gx_link_max + 2` entries, allocated in
[`gobjinit.c`](../../src/sysdolphin/baselib/gobjinit.c).
The entry at `gx_link_max + 1` is an extra list for callbacks such as cameras.
The ordinary lists use indices from zero through `gx_link_max`.

Objects run in ascending numeric `render_priority`. The insertion functions
handle equal priorities differently:

| Function | Destination | Position among existing equal priorities |
| --- | --- | --- |
| `GObj_SetupGXLink` | Requested ordinary list | After them |
| `GObj_SetupGXLinkMax` | Extra list | After them |
| `GObj_SetupGXLinkMaxSorted` | Extra list | Before them |
| `HSD_GObjGXLink_80390908` | Requested ordinary list | Before them |
| `HSD_GObjGXLink_803909D8` | Another object's list and priority | Directly before that object |

For example, if A and B already have priority 2, setup with
`GObj_SetupGXLink` adds C in the order A, B, C. Moving C with
`HSD_GObjGXLink_80390908` at priority 2 produces C, A, B.
The `Sorted` suffix does not mean the other setup functions are unsorted.
All of them preserve numeric priority order.

Setup functions assign a callback and insert an object. They do not remove
an existing render link first. `HSD_GObjGXLink_8039084C` removes that link,
sets `gx_link` to `HSD_GOBJ_GXLINK_NONE`, and clears render priority and both
render neighbors. It keeps the callback, payload, and `p_link` membership.
The two move functions remove the old render link themselves and retain
the callback. Their input object must already have a render link.
For `HSD_GObjGXLink_803909D8`, the destination must be a different linked object.

`GObj_GXReorder` is the common insertion operation. Its second argument is
the previous object, or NULL to insert at the head. It neither searches by
priority nor removes the object's old link. Keep this distinction when
reading the exported name.

## Callback dispatch

The frame loop in [`gm_1A45.c`](../../src/melee/gm/gm_1A45.c) calls
`HSD_GObj_80390FC0` after `HSD_StartRender`. This walks the extra list from
head to tail and calls each non-NULL callback with argument zero. It saves
and restores `HSD_GObj_804D7818` around each callback.

A camera callback can call `HSD_GObj_80390ED0` to draw selected lists.
That function has two independent masks:

- Its `mask` argument selects callback pass indices. Bit zero calls pass 0,
  bit one calls pass 1, and bit two calls pass 2.
- The object's `gxlink_prios` field selects render-list indices. Despite its
  name, it does not select values of `render_priority`.

Dispatch visits pass indices first, then selected list indices, then each
list from head to tail. `HSD_GObj_80390ED0` reads `gxlink_prios` again at the
start of each selected pass. It skips NULL callbacks and saves and restores
`HSD_GObj_804D7814` around each call.

`HSD_GObj_803910D8` selects the camera, dispatches mask 7, and ends the camera.
The mask calls passes 0, 1, and 2. `HSD_GObj_JObjCallback` maps these indices
through `HSD_GObj_80390EB8` before drawing joints:

| Callback pass index | Joint transparency mask |
| --- | --- |
| 0 | `HSD_TRSP_OPA`, value 1 |
| 1 | `HSD_TRSP_TEXEDGE`, value 4 |
| 2 | `HSD_TRSP_XLU`, value 2 |

The callback argument is an index. Its value is not the joint transparency
mask. Other render callbacks can use the index directly.

## Callers to follow

- [`textdraw.c`](../../src/melee/if/textdraw.c), `DevText_CreateCObj`, adds a
  camera to the extra list and sets one bit in `gxlink_prios`.
- [`grizumi.c`](../../src/melee/gr/grizumi.c), `grIzumi_801CCD98`, inserts the
  reflection camera before other extra-list objects with priority 2.
- [`grlast.c`](../../src/melee/gr/grlast.c), `grLast_8021B920`, moves newly
  created stage objects directly before an existing stage object.
- [`grcorneria.c`](../../src/melee/gr/grcorneria.c) moves a stage object to
  render list 3 with priority zero through `HSD_GObjGXLink_80390908`.
- [`camera.c`](../../src/melee/cm/camera.c) changes `gxlink_prios` between
  calls to `HSD_GObj_80390ED0` to select the lists for each draw operation.

## Matching constraints

Keep the original exported names and the 8-bit `render_priority` field.
Setup functions accept a 32-bit priority, but store it in that field before
they compare it with existing objects.

The two forward searches share `findFirstAtOrAbovePriority`. The backward
searches remain separate. Combining them in one inline helper changed the
original compiler's register choices in `GObj_SetupGXLinkMax`. Simplifying
the first backward loop also changed instructions. The temporary previous
pointer and the no-inline control around `GObj_GXReorder` are retained for
matching.

The cleanup object matched its local baseline byte for byte. This verifies
its instructions, data, and relocations. The complete game still needs the
[integrated build check](../build-and-run.md#build-and-verify-the-original-game).
