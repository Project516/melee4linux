#ifndef GALE01_013C18
#define GALE01_013C18

#include <Runtime/platform.h>

#include <melee/ft/forward.h>
#include <melee/lb/forward.h>

// Advance commands and blends. Return true for opcode 0x0A or duration expiry.
bool lb_80014258(Fighter_GObj* gobj, void* overlay_data, FtCmd2 execute_cmd);
void lb_80014498(ColorOverlay* overlay);
// Replace an animation when its table priority is at least the current one.
bool lb_800144C8(ColorOverlay* overlay, struct Fighter_804D653C_t* animations,
                 int animation_id, int duration);
void lb_80014534(void);
// A zero duration plays the rumble script once.
void lb_80014574(u8 channel, int id, int rumble_id, int duration);
void lb_800145C0(u8 slot);
void lb_800145F4(void);

#endif
