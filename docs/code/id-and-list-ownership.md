# ID tables and list ownership

[`id.c`](../../src/sysdolphin/baselib/id.c) maps a 32-bit ID to a data pointer.
[`list.c`](../../src/sysdolphin/baselib/list.c) allocates and links generic list
nodes. Both modules free their own records. They do not free the data pointers
stored in those records.

## ID lookup and replacement

The insert, remove, and lookup functions accept a table pointer. `NULL` selects
the default table. Each table has 101 buckets. IDs in the same bucket form a
linked chain, and each operation compares the full ID before selecting an entry.

`HSD_IDInsertToTable` replaces the data pointer when the ID already exists. It
does not allocate another entry or release the old data. For a new ID, it
allocates an entry and inserts it at the start of the bucket chain.
`HSD_IDRemoveByIDFromTable` unlinks and frees an entry if present. It does not
release the stored data.

`HSD_IDGetDataFromTable` returns `NULL` for both an absent ID and an entry whose
data is `NULL`. Its optional `success` output distinguishes these cases:

| Result | Return value | `*success` |
| --- | --- | --- |
| ID is absent | `NULL` | 0 |
| ID is present with null data | `NULL` | 1 |
| ID is present with non-null data | Stored pointer | 1 |

[`JObjLoad`](../../src/sysdolphin/baselib/jobj.c) registers a joint descriptor
address as the ID and a loaded `HSD_JObj` as its data. Reference resolution in
[`pobj.c`](../../src/sysdolphin/baselib/pobj.c) and
[`robj.c`](../../src/sysdolphin/baselib/robj.c) uses descriptor addresses to find
the loaded joints. `JObjRelease` removes the ID only if the current entry still
points to the object being released. An ID can have been assigned to another
object since that joint was loaded.

`HSD_IDSetup` and `_HSD_IDForgetMemory` clear all default-table bucket pointers.
They do not walk or free the entries. `_HSD_IDForgetMemory` also ignores its
`low` and `high` arguments. It is registered as a memory-forget callback in
[`initialize.c`](../../src/sysdolphin/baselib/initialize.c), so it is not a
range-specific entry removal API.

## List insertion and removal

`HSD_SListAppendList(list, next)` inserts one node immediately after `list`. It
does not search for the tail and does not append a chain. It overwrites
`next->next` with the old successor of `list` and returns `list`. If `list` is
`NULL`, it sets `next->next` to `NULL` and returns `next`.

`HSD_SListPrependList(list, prev)` sets `prev->next` to `list` and returns `prev`.
It also inserts one node, replacing that node's previous successor. Both
functions require a non-null inserted node. The `AllocAndAppend` and
`AllocAndPrepend` variants allocate this node and store the supplied data
pointer before inserting it. Their return values follow the same rules.

`HSD_SListRemove` frees only the supplied node and returns its successor. It
does not find a predecessor or update the list head. Save its return value in
the head or link that pointed to the removed node. Passing `NULL` returns
`NULL`.

Callers manage the data separately. For example,
[`HSD_LObjDeleteCurrent`](../../src/sysdolphin/baselib/lobj.c) updates the link
with `HSD_SListRemove` and then releases the light reference.
[`HSD_EnvelopeListFree`](../../src/sysdolphin/baselib/pobj.c) first releases
joint references and envelope data, then frees each list node. Copying either
pattern without its data cleanup can leave allocated data or references behind.
