# Controller input

[`controller.c`](../../src/sysdolphin/baselib/controller.c) queues raw controller
samples, converts them to usable input, and keeps button history for three
status arrays. The SDK's [`PADStatus`](../../extern/dolphin/include/dolphin/pad.h)
contains one controller's raw values. One `HSD_PadData` contains a sample for
all four controllers.

## Sampling and queue storage

`HSD_PadInit` takes caller-owned storage and its capacity in samples. The
capacity must be nonzero because queue indices advance with a remainder
operation. Melee supplies five samples in
[`gmMain_8015FD24`](../../src/melee/gm/gmmain.c).

The queue fields in `HSD_PadLibData` describe a circular queue:

| Field | Meaning |
| --- | --- |
| `qnum` | Capacity in complete four-controller samples |
| `qread` | Index of the oldest unread sample |
| `qwrite` | Index for the next write |
| `qcount` | Number of unread samples |
| `qtype` | Behavior when a new sample arrives at a full queue |

`HSD_PadRenewRawStatus` first updates rumble and calls `PADRead`. If
`skip_if_all_invalid` is true and every controller has an error, it returns
before queue writes or reset checks. Existing game callers pass false.

When the queue is full, `qtype` selects the following behavior:

| Value | Behavior |
| --- | --- |
| `0` | Merge the oldest sample's buttons into the next oldest sample, then replace the oldest slot with the new sample. |
| `1` | Discard the oldest sample and store the new sample. |
| `2` | Keep the queued samples and discard the new sample. Still perform reset checks. |

The merge operation changes only button bits. Analog values and errors stay
with the destination sample. With a capacity of one, mode `0` merges the old
buttons into the new sample instead. This preserves the new analog values.

`HSD_PadFlushQueue` performs an explicit flush under disabled interrupts.
`MERGE` combines all queued button bits into the newest sample. `THROWAWAY`
empties the queue. `LEAVE1` keeps only the newest sample without merging.
These are flush operations, separate from the `qtype` overflow behavior.

## Updating controller status

`HSD_PadRenewMasterStatus` removes one queued sample. For a controller with no
error, it copies the raw values, clamps analog input, adds stick-direction
button bits, scales the analog values, then applies the D-pad direction rule.
If the queue is empty, it leaves the master status unchanged.

`PAD_ERR_TRANSFER` preserves that controller's previous inputs and clears the
error. Other errors clear its input values. This distinction also affects
button releases and repeat timing, so keep it when changing error handling.

`HSD_PadRenewCopyStatus` and `HSD_PadRenewGameStatus` each copy the current master
inputs, then update their own button history. Their `trigger`, `release`, and
`repeat_count` fields are not copied from the master array.

The private `updateButtonHistory` helper serves all three arrays. A changed
button mask records presses and releases and restarts `repeat_start`.
An unchanged mask decrements the counter. When it reaches zero, the held
buttons repeat and the counter resets to `repeat_interval`. These counts
advance when the relevant update function runs.

## Callers and reset handling

[`lb_0195.c`](../../src/melee/lb/lb_0195.c) schedules raw reads through an alarm
callback, consumes queued samples through `lb_800198E0`, and updates the copy
and game arrays through `lb_80019900`. The scene loop in
[`gm_1A45.c`](../../src/melee/gm/gm_1A45.c) waits for queued samples.

`HSD_PadRenewStatus` provides a combined call that runs raw, master, copy, and
game updates in that order. Some trophy code uses this entry point directly.

After sampling, disconnected controllers contribute to a `PADReset` channel
mask. The console reset-switch flag becomes set after the SDK reports a
held-to-released transition. `HSD_PadReset` clears that flag, flushes queued
samples, stops rumble, and recalibrates all four channels.

## Matching constraints

Queue copies use `HSD_PadData` directly. Queue reads use `queue[index].stat`,
which keeps indexing within the declared arrays. Both changes reproduce the
original object bytes.

Sharing button-history code makes two status-update functions small enough
for the matching compiler to inline into `HSD_PadRenewStatus`. Its local
`dont_inline` control preserves the original four calls. It does not apply
to non-matching builds.

The float formulas, casts, and operation order in the clamp and analog-to-button
conversion code remain unchanged. Reordering them needs separate matching
and behavior checks.
