#include "hash.h"

#include "debug.h"

HSD_HashEntry* HashSearchEntry(HSD_Hash* hash, int idx, void* key,
                               HSD_HashEntry** link_out)
{
    if (hash->table[idx] == NULL) {
        return NULL;
    }
    if (link_out != NULL) {
        HSD_HashEntry** entry_link;
        for (entry_link = &hash->table[idx]; *entry_link != NULL;
             entry_link = &((*entry_link)->next))
        {
            if (hash->parent.class_info->keycheck(hash, (*entry_link)->key,
                                                  key) == 0)
            {
                *link_out = (HSD_HashEntry*) entry_link;
                return *entry_link;
            }
        }
    } else {
        HSD_HashEntry* entry;
        for (entry = hash->table[idx]; entry != NULL; entry = entry->next) {
            if (hash->parent.class_info->keycheck(hash, entry->key, key) == 0)
            {
                return entry;
            }
        }
    }
    return NULL;
}

HSD_HashClassInfo* HSD_HashSearch(HSD_Hash* hash, void* key, int* success)
{
    HSD_HashEntry* entry;
    u32 idx;

    idx = hash->parent.class_info->getidx(hash);
    HSD_ASSERT(113, idx < hash->table_size);
    entry = HashSearchEntry(hash, idx, key, NULL);
    if (success != NULL) {
        *success = !!entry;
    }
    if (entry != NULL) {
        return (HSD_HashClassInfo*) entry->value;
    }
    return NULL;
}
