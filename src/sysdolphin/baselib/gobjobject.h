#ifndef SYSDOLPHIN_BASELIB_GOBJOBJECT_H
#define SYSDOLPHIN_BASELIB_GOBJOBJECT_H

#include <Runtime/platform.h>

#include <sysdolphin/baselib/forward.h> // IWYU pragma: export

// Find the first object of this classifier in one process-link list.
/* 390A3C */ HSD_GObj* HSD_GObjObject_80390A3C(u16 classifier, u8 p_link);
/* 390A70 */ void HSD_GObjObject_80390A70(HSD_GObj* gobj, u8 kind, void* obj);
// Detach and return the attached object without calling its remover.
/* 390ADC */ void* HSD_GObjObject_80390ADC(HSD_GObj* gobj);
// Call the registered remover, then clear the attachment.
/* 390B0C */ void HSD_GObjObject_80390B0C(HSD_GObj* gobj);

#endif
