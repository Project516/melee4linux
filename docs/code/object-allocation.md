# Object pools and hash lookup

[`objalloc.c`](../../src/sysdolphin/baselib/objalloc.c) manages reusable pools
for objects of one size. Fighters, items, lists, animation objects, and other
subsystems each pass their own `HSD_ObjAllocData` record.

## Pool storage

`HSD_ObjAllocInit` clears an allocator record and adds it to the allocator
registry. It rounds `size` up to the requested alignment and stores that
stride in `data->size`. The `data->align` field stores alignment minus one,
which the allocator uses as a bit mask. In the GameCube build, callers use
alignments of 4 or 32 bytes.

Each free object's first word stores the next `HSD_ObjAllocLink`. Allocating
an object removes it from the free list. Freeing it puts it back at the head
of that list. The allocator does not clear object data. For example,
[`HSD_SListAlloc`](../../src/sysdolphin/baselib/list.c) clears the returned
object separately.

`HSD_ObjAllocAddFree` obtains a new block, links its objects in address order,
and connects its last object to the
existing free list. If a caller supplies a fixed arena with `HSD_ObjSetHeap`,
the block can contain fewer objects than requested. The function returns
the actual count added. `HSD_ObjAlloc` requests one object when its free list
is empty.

`HSD_ObjSetHeap` selects the source of new blocks:

| `ptr` | Source of new storage | Available memory used by the heap limit |
| --- | --- | --- |
| Non-NULL | The supplied arena. The allocator advances its cursor and aligns each block. | Remaining arena bytes. |
| NULL | `HSD_MemAlloc` from the current HSD heap. | `OSCheckHeap(HSD_GetHeap())`. |

Both calls in [`initialize.c`](../../src/sysdolphin/baselib/initialize.c)
select the current HSD heap with `ptr == NULL`. `HSD_ObjFree` keeps objects
in their pool. It does not return their storage to the backing heap.

The counters have separate meanings:

- `used` counts allocated objects.
- `free` counts reusable objects on the free list.
- `peak` records the highest `used` count since initialization.

Reinitialization resets a record without freeing its old blocks.
`_HSD_ObjAllocForgetMemory` only clears the allocator registry. It is part
of the heap reset sequence in `HSD_CreateMainHeap`.

## Allocation limits

The number limit rejects allocation when its flag is enabled and
`used >= num_limit`. Setting the limit value does not enable its flag.

The heap limit uses a saved object count:

1. With no saved cap, `heap_limit_num` is unsigned `-1`.
2. If available heap bytes fall to or below `heap_limit_size`, the allocator
   saves `used + free` as the cap. Existing free objects remain available,
   but ordinary allocation cannot grow the pool beyond that count.
3. If available bytes later exceed the threshold, the allocator clears the
   cap back to `-1`.

The private `getHeapFreeSize` helper contains the shared arena-or-heap
calculation. Both original branches still call it in the same order.
There is no direct assignment that enables the heap-limit flag in the current
source. Its behavior above comes from the allocator implementation.

## Hash lookup output

[`hash.c`](../../src/sysdolphin/baselib/hash.c) looks up an entry in a bucket
chain. `keycheck` returns zero for a matching key. `HSD_HashSearch` gets the
bucket index from the hash class, checks its bounds, then returns the entry's
value. Its optional `success` output reports whether an entry exists. That
distinguishes a missing entry from an entry whose value is NULL.

`HashSearchEntry` has a separate optional output with an unusual type.
On a match, `link_out` receives the address of the pointer that points to
the matching entry. That address is either `&hash->table[idx]` or the
previous entry's `next` field. The function casts this link address to
`HSD_HashEntry*` to fit the existing signature. It does not return the
previous entry itself. A miss leaves this output unchanged.

The only in-tree caller passes NULL for this output. The repository therefore
does not show a consumer of the encoded link address. The cleanup preserves
the exported signature and cast instead of changing that contract.

## Verification

Typed free-list writes use the existing `HSD_ObjAllocLink` layout. The
private helper remains inline. Both changed objects preserve their code and
data sections. `hash.o` also matches byte for byte. The helper changes only
compiler-generated local labels in `objalloc.o`'s string table.

Run the complete executable check in the [build guide](../build-and-run.md)
after integration. Object matching alone does not check callers rebuilt
from the edited headers.
