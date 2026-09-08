#ifndef SYSDOLPHIN_BASELIB_RUMBLE_H
#define SYSDOLPHIN_BASELIB_RUMBLE_H

#include <Runtime/platform.h>

#include <sysdolphin/baselib/forward.h>

struct HSD_RumbleData {
    u8 last_status;
    u8 status;
    u8 direct_status;
    u16 nb_list;
    HSD_PadRumbleListData* listdatap;
};

struct RumbleCommand {
    u16 op;
    u16 frame;
};

union HSD_Rumble {
    u16 def;
    RumbleCommand command;
};

struct RumbleInfo {
    u16 max_list;
    u8 unk2;
    HSD_PadRumbleListData* listdatap;
};

struct HSD_PadRumbleListData {
    /*0x00*/ HSD_PadRumbleListData* next;
    /*0x04*/ u32 id;
    /*0x08*/ u8 pause;
    /*0x09*/ u8 pri;
    /*0x0A*/ u8 status;
    /*0x0C*/ u16 loop_count;
    /*0x0E*/ u16 wait;
    /*0x10*/ s32 frame;
    /*0x14*/ /* HSD_Rumble* */ u16* stack;
    /*0x18*/ /* HSD_Rumble* */ u16* listp;
    /*0x1C*/ /* HSD_Rumble* */ u16* headp;
};

void HSD_PadRumbleRemoveId(u8 channel, int id);

// Unlink an entry already in this controller's list and return it to the pool.
void HSD_PadRumbleFree(HSD_RumbleData* rumble, HSD_PadRumbleListData* entry);
void HSD_PadRumbleRemove(u8 channel);
void HSD_PadRumbleRemoveAll(void);
void HSD_PadRumblePause(u8 channel, int paused);
void HSD_PadRumblePauseAll(void);
void HSD_PadRumbleUnpauseAll(void);
// Insert after existing entries with the same or lower priority.
void func_80378430_inline(HSD_PadRumbleListData** entry_link,
                          HSD_PadRumbleListData* entry);
int HSD_PadRumbleAdd(u8 channel, int id, int frame, int priority,
                     void* script);
void HSD_Rumble_80378524(int disabled);
int HSD_PadRumbleInterpret1(HSD_PadRumbleListData* entry, u8* status);
void HSD_PadRumbleInterpret(void);
void HSD_PadRumbleInit(u16 max_entries, void* entries);
void HSD_PadRumbleOn(u8 channel);
void HSD_PadRumbleOffN(u8 channel);

#endif
