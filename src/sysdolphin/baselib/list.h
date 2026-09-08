#ifndef _list_h_
#define _list_h_

#include <sysdolphin/baselib/objalloc.h>

typedef struct _HSD_SList {
    struct _HSD_SList* next;
    void* data;
} HSD_SList;

typedef struct _HSD_DList {
    struct _HSD_DList* next;
    struct _HSD_DList* prev;
    void* data;
} HSD_DList;

void HSD_ListInitAllocData(void);
HSD_ObjAllocData* HSD_SListGetAllocData(void);
HSD_ObjAllocData* HSD_DListGetAllocData(void);
HSD_SList* HSD_SListAlloc(void);
/// Allocates one node and inserts it with HSD_SListAppendList.
HSD_SList* HSD_SListAllocAndAppend(HSD_SList* list, void* data);
/// Allocates one node and inserts it with HSD_SListPrependList.
HSD_SList* HSD_SListAllocAndPrepend(HSD_SList* list, void* data);
/// Inserts one node immediately after list, overwriting next->next.
/// Returns list, or next when list is NULL. Does not search for the tail.
HSD_SList* HSD_SListAppendList(HSD_SList* list, HSD_SList* next);
/// Inserts one node before list, overwriting prev->next, and returns prev.
HSD_SList* HSD_SListPrependList(HSD_SList* list, HSD_SList* prev);
/// Frees only this node and returns its successor. Does not free its data.
/// The caller must update the link or head that points to this node.
HSD_SList* HSD_SListRemove(HSD_SList* list);

#endif
