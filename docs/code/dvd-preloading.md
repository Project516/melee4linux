# DVD preload entries

[`lbdvd.c`](../../src/melee/lb/lbdvd.c) queues disc files, reads one file at a
time, and prepares selected files as archives. The cache has 80 entries in
[`types.h`](../../src/melee/lb/types.h). Its `state` field tracks the request.
Its separate `load_state` field controls archive initialization.

## Request flow

1. `lbDvd_800178E8` resolves a filename and passes its parameters to
   `lbDvd_80017740`. The latter creates or reuses a cache entry.
2. `lbDvd_80017CC4` selects a queued entry with the highest positive
   `load_score`. An existing read blocks another read. Equal scores keep the
   first candidate in array order.
3. `lbDvd_CachePreloadedFile` prepares the heap, allocates storage, and queues
   the read through `lbFile_800164A4`.
4. `lbDvd_80017E64` receives the completion callback. It asserts on
   cancellation, marks a completed request as loaded, and runs selection
   again.
5. `lbDvd_GetPreloadedArchive` waits for readiness, performs any required
   archive initialization, and returns the archive or raw data address.

`lbDvd_80017740` searches for an existing entry by DVD entry number and the
`transient_heap` argument. When it creates a new entry, it stores the separate
`heap` argument. Existing callers often pass the same heap twice, but these
arguments have distinct uses and must remain separate.

## Request states

| `state` | Meaning in this code |
| --- | --- |
| 0, unused | Available for a new request. |
| 1, queued | Waiting for selection by positive `load_score`. |
| 2, reading | A disc read is active. The completion callback advances it. |
| 3, loaded | Completion has been reported. Readiness checks can still wait for heap work. |
| 4, ready | A readiness check has promoted the entry. Cleanup before compaction skips it. |

`lbDvd_800187F4` returns 0 when it finds no requested entry, 1 while work is
pending, and 2 when the entry is ready. It promotes state 3 to state 4 and
sets `load_score` to 9999. `lbDvd_800189EC` waits only while the result is 1.

Readiness can wait for other entries on the same heap. In state 3,
`findHeapDependencies` checks for both a queued entry with a positive score
and a reading or loaded entry with a negative score. If both exist, the
request remains pending. The mask-based readiness check in
`lbDvd_80018A2C` makes the same check for entries selected by `unknown004`.
The exact category names for those flag bits remain unspecified here.

The state values above describe request progress. State 4 does not prove
that an archive has been parsed. That uses `load_state == 1`, which the
lookup function changes to 2 after initialization.

## Heap work and stored addresses

The field named `persistent_heap` blocks request selection while its value
is a heap index. Value 6 permits selection. Before allocating a file,
`lbDvd_CleanupPreloadHeap` releases state-3 entries with negative scores on
that heap, sets this field, and calls `lbHeap_80015D6C`.

That heap call can start compaction through
[`lbmemory.c`](../../src/melee/lb/lbmemory.c). While compaction is pending,
the file allocation waits. Its callback `lbDvd_80017A80` restores value 6
and starts selection again. If no compaction is needed, the file loader
restores value 6 directly and continues allocation.

The `archive` and `raw_data` fields hold allocation handles with an `addr`
field. Reads and parsers use the current `addr`. The memory code can update
that address during compaction. `lbDvd_800174E8` frees both allocations
through their stored heap and resets the entry. It does not free the cache
entry itself.

Scene updates make positive scores negative before requesting the next
scene's files. Reused requests become positive again. Unused ready entries
can return to state 3, where later heap cleanup can release them. The
returned data therefore remains part of the cache's storage and lifetime.

## File types and callers

| `type` | Storage and preparation |
| --- | --- |
| 0 | Allocate raw storage and report completion without a disc read. |
| 1 | Read raw data. Fighter animation files use this path with `load_state == 0`. |
| 2 | Allocate an archive object and initialize it with `lbArchive_InitializeDAT`. |
| 3 | Allocate an archive object and prepare it with `efAsync_OnLoad`. |
| 4 | Allocate an archive object and prepare it with `grDatFiles_801C5FC0`. |

The preparation calls for types 2 through 4 occur on lookup when
`load_state == 1`. Examples are in
[`ftdata.c`](../../src/melee/ft/ftdata.c),
[`efasync.c`](../../src/melee/ef/efasync.c), and
[`ground.c`](../../src/melee/gr/ground.c).
See the [file loading guide](file-loading.md) for filename rules and the
32-byte transfer rounding used by the underlying reader.

The matching compiler still needs the integer result in `sameHeap`, the
repeated entry reload in heap cleanup, and the separate compaction-result
checks in the file loader. Simplifying those forms changes the generated
instructions. Keep a complete build check when changing them.
