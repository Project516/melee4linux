#ifndef _class_h_
#define _class_h_

#include <Runtime/platform.h>

#include <sysdolphin/baselib/forward.h>

#define HSD_CLASS_INFO(o) ((HSD_ClassInfo*) o)
#define HSD_CLASS_METHOD(o) (((HSD_Class*) o)->class_info)
#define HSD_PARENT_INFO(o) ((o)->parent.head.parent)

#define next_p(p) (p != NULL ? p->next : NULL)

typedef struct _HSD_Class {
    struct _HSD_ClassInfo* class_info;
} HSD_Class;

typedef struct _HSD_ClassInfoHead {
    void (*info_init)(void);
    u32 flags;
    char* library_name;
    char* class_name;
    s16 obj_size;
    s16 info_size;
    struct _HSD_ClassInfo* parent;
    struct _HSD_ClassInfo* next;
    struct _HSD_ClassInfo* child;
    u32 nb_exist;
    u32 nb_peak;
} HSD_ClassInfoHead;

typedef struct _HSD_ClassInfo {
    struct _HSD_ClassInfoHead head;
    HSD_Class* (*alloc)(struct _HSD_ClassInfo* c);
    int (*init)(struct _HSD_Class* c);
    void (*release)(struct _HSD_Class* c);
    void (*destroy)(struct _HSD_Class* c);
    void (*amnesia)(struct _HSD_ClassInfo* c);
} HSD_ClassInfo;

// A free piece stores its next pointer in the memory returned by the caller.
typedef struct _HSD_FreeList {
    /* 0x00 */ struct _HSD_FreeList* next;
} HSD_FreeList;

typedef struct _HSD_MemoryEntry {
    /* 0x00 */ u32 size;     // Bytes, in multiples of 32.
    /* 0x04 */ u32 nb_alloc; // Pieces in use plus free pieces.
    /* 0x08 */ u32 nb_free;  // Pieces on free_list.
    /* 0x0C */ struct _HSD_FreeList* free_list;
    // Next existing entry with a larger piece size.
    /* 0x10 */ struct _HSD_MemoryEntry* next;
} HSD_MemoryEntry;

extern HSD_ClassInfo hsdClass;

/// void hsdDelete(void* object);
void ClassInfoInit(HSD_ClassInfo* info);
void hsdInitClassInfo(HSD_ClassInfo* class_info, HSD_ClassInfo* parent_info,
                      char* base_class_library, char* type, s32 info_size,
                      s32 class_size);
void OSReport_PrintSpaces(s32 count);

// Allocate an uninitialized piece. size must be positive.
void* hsdAllocMemPiece(s32 size);
// Return a piece to its size class. Use the allocation size. NULL is ignored.
void hsdFreeMemPiece(void* mem, s32 size);
void* hsdNew(HSD_ClassInfo*);
bool hsdChangeClass(void* object, void* class_info);
bool hsdIsDescendantOf(void* info, void* p);
bool hsdObjIsDescendantOf(HSD_Obj* o, HSD_ClassInfo* p);
HSD_ClassInfo* hsdSearchClassInfo(const char* class_name);
void hsdForgetClassLibrary(const char* library_name);

// Get or create the entry for (idx + 1) * 32 bytes. idx must be nonnegative.
HSD_MemoryEntry* GetMemoryEntry(s32 idx);
HSD_Class* _hsdClassAlloc(HSD_ClassInfo* info);
int _hsdClassInit(HSD_Class* arg0);
void _hsdClassRelease(HSD_Class* cls);
void _hsdClassDestroy(HSD_Class* cls);
void _hsdClassAmnesia(HSD_ClassInfo* info);
void class_set_flags(HSD_ClassInfo* class_info, s32 set, s32 reset);
void ForgetClassLibraryReal(HSD_ClassInfo* class_info);
void DumpClassStat(HSD_ClassInfo* info, s32 level);
void hsdDumpClassStat(HSD_ClassInfo* info, bool recursive, s32 level);

void ForgetClassLibraryChild(const char* library_name,
                             HSD_ClassInfo* class_info);

static inline void hsdDelete(void* object)
{
    if (object == NULL) {
        return;
    }

    HSD_CLASS_METHOD(object)->release((HSD_Class*) object);
    HSD_CLASS_METHOD(object)->destroy((HSD_Class*) object);
}

#endif
