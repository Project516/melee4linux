#ifndef _gobjuserdata_h_
#define _gobjuserdata_h_

#include <Runtime/platform.h>

#include <sysdolphin/baselib/forward.h>

#define HSD_GOBJ_USER_DATA_NONE (u8) - 1

// Attach data and its remover. Removal requires a callback even for null data.
void GObj_InitUserData(HSD_GObj* gobj, u8 kind, HSD_UserDataEvent remove_func,
                       void* data);
// Call the remover before clearing the data and marking the slot unused.
void GObj_RemoveUserData(HSD_GObj* gobj);

#endif
