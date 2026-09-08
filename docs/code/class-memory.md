# Class memory pieces

The allocator in [`class.c`](../../src/sysdolphin/baselib/class.c) groups
pieces by size in 32-byte units. It serves the class allocation method
`_hsdClassAlloc` and direct callers such as materials and texture records.
It does not initialize the returned memory.

## Entries and free pieces

For a positive requested size, the entry index is `(size + 31) / 32 - 1`.
An entry at index `idx` stores pieces of `(idx + 1) * 32` bytes.
For example, requests of 33 through 64 bytes use index 1 and receive a
64-byte piece.

`GetMemoryEntry` gets or creates this entry. The `memory_list` pointer table
starts with at least 32 slots and doubles until the index fits.
`nb_memory_list` is the table capacity, including slots with no entry yet.
Each entry's `next` pointer links to the next existing entry with a larger
piece size. This chain lets allocation skip unused size classes.

The entry records in [`class.h`](../../src/sysdolphin/baselib/class.h) track:

| Field | Meaning |
| --- | --- |
| `size` | Piece size in bytes. |
| `nb_alloc` | Number of pieces assigned to this entry, including pieces in use and free pieces. It is not a count of allocation calls. |
| `nb_free` | Number of pieces on the entry's free list. |
| `free_list` | Head of the free-piece list. |
| `next` | Next existing entry with a larger piece size. |

`HSD_FreeList` is stored inside each free piece. Its `next` pointer uses the
first word of that memory. Returning a piece therefore overwrites the
beginning of the caller's data.

## Allocation paths

`hsdAllocMemPiece` first checks the requested entry's free list. If it finds
a piece, it removes the head and decreases `nb_free`. The piece was already
counted in `nb_alloc`, so that count stays the same.

If this list is empty, allocation walks the larger-entry chain. It takes a
piece from the first entry with free memory and splits it at the requested
entry's size. The requested portion goes to the caller. The remainder goes to its
own size class as a free piece. Both counts decrease in the original larger
entry. The requested entry gains one piece, and the remainder entry gains
one free piece. A 96-byte free piece can therefore supply a 64-byte request
and leave one 32-byte free piece.

If no larger entry has free memory, allocation requests a new block of
`nb_memory_list * 32` bytes from `HSD_MemAlloc`. It returns the requested
portion and registers any remainder as a free piece. With the initial table
capacity of 32, a new block has 1024 bytes. The private `addFreePiece` helper
registers remainders from either allocation path and updates both counts.

## Returning memory and growing the table

`hsdFreeMemPiece` accepts the allocation size because pieces have no separate
size header. It selects that size class, puts the piece at the free-list
head, and increases `nb_free`. It ignores a null pointer. It does not merge
adjacent pieces or return memory to the OS heap.

When `GetMemoryEntry` grows the table, it copies the old pointers and clears
the new slots. It publishes the new table before it recycles the old table
through `hsdFreeMemPiece`. It then adds that recycled piece to `nb_alloc`.
The old table came directly from the heap and was not previously counted
as a memory piece. The entry records themselves stay at their original
addresses, so callers can keep their entry pointers during table growth.

The size argument on a normal free must select the same class as the
allocation. For examples, see `HSD_TlutAlloc` and `HSD_TlutFree` in
[`tobj.c`](../../src/sysdolphin/baselib/tobj.c). They use the same `sizeof`
value. The allocation wrapper also clears the memory. In
[`mobj.c`](../../src/sysdolphin/baselib/mobj.c), `HSD_MaterialAlloc` clears a
material and sets its alpha. `MObjRelease` returns it with the same size.

`_hsdClassAlloc` uses `info->head.obj_size`, and `_hsdClassDestroy` returns
the piece with that size. `hsdNew` supplies the zero initialization for
class instances. The class-level `nb_exist` and `nb_peak` counts are separate
from the allocator's piece counts.

`_hsdClassAmnesia` clears the allocator tables when called for `hsdClass`.
This is part of the heap reset path in `HSD_CreateMainHeap` in
[`initialize.c`](../../src/sysdolphin/baselib/initialize.c), which forgets
the class library before destroying and recreating the heap. Amnesia does
not walk the free lists and release each piece.

## Matching checks

The cleanup preserves the code, data, symbol records, and relocation
records in the compiled object. Only generated local names in the ELF
string table change. The pointer-table clear uses `sizeof(*memory_list)`
in place of the literal 4. Both are 4 bytes in the GameCube build.

Keep the explicit `HSD_FreeList*` cast in `hsdFreeMemPiece`. Removing it
changes a register instruction with the original compiler. Keep the
`idx >= 0` assertion text as well. The executable stores this text.
The [build guide](../build-and-run.md) gives the complete executable check
required after combining these changes with other work.
