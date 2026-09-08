# Archive layout and relocation

[`archive.c`](../../src/sysdolphin/baselib/archive.c) reads HSD archive metadata,
relocates internal pointers, and finds named data. The file loaders in
[`lbarchive.c`](../../src/melee/lb/lbarchive.c) supply its file buffer. See the
[file-loading guide](file-loading.md) for disc reads and heap ownership.

## File layout

The structs in [`archive.h`](../../src/sysdolphin/baselib/archive.h) describe
these consecutive regions:

| Region | Size | Contents |
| --- | --- | --- |
| Header | `0x20` bytes | File size, data size, table counts, version bytes, and padding. |
| Data | `data_size` bytes | Objects and encoded pointer values. |
| Relocation table | `nb_reloc * 4` bytes | Offsets of internal pointer slots within the data. |
| Public table | `nb_public * 8` bytes | Data offsets and symbol-name offsets for exported objects. |
| External table | `nb_extern * 8` bytes | First reference offsets and symbol-name offsets for external names. |
| Symbol strings | Remaining bytes | Null-terminated names used by the public and external tables. |

A public entry's `offset` selects data relative to `archive->data`. A relocation
entry's `offset` selects the word to update relative to the same base. The
`symbol` fields in public and external entries are byte offsets relative to
`archive->symbols`, not pointers or symbol indices.

The format uses GameCube byte order and 32-bit pointer words. The parser copies
the header and reads the tables directly. It does not swap bytes. Some accesses
use `uintptr_t`, so compiling this source for a 64-bit host does not make it a
working host archive reader.

## Parsing and storage

`HSD_ArchiveParse` clears the supplied archive object and copies the file header
into it. It sets table pointers into the source buffer, stores that buffer in
`top_ptr`, and calls the private `relocateInternalPointers` helper. For each
relocation entry, the helper adds the data base address to the word at the
entry's data offset. This changes an encoded data offset into a runtime pointer.

The source buffer must be writable. Parsing changes its data in place and does
not allocate or copy the data region. Keep that storage at the same address
while its pointers are in use. Parsing the same relocated bytes again would add
the data base a second time. When animation code copies an already relocated
buffer, it instead uses `lbArchiveRelocate` to apply the address difference.
See `ftData_80085E50` in [`ftdata.c`](../../src/melee/ft/ftdata.c).

The parser returns `-1` for a null archive pointer or a file-size mismatch.
The mismatch report says "byte-order mismatch", but that comparison alone does
not identify the cause. Success does not certify arbitrary input. The parser
does not check every table range, pointer slot, or string terminator against
the supplied size.

The parser sets `HSD_ARCHIVE_DONT_FREE`, but it does not free storage itself.
The flag name does not prevent Melee's loader from releasing its own heap
allocations. `lbArchive_80016EFC` checks that flag, then frees the file buffer
and archive object. Stack archive objects also occur in `ftdata.c`. They borrow
animation buffers and must not be passed to that heap-specific release path.

## Public names and external references

`HSD_ArchiveGetPublicAddress` scans the public table and returns the data address
for the first matching name. It returns `NULL` when the name is absent. The
returned address refers to the existing data buffer.

`HSD_ArchiveGetExtern` takes an external-table index. It returns a name in the
symbol strings, or `NULL` for a negative index or an index at or beyond the
table count. It does not return the address of an external object.

`HSD_ArchiveLocateExtern` finds the first external-table entry with a matching
name. That entry's `offset` starts a chain within the data. Before patching,
each word in the chain contains the data offset of the next word. The function
reads the next offset, overwrites the current word with the supplied address,
and continues. `0xFFFFFFFF` ends the chain. An offset at or beyond `data_size`
also stops traversal.

Patching consumes the chain because the address replaces each next-offset
word. This is not a retained list that can be walked again to bind a second
address. The table entry and its name remain, but the original links do not.
The loop's range comparison does not check alignment or that a full pointer
word fits within the data region.

`lbArchive_InitializeDAT` parses an archive, enumerates its external names, and
patches each chain with `NULL`. This leaves public data ready for the game's
loaders without resolving external names to another archive.
