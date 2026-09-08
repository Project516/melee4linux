# Animation playback

[`aobj.c`](../../src/sysdolphin/baselib/aobj.c) controls an animation timeline.
Its `HSD_AObj` stores the current frame, playback rate, loop range, flags, and
a linked chain of `HSD_FObj` tracks. Each track in
[`fobj.c`](../../src/sysdolphin/baselib/fobj.c) decodes values and sends them
to an object update callback. The [track guide](animation-tracks.md) explains
stream bytes, packed counts, wait times, and value decoding.

## Request, advance, and stop

`HSD_AObjAlloc` starts with `AOBJ_NO_ANIM` set and a playback rate of 1.0.
`HSD_AObjReqAnim(aobj, frame)` starts or restarts playback. It stores the
requested frame, clears `AOBJ_NO_ANIM`, sets `AOBJ_FIRST_PLAY`, and resets
each track's decoder to that frame.

The first `HSD_AObjInterpretAnim` call clears `AOBJ_FIRST_PLAY` and passes a
zero frame step to the tracks. It does not add the playback rate to
`curr_frame`. Later calls add `framerate` to `curr_frame` and use that rate
as the track step. Loop and end checks still apply on the first call.
A NULL AObj or an AObj with `AOBJ_NO_ANIM` set returns before processing.

`HSD_AObjSetCurrentFrame` requests another frame only while playback is
active. It leaves a stopped AObj unchanged. Use `HSD_AObjReqAnim` when a
stopped animation must start again.

`HSD_AObjStopAnim` stops every track and sets `AOBJ_NO_ANIM`. A track stop
can interpret pending key data before it stops. It is not just a flag write.

## Loop boundaries and flags

The loop branch runs when `AOBJ_LOOP` is set and
`curr_frame >= end_frame`. If `rewind_frame < end_frame`, it stops the old
track states, then wraps the frame with:

```text
loop_length = end_frame - rewind_frame
loop_offset = curr_frame - rewind_frame
curr_frame = fmodf(loop_offset, loop_length) + rewind_frame
```

It requests the wrapped frame on every track. A step that crosses more
than one loop keeps the remainder. If `rewind_frame >= end_frame`, it sets
`curr_frame` to `end_frame` without stopping and requesting the tracks.
Both branches then use a zero track step and set `AOBJ_REWINDED`.
An interpret call that does not enter the loop branch clears that flag.

Without `AOBJ_LOOP`, reaching the end first interprets the tracks, then
stops them and sets `AOBJ_NO_ANIM`. This path does not clamp `curr_frame`
to `end_frame`.

The public flag setters change only `AOBJ_LOOP` and `AOBJ_NO_UPDATE`.
Playback functions manage the other flags. `HSD_AObjLoadDesc` uses the same
setter, so loading descriptor flags does not clear the allocator's initial
`AOBJ_NO_ANIM` flag.

`AOBJ_NO_UPDATE` passes NULL as the callback for the main track
interpretation call. The frame and track decoders still advance. The
separate stop calls at a loop boundary or at the end still receive the
original callback, which can be called when pending key data is flushed.
Do not treat `AOBJ_NO_UPDATE` as a guarantee that all updates are suppressed.

## End callback counters

`HSD_AObjInitEndCallBack` resets two counters. An interpret call that reaches
its end increments one counter according to its final `AOBJ_NO_ANIM` flag:

| Counter | Condition |
| --- | --- |
| `HSD_AObj_804D762C` | Playback is stopped |
| `HSD_AObj_804D7630` | Playback remains active |

These count processed calls since the reset. They do not count every
allocated AObj. Already stopped AObjs return early and do not contribute.
`HSD_AObjStopAnim` does not update the counters itself.

`HSD_AObjInvokeCallBacks` walks `endcallback_list` only if at least one
processed call ended stopped and none ended active. It does not clear the
counters. [`HSD_JObjAnimAll`](../../src/sysdolphin/baselib/jobj.c) resets them,
animates the joint hierarchy and its attached objects, then invokes the
callbacks. The current source has no function that adds entries to the
private `endcallback_list`. `_HSD_AObjForgetMemory` clears it and ignores
its range arguments.

## Track and joint ownership

`HSD_AObjSetFObj` frees the old track chain before assigning the supplied
chain. The new chain must not reuse nodes from the old one. It does not
copy the chain or request a playback frame. With a NULL AObj it does
nothing, so the caller retains the supplied chain.

`HSD_AObjLoadDesc` loads a track chain from the descriptor. If `obj_id` is
nonzero, it looks up that ID in the default ID table. An existing object
gets another reference. Otherwise, the loader treats `obj_id` as a joint
descriptor address and loads that joint. The resulting reference is stored
in `hsd_obj`.

`HSD_AObjRemove` frees all track nodes, releases the attached joint reference,
and frees the AObj. `HSD_AObjFree` frees only the AObj record. Track nodes
refer to animation stream data through `ad_head`. Their removal does not
free those stream bytes.

[`lbanim.c`](../../src/melee/lb/lbanim.c), `lbAnim_8001E6D8` and
`lbAnim_8001E7E8`, builds track chains from fighter animation data and gives
them to `HSD_AObjSetFObj`. [`jobj.c`](../../src/sysdolphin/baselib/jobj.c)
requests frames and interprets them with `JObjUpdateFunc`.
[`gmcamera.c`](../../src/melee/gm/gmcamera.c) uses `HSD_ForeachAnim` with
`TOBJ_MASK` and `HSD_AObjStopAnim` to stop texture animation after sampling
a frame.

## Matching constraints

The cleanup keeps the exported functions, data layouts, address-based
static names, and the no-inline control around `HSD_AObjInterpretAnim`.
The repeated AObj checks in `HSD_AObjRemove` remain because removing them
changed the original compiler's instructions.

The edited object is byte-for-byte identical to its local baseline.
Accept an integrated batch only after the
[full executable check](../build-and-run.md#build-and-verify-the-original-game).
