# Heap lifecycle

[`lbheap.c`](../../src/melee/lb/lbheap.c) manages six heap slots. A slot index
is different from the SDK heap ID stored in `Heap.id`. Public calls expect a
slot index from 0 through 5.

## Slots and allocation results

The layout table configures slots 2 through 5. Rebuilding the heaps configures
the two reserved slots, 0 and 1.

| Slot | Printed name | Type | Storage | Result of `lbHeap_80015BD0` |
| --- | --- | --- | --- | --- |
| 0 | Hsd | 0 | Current HSD main RAM heap. | Data address. |
| 1 | ARAM | 3 | Remaining ARAM range. | ARAM address stored as `void*`. |
| 2 | Seq | 1 | `0x800` bytes at the low end of main RAM. | Allocation descriptor. |
| 3 | Stay | 1 | `0x4F8800` bytes after slot 2. | Allocation descriptor. |
| 4 | AllM | 2 | `0x64B400` bytes at the high end of main RAM. | Allocation descriptor. |
| 5 | AllA | 4 | `0x96C800` bytes at the low end of ARAM. | Allocation descriptor. |

Type 0 uses the SDK heap allocator through `HSD_MemAlloc` and `HSD_Free`.
The other types use [`lbmemory.c`](../../src/melee/lb/lbmemory.c). For type 3,
the wrapper extracts the descriptor's `x4_lo` address before returning.
Types 1, 2, and 4 return the descriptor itself.

Allocation from a destroyed slot returns NULL. The allocation function does
not create a heap on demand. Freeing requires a created heap and always takes
the data address. For slots 2 through 5, pass the descriptor's address field,
not the descriptor pointer. The preload code in
[`lbdvd.c`](../../src/melee/lb/lbdvd.c) follows this distinction when it frees
`entry->archive->addr` and `entry->raw_data->addr`.

## Initialization and scene changes

`lbHeap_80015F3C` reads the main RAM and ARAM bounds and resets all slots to
`LbHeapStatus_Destroy`. It sets each `transient` flag to 1, then calculates
the configured ranges for slots 2 through 5. It does not create their heap
handles yet. The layout's `prev_idx == 6` selects an arena boundary. Other
values place a heap relative to the indicated slot.

`lbHeap_800158D0` only changes a slot's `transient` flag. For slots 2 through 5,
the next `lbHeap_80015900` call uses these exact values:

| Value | Rebuild behavior |
| --- | --- |
| 0 | Reserve the configured range, retain an existing heap, or create it if destroyed. |
| 1 | Destroy the heap if created and return its range to the reserved heaps. |

The preload scene transition in `lbDvd_80018CF4` sets these flags, waits for
pending work on heaps marked for destruction, then calls `lbHeap_80015900`.
The rebuild runs in this order:

1. Destroy created heaps marked transient in slots 2 through 5.
2. Start from the stored arena bounds and exclude ranges whose flags are 0.
   Type 1 advances the main RAM low bound. Type 2 lowers its high bound.
   Type 4 advances the ARAM low bound.
3. Recreate slot 0 through `HSD_CreateMainHeap` and slot 1 through the default
   ARAM handle functions in `lbmemory.c`.
4. Create any destroyed heap whose flag is 0. Already created heaps keep
   their allocation records and storage addresses.

`LbHeapStatus_Create` is numerically 0, and `LbHeapStatus_Destroy` is 1.
Keep that distinction when reading callers that test the status as a boolean.

## Compaction and memory accounting

`lbHeap_80015D6C` returns 0 without calling back for slots 0 and 1. For slots
2 through 5, it delegates compaction to `lbMemory_8001529C`. Its final argument
is passed to the completion callback unchanged. The DVD caller passes the
heap index, but the wrapper does not interpret that argument as another heap.

For slots 2 through 5, a return of 1 means that compaction started. A return
of 0 means no copy was needed. See the [allocator guide](memory-allocator.md)
for descriptor updates, copy timing, and callback ownership.

Allocation, release, and compaction entry points save and disable interrupts,
then restore the saved state. The type 0 allocation and release paths also
save and restore the current HSD heap ID around their SDK calls.

`lbHeap_80015DF8` reports used and free bytes per slot. It gets free bytes from
`OSCheckHeap` for type 0 and sums free gaps through `lbMemory_80014F7C` for the
other types.

## Matching details

All private heap declarations now live in `lbheap.c`. No other source file
included the removed `lbheap.static.h`. The field offsets on `Heap` are
relative to that structure, starting at zero.

The rebuild loops retain `lbHeap_HeapOffsetView`. Its `heap` field begins
`0x10` bytes after the view address. `lbHeap_HeapViewOffset` uses `offsetof`
to calculate the view address for an array slot. The destruction check now
reads through that type instead of adding a literal `0x10` and casting again.

The end of a reserved range uses `uintptr_t`, like the stored start address.
This avoids narrowing an address through `s32` on a wider host. The GameCube
object remains identical. Keep the local name `p` in the release assertion
because the original expression is part of the executable's strings.
