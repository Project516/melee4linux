# Memory allocator

[`lbmemory.c`](../../src/melee/lb/lbmemory.c) manages allocation descriptors
for address ranges in ARAM or main RAM. It does not obtain new backing memory
when creating a heap. [`lbheap.c`](../../src/melee/lb/lbheap.c) supplies the
bounds and selects this allocator or the SDK heap allocator.

## Heap handles and allocation descriptors

The public `Handle*` type represents two different records. Keep their uses
separate when reading a field.

| Field | Heap handle | Allocation descriptor |
| --- | --- | --- |
| `x0_next` | Next handle while on the free heap list. | Next live allocation or next free descriptor. |
| `x4_lo` | Low bound of the heap. | Start address of the allocation. |
| `x8_hi` | Exclusive high bound of the heap. | Allocation size stored in a pointer field. |
| `xC_prev` | First live allocation. | Not present in the 12-byte descriptor. |

The global allocator stores six heap handles and 131 allocation descriptors.
All heaps share these descriptor pools. Initialization creates one default
ARAM heap. Heap setup releases that handle with `lbMemory_800155A4`, then
stores a replacement with `lbMemory_800154D4`.

Allocation descriptors use the first three fields of `Handle`, backed by the
private `MemEntry` array. Do not read `xC_prev` from an allocation returned by
`lbMemory_80014FC8`. Do not change the descriptor stride to `sizeof(Handle)`.

## Allocation and release

| Function | Work |
| --- | --- |
| `lbMemory_80014E24` | Create a heap handle for supplied bounds. |
| `lbMemory_80014EEC` | Release a heap handle and all its allocation descriptors. |
| `lbMemory_80014F7C` | Add the sizes of every free gap in a heap. |
| `lbMemory_80014FC8` | Round the size to 32 bytes and allocate from the best-fitting gap. |
| `lbMemFreeToHeap` | Find an allocation by its start address and release its descriptor. |
| `lbMemory_800154BC` | Return the usable ARAM bounds stored during initialization. |

The live allocation list stays in address order. Allocation scans the gap
before the first allocation, between allocations, and after the last one.
It selects the fitting gap with the smallest leftover size. If two gaps have
equal leftover sizes, the later gap wins. An empty descriptor pool or a lack
of a fitting gap causes an assertion.

`lbMemory_80014FC8` returns the descriptor, not the data address. Use its
`x4_lo` field for the address. The ARAM path in `lbHeap_80015BD0` does this
conversion for its callers. Release takes the data address, not the descriptor.

`lbMemFreeToHeap` walks a `Handle**` link. The link can be `heap->xC_prev` or
the preceding allocation's `x0_next`. This lets one assignment remove either
the first allocation or a later allocation. Freeing a descriptor does not
move other live allocations or clear their bytes.

## Compaction

`lbMemory_8001529C` packs allocations toward the heap's low bound. It first
skips allocations that already have the correct address. If every allocation
is already packed, it returns 0 and does not call the supplied callback.
Otherwise, it starts the copy chain and returns 1.

The allocator stores the next destination address and final callback in
global state. `lbMemory_80015320` advances through the allocation list. It
changes each descriptor's address before starting its copy. After the final
copy, it calls `callback(callback_arg)`. Callers must wait for completion
before using moved data. Compaction operations share one state and must not
overlap.

The copy path depends on the destination address:

- Below `0x80000000`, `HSD_DevComRequest` type `0x1B` copies ARAM data through
  a main RAM relay buffer. See the `0x1B` path in
  [`devcom.c`](../../src/sysdolphin/baselib/devcom.c).
- At or above `0x80000000`, `start_ram_copy` schedules an alarm after 3 ms.
  Each alarm copies up to `0x19000` bytes, which is 100 KiB. It schedules
  another alarm if bytes remain, then advances the compaction chain.

The `lbHeap` wrappers save and disable interrupts around allocator operations.
The compaction callbacks run later. The allocator does not maintain a separate
copy manager for each heap.

## Matching constraints

Keep the original names inside assertions, including `memp_kouho`, `p`,
`arenaLo`, and `arenaHi`. Their expressions become strings in the executable.
`memp_kouho` holds the predecessor for the selected allocation gap.

The free-space and allocation scans view the heap's link to the first
allocation as a predecessor node. Only `x0_next` is read through that view. Changing
the free-space scan to separate `Handle**` and `Handle*` locals adds a register
move. The release function can use a typed link without that change.

The two assignments that calculate `leftover` affect register allocation.
Combining them changes the generated instructions. The explicit heap-pool
offset writes during initialization also remain for matching.

The cleanup preserves the object code and data. Converting the free-space
scan from a `goto` to a loop changes compiler-generated local symbol numbers.
Compare resolved relocations as well as section bytes, then run the complete
executable check in the [build guide](../build-and-run.md).
