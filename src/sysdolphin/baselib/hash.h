#ifndef _hash_h_
#define _hash_h_

#include <Runtime/platform.h>

#include <sysdolphin/baselib/forward.h>

#include <sysdolphin/baselib/class.h>

#define hash(s) (s % 0x65)

struct HSD_HashEntry {
    HSD_HashEntry* next;
    void* key;
    void* value;
};

typedef struct _HSD_HashClass {
    struct _HSD_HashClassInfo* class_info;
} HSD_HashClass;

typedef struct _HSD_HashClassInfo {
    HSD_ClassInfo parent;
    int (*getidx)(HSD_Hash* hash);
    bool (*keycheck)(HSD_Hash* hash, void* table_key, void* key);
} HSD_HashClassInfo;

struct HSD_Hash {
    HSD_HashClass parent;
    HSD_HashEntry** table;
    u32 table_size;
};

// On a match, link_out receives the link address cast to HSD_HashEntry*.
// The link is a bucket head or an entry's next field. A miss leaves it
// unchanged.
HSD_HashEntry* HashSearchEntry(HSD_Hash* hash, int idx, void* key,
                               HSD_HashEntry** link_out);
// success reports a found entry even when that entry's value is NULL.
HSD_HashClassInfo* HSD_HashSearch(HSD_Hash* hash, void* key, int* success);

#endif
