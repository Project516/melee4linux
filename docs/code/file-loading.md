# File and archive loading

[`lbfile.c`](../../src/melee/lb/lbfile.c) reads disc bytes.
[`lbarchive.c`](../../src/melee/lb/lbarchive.c) parses those bytes as an
`HSD_Archive` and finds named data inside it.
[`lbdvd.c`](../../src/melee/lb/lbdvd.c) supplies the preload cache.

## Filenames and read sizes

`lbFileGetFullName` uses three rules:

| Input | Result |
| --- | --- |
| A name with an extension, such as `IfAll.dat` | Keep the supplied name. |
| A name ending in `.`, such as `ItCo.` | Add `usd` or `dat` using the current language setting. |
| A name without `.`, such as `IfAll` | Add `.usd` or `.dat` using the saved language. |

The US language selects `usd`. The other branch selects `dat`. The two
language checks are separate in
[`lblanguage.c`](../../src/melee/lb/lblanguage.c).
The result uses one static 32-byte buffer. A later call overwrites it.

`lbFileGetSize` resolves the name to a DVD entry number.
`lbFile_8001634C` opens that entry, reads `DVDFileInfo.length`, and closes it.
It restores the interrupt state that was active before the size query.

`lbFile_800164A4` queues a whole-file read. Its output size is the actual file
length, while the requested transfer size is rounded up to 32 bytes.
The allocation helpers use the same rounding. Callers that supply their own
buffer must account for this transfer size. The SDK also requires aligned
source, destination, and size values in
[`HSD_DevComRequest`](../../src/sysdolphin/baselib/devcom.c).

## Completion and preloading

`lbFile_80016580` queues a read and returns. It accepts a completion callback.
`lbFile_8001668C` uses that function, then waits in `waitForDisc`.
`lbFile_80016760` also allocates the destination on heap 0 before waiting.

The static flag named `cancel` is a completion flag in this module.
`lbFile_8001615C` asserts that the callback's cancellation flag is false,
then sets `cancel` to true. The wait loop calls `lb_800195D0` while it checks
completion. Keep the existing non-inlining control on `discIsDone`.

`lbFile_800168A0` first checks the preload cache. On a miss, it allocates on
the requested heap and waits for the read. Its return value is true for a
cache hit and false for a new allocation. False does not mean the read failed.

## Archive symbols and ownership

When reading a new archive, the loaders allocate both the file buffer and
an `HSD_Archive` on heap 0. `lbArchive_InitializeDAT` calls `HSD_ArchiveParse`, then walks the
external symbol names and sets their references to NULL with
`HSD_ArchiveLocateExtern`. These SDK functions are in
[`archive.c`](../../src/sysdolphin/baselib/archive.c).

Symbol-loading arguments alternate an output pointer and a symbol name.
The last argument is a null output pointer. Each output receives the address
returned by `HSD_ArchiveGetPublicAddress`. The first output parameter is
named `symbol_dst` to distinguish it from the symbol name.

| Function | Read behavior | Missing public symbol |
| --- | --- | --- |
| `lbArchive_LoadSections` | Use the supplied archive. | Report the name and leave the output NULL. |
| `lbArchive_LoadSymbols` | Allocate and read an archive. | Report the name and assert. |
| `lbArchive_80016DBC` | Allocate and read an archive. | Report the name and leave the output NULL. |
| `lbArchive_80017040` | Use the preload cache, or allocate and read. | Report the name and assert. |
| `lbArchive_800171CC` | Use the preload cache, or allocate and read. | Report the name and leave the output NULL. |

`lbArchive_80016F80` has the same preload-or-read choice without symbol
arguments. It and the two symbol loaders with cache checks return true on a
cache hit. Their optional `dst` parameter receives the archive itself.
For a caller example, follow `ifAll_802F390C` in
[`ifall.c`](../../src/melee/if/ifall.c).

`lbArchive_80016EFC` frees two heap-0 allocations. It finds the file buffer
one `HSD_ArchiveHeader` before `archive->data`, then frees the archive object.
This allocation pattern differs from storage supplied by the preload cache.
The cache owns its entries and manages their lifetime in `lbdvd.c`.

## Relocation and matching constraints

`lbArchiveRelocate` reconstructs the archive's table pointers from a file
buffer, then adds the supplied `base_addr` adjustment to each relocation
target. For example, `ftData_80085E50` in
[`ftdata.c`](../../src/melee/ft/ftdata.c) uses it after copying animation data
and passes the difference between the new and old addresses.

`HSD_ArchiveRelocationInfo.offset` is an integer byte offset. The local
relocation loop keeps it as `u32` until it selects the pointer to update.
The format still assumes GameCube byte order and 32-bit pointers. This
cleanup does not make archive parsing portable to a 64-bit host.

The archive loaders retain repeated allocation blocks and stack padding.
Replacing those blocks with the existing inline loader changed register
allocation and stack offsets in the matching compiler. Keep those blocks
unless the replacement also reproduces the original object bytes.
