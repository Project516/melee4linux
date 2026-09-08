#include "gobjgxlink.h"

#include "debug.h"
#include "gobj.h"

#ifdef MUST_MATCH
#pragma push
#pragma dont_inline on
#endif
void GObj_GXReorder(HSD_GObj* gobj, HSD_GObj* prev_gobj)
{
    u32 gx_link = gobj->gx_link;

    gobj->prev_gx = prev_gobj;
    if (prev_gobj != NULL) {
        gobj->next_gx = prev_gobj->next_gx;
        prev_gobj->next_gx = gobj;
    } else {
        gobj->next_gx = HSD_GObjGXLinkHead[gx_link];
        HSD_GObjGXLinkHead[gx_link] = gobj;
    }

    if (gobj->next_gx != NULL) {
        gobj->next_gx->prev_gx = gobj;
    } else {
        HSD_GObj_804D7820[gobj->gx_link] = gobj;
    }
}
#ifdef MUST_MATCH
#pragma pop
#endif

void GObj_SetupGXLink(HSD_GObj* gobj, GObj_RenderFunc render_cb, u8 gx_link,
                      u32 priority)
{
    HSD_GObj* cursor;
    HSD_GObj* prev_gobj;

    HSD_ASSERT(167, gx_link <= HSD_GObjLibInitData.gx_link_max);
    gobj->render_cb = render_cb;
    gobj->gx_link = gx_link;
    gobj->render_priority = priority;

    /* Search from the tail to insert after existing equal priorities. */
    for (cursor = HSD_GObj_804D7820[gobj->gx_link];
         cursor != NULL && cursor->render_priority > gobj->render_priority;
         cursor = prev_gobj)
    {
        prev_gobj = cursor->prev_gx;
    }
    GObj_GXReorder(gobj, cursor);
}

void GObj_SetupGXLinkMax(HSD_GObj* gobj, GObj_RenderFunc render_cb,
                         u32 priority)
{
    HSD_GObj* cursor;
    u8 max_link = HSD_GObjLibInitData.gx_link_max;

    gobj->render_cb = render_cb;
    gobj->gx_link = max_link + 1;
    gobj->render_priority = priority;

    cursor = HSD_GObj_804D7820[gobj->gx_link];
    while (cursor != NULL && cursor->render_priority > gobj->render_priority) {
        cursor = cursor->prev_gx;
    }
    GObj_GXReorder(gobj, cursor);
}

/* Find the first object at or after this priority, including equal values. */
static inline HSD_GObj* findFirstAtOrAbovePriority(HSD_GObj* gobj)
{
    HSD_GObj* cursor = HSD_GObjGXLinkHead[gobj->gx_link];
    while (cursor != NULL && cursor->render_priority < gobj->render_priority) {
        cursor = cursor->next_gx;
    }
    return cursor;
}

void GObj_SetupGXLinkMaxSorted(HSD_GObj* gobj, GObj_RenderFunc render_cb,
                               u32 priority)
{
    HSD_GObj* cursor;
    u8 max_link = HSD_GObjLibInitData.gx_link_max;

    gobj->render_cb = render_cb;
    gobj->gx_link = max_link + 1;
    gobj->render_priority = priority;

    cursor = findFirstAtOrAbovePriority(gobj);

    if (cursor != NULL) {
        cursor = cursor->prev_gx;
    } else {
        cursor = HSD_GObj_804D7820[gobj->gx_link];
    }
    GObj_GXReorder(gobj, cursor);
}

void HSD_GObjGXLink_8039084C(HSD_GObj* gobj)
{
    HSD_GObj* prev;
    HSD_GObj* next;

    HSD_ASSERT(415, gobj->gx_link != HSD_GOBJ_GXLINK_NONE);

    prev = gobj->prev_gx;
    if (prev != NULL) {
        prev->next_gx = gobj->next_gx;
    } else {
        HSD_GObjGXLinkHead[gobj->gx_link] = gobj->next_gx;
    }
    next = gobj->next_gx;
    if (next != NULL) {
        next->prev_gx = gobj->prev_gx;
    } else {
        HSD_GObj_804D7820[gobj->gx_link] = gobj->prev_gx;
    }
    gobj->gx_link = HSD_GOBJ_GXLINK_NONE;
    gobj->render_priority = 0;
    gobj->prev_gx = NULL;
    gobj->next_gx = NULL;
}

void HSD_GObjGXLink_80390908(HSD_GObj* gobj, u8 gx_link, u8 priority)
{
    HSD_GObj* cursor;
    HSD_ASSERT(535, gx_link <= HSD_GObjLibInitData.gx_link_max);
    HSD_GObjGXLink_8039084C(gobj);
    gobj->gx_link = gx_link;
    gobj->render_priority = priority;
    cursor = findFirstAtOrAbovePriority(gobj);
    GObj_GXReorder(gobj, cursor != NULL ? cursor->prev_gx
                                        : HSD_GObj_804D7820[gobj->gx_link]);
}

void HSD_GObjGXLink_803909D8(HSD_GObj* gobj, HSD_GObj* next_gobj)
{
    u8 _[12];

    u8 gx_link;
    u8 priority;

    priority = next_gobj->render_priority;
    gx_link = next_gobj->gx_link;
    HSD_GObjGXLink_8039084C(gobj);
    gobj->gx_link = gx_link;
    gobj->render_priority = priority;
    GObj_GXReorder(gobj, next_gobj->prev_gx);
}
