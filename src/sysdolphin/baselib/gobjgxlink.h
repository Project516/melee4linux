#ifndef _gobjgxlink_h_
#define _gobjgxlink_h_

#include <Runtime/platform.h>

#include <sysdolphin/baselib/forward.h>

#include <sysdolphin/baselib/gobj.h>

/// Insert an unlinked object after prev_gobj, or at the head if it is NULL.
void GObj_GXReorder(HSD_GObj* gobj, HSD_GObj* prev_gobj);
/// Insert after existing objects with the same priority in gx_link.
void GObj_SetupGXLink(HSD_GObj* gobj, GObj_RenderFunc render_cb, u8 gx_link,
                      u32 priority);
/// Insert after equal priorities in the extra list at gx_link_max + 1.
void GObj_SetupGXLinkMax(HSD_GObj* gobj, GObj_RenderFunc render_cb,
                         u32 priority);
/// Insert before equal priorities in the extra list at gx_link_max + 1.
void GObj_SetupGXLinkMaxSorted(HSD_GObj* gobj, GObj_RenderFunc render_cb,
                               u32 priority);
/// Unlink gobj from rendering. Keep its callback and other object links.
void HSD_GObjGXLink_8039084C(HSD_GObj* gobj);
/// Move a linked object to gx_link, before existing equal priorities.
void HSD_GObjGXLink_80390908(HSD_GObj* gobj, u8 gx_link, u8 priority);
/// Move a linked object directly before next_gobj at its link and priority.
void HSD_GObjGXLink_803909D8(HSD_GObj* gobj, HSD_GObj* next_gobj);

#endif
