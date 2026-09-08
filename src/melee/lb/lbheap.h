#ifndef MELEE_LB_HEAP_H
#define MELEE_LB_HEAP_H

#include <Runtime/platform.h>

/// @remarks @c LbHeapStatus_Create is named by an assert in #lbHeap_80015CA8.
typedef enum LbHeapStatus {
    /* 0x00 */ LbHeapStatus_Create,
    /* 0x01 */ LbHeapStatus_Destroy,
} LbHeapStatus;

// Slots 2 through 5 use 0 to keep the heap or 1 to release it on rebuild.
/* 0158D0 */ void lbHeap_800158D0(int heap_index, int transient);
/* 0158E8 */ int lbHeap_800158E8(int heap_index);
/* 015900 */ void lbHeap_80015900(void);
/* 015BB8 */ LbHeapStatus lbHeap_80015BB8(int heap_index);
// Slots 0 and 1 return addresses. Slots 2 through 5 return Handle* records.
/* 015BD0 */ void* lbHeap_80015BD0(int heap_index, size_t size);
// Free by data address, including for slots that return allocation records.
/* 015CA8 */ void lbHeap_80015CA8(int heap_index, void* address);
/* 015D6C */ int lbHeap_80015D6C(u32 heap_index, void (*callback)(u32),
                                 u32 callback_arg);
/* 015DF8 */ void lbHeap_80015DF8(void);
/* 015F3C */ void lbHeap_80015F3C(void);

#endif
