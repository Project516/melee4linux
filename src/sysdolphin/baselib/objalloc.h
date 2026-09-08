#ifndef _objalloc_h_
#define _objalloc_h_

#include <Runtime/platform.h>

#include <sysdolphin/baselib/debug.h>

typedef struct _objheap {
    u32 top;
    u32 curr;
    u32 size;
    u32 remain;
} objheap;

typedef struct _HSD_ObjAllocLink {
    struct _HSD_ObjAllocLink* next;
} HSD_ObjAllocLink;

typedef struct _HSD_ObjAllocData {
    u32 num_limit_flag : 1;
    u32 heap_limit_flag : 1;
    HSD_ObjAllocLink* freehead;
    u32 used;
    u32 free;
    u32 peak;
    u32 num_limit;
    // Free heap threshold for enabling the cap on allocated objects.
    u32 heap_limit_size;
    // Captured pool count, or -1 while the heap threshold does not limit it.
    u32 heap_limit_num;
    // Object stride after alignment.
    u32 size;
    // Requested alignment minus one.
    u32 align;
    struct _HSD_ObjAllocData* next;
} HSD_ObjAllocData;
ASSERT_SIZE(struct _HSD_ObjAllocData, 0x2C);

static inline u32 HSD_ObjAllocGetUsing(HSD_ObjAllocData* data)
{
    HSD_ASSERT(205, data);
    return data->used;
}

static inline u32 HSD_ObjAllocGetFreed(HSD_ObjAllocData* data)
{
    HSD_ASSERT(221, data);
    return data->free;
}

static inline u32 HSD_ObjAllocGetPeak(HSD_ObjAllocData* data)
{
    HSD_ASSERT(237, data);
    return data->peak;
}

static inline void HSD_ObjAllocSetNumLimit(HSD_ObjAllocData* data,
                                           u32 num_limit)
{
    HSD_ASSERT(251, data);
    data->num_limit = num_limit;
}

static inline void HSD_ObjAllocEnableNumLimit(HSD_ObjAllocData* data)
{
    HSD_ASSERT(278, data);
    data->num_limit_flag = 1;
}

static inline void HSD_ObjAllocDisableNumLimit(HSD_ObjAllocData* data)
{
    HSD_ASSERT(291, data);
    data->num_limit_flag = 0;
}

void HSD_ObjSetHeap(u32 size, void* ptr);
// Grow the free list by up to num objects. Return the number added.
s32 HSD_ObjAllocAddFree(HSD_ObjAllocData* data, u32 num);
void* HSD_ObjAlloc(HSD_ObjAllocData* data);
void HSD_ObjFree(HSD_ObjAllocData* data, void* obj);
void _HSD_ObjAllocForgetMemory(void* low, void* high);
void HSD_ObjAllocInit(HSD_ObjAllocData* data, size_t size, u32 align);

#endif
