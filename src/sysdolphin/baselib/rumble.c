#include "rumble.h"

#include <Runtime/platform.h>

/// @todo Circular dependency
#include "controller.h" // IWYU pragma: keep
#include <dolphin/os.h>
#include <dolphin/pad.h>

enum {
    RUMBLE_STATUS_STOP_HARD = 0,
    RUMBLE_STATUS_STOP = 1,
    RUMBLE_STATUS_RUMBLE = 2,
};

enum {
    RUMBLE_CMD_END = 0,
    RUMBLE_CMD_RUMBLE = 1,
    RUMBLE_CMD_STOP = 2,
    RUMBLE_CMD_STOP_HARD = 3,
    RUMBLE_CMD_LOOP = 4,
    RUMBLE_CMD_LOOP_END = 5,
};

#define RUMBLE_COMMAND_VALUE_MASK 0x1FFF

HSD_RumbleData HSD_Rumble_804C22E0[PAD_MAX_CONTROLLERS];

void HSD_PadRumbleOn(u8 channel)
{
    bool interrupts_enabled = OSDisableInterrupts();
    HSD_RumbleData* rumble = &HSD_Rumble_804C22E0[channel];

    rumble->direct_status = RUMBLE_STATUS_STOP;
    OSRestoreInterrupts(interrupts_enabled);
}

void HSD_PadRumbleOffN(u8 channel)
{
    bool interrupts_enabled = OSDisableInterrupts();
    HSD_RumbleData* rumble = &HSD_Rumble_804C22E0[channel];

    rumble->direct_status = RUMBLE_STATUS_STOP_HARD;
    OSRestoreInterrupts(interrupts_enabled);
}

void HSD_PadRumbleFree(HSD_RumbleData* rumble, HSD_PadRumbleListData* entry)
{
    RumbleInfo* rumble_info = &HSD_PadLibData.rumble_info;
    HSD_PadRumbleListData** entry_link = &rumble->listdatap;

    while (*entry_link != entry) {
        entry_link = &(*entry_link)->next;
    }
    *entry_link = entry->next;
    rumble->nb_list--;
    entry->next = rumble_info->listdatap;
    rumble_info->listdatap = entry;
}

void HSD_PadRumbleRemove(u8 channel)
{
    HSD_RumbleData* rumble = &HSD_Rumble_804C22E0[channel];
    bool interrupts_enabled = OSDisableInterrupts();
    HSD_PadRumbleListData* entry = rumble->listdatap;

    while (entry != NULL) {
        HSD_PadRumbleListData* next_entry = entry->next;
        HSD_PadRumbleFree(rumble, entry);
        entry = next_entry;
    }
    OSRestoreInterrupts(interrupts_enabled);
}

void HSD_PadRumbleRemoveAll(void)
{
    int channel;

    for (channel = 0; channel < PAD_MAX_CONTROLLERS; channel++) {
        HSD_PadRumbleRemove(channel);
    }
}

void HSD_PadRumbleRemoveId(u8 channel, int id)
{
    HSD_RumbleData* rumble = &HSD_Rumble_804C22E0[channel];
    bool interrupts_enabled = OSDisableInterrupts();
    HSD_PadRumbleListData* entry = rumble->listdatap;

    while (entry != NULL) {
        HSD_PadRumbleListData* next_entry = entry->next;
        if (entry->id == (unsigned) id) {
            HSD_PadRumbleFree(rumble, entry);
        }
        entry = next_entry;
    }
    OSRestoreInterrupts(interrupts_enabled);
}

void HSD_PadRumblePause(u8 channel, int paused)
{
    bool interrupts_enabled = OSDisableInterrupts();
    HSD_PadRumbleListData* entry = HSD_Rumble_804C22E0[channel].listdatap;

    while (entry != NULL) {
        HSD_PadRumbleListData* next_entry = entry->next;

        entry->pause = paused;
        entry = next_entry;
    }
    OSRestoreInterrupts(interrupts_enabled);
}

void HSD_PadRumblePauseAll(void)
{
    u8 _[8];

    int channel;
    for (channel = 0; channel < PAD_MAX_CONTROLLERS; channel++) {
        HSD_PadRumblePause(channel, 1);
    }
}

void HSD_PadRumbleUnpauseAll(void)
{
    u8 _[8];

    int channel;
    for (channel = 0; channel < PAD_MAX_CONTROLLERS; channel++) {
        HSD_PadRumblePause(channel, 0);
    }
}

void func_80378430_inline(HSD_PadRumbleListData** entry_link,
                          HSD_PadRumbleListData* entry)
{
    HSD_PadRumbleListData* current;

    while ((current = *entry_link) != NULL && current->pri <= entry->pri) {
        entry_link = &current->next;
    }
    entry->next = current;
    *entry_link = entry;
}

int HSD_PadRumbleAdd(u8 channel, int id, int frame, int priority, void* script)
{
    struct RumbleInfo* rumble_info = &HSD_PadLibData.rumble_info;
    HSD_RumbleData* rumble = &HSD_Rumble_804C22E0[channel];
    int added = 0;
    bool interrupts_enabled = OSDisableInterrupts();
    HSD_PadRumbleListData* entry = rumble_info->listdatap;

    if (entry != NULL && rumble->nb_list < rumble_info->max_list) {
        rumble_info->listdatap = entry->next;
        entry->id = id;
        entry->pause = 0;
        entry->pri = priority;
        entry->status = RUMBLE_STATUS_STOP_HARD;
        entry->loop_count = 0;
        entry->wait = 0;
        entry->frame = frame;
        entry->stack = NULL;
        entry->headp = script;
        entry->listp = script;
        func_80378430_inline(&rumble->listdatap, entry);
        rumble->nb_list++;
        added = 1;
    }
    OSRestoreInterrupts(interrupts_enabled);
    return added;
}

void HSD_Rumble_80378524(int disabled)
{
    bool interrupts_enabled = OSDisableInterrupts();

    HSD_PadLibData.rumble_info.unk2 = disabled;
    OSRestoreInterrupts(interrupts_enabled);
}

int HSD_PadRumbleInterpret1(HSD_PadRumbleListData* entry, u8* status)
{
    if (entry->pause == 1) {
        return 0;
    }
    while (entry->wait == 0) {
        // Read the opcode from the first byte of a big-endian command word.
        switch ((*(u8*) entry->listp >> 5) & 7) {
        case RUMBLE_CMD_END:
            if (entry->frame == -2) {
                return 1;
            }
            entry->listp = entry->headp;
            break;
        case RUMBLE_CMD_RUMBLE:
            entry->status = RUMBLE_STATUS_RUMBLE;
            entry->wait = *entry->listp & RUMBLE_COMMAND_VALUE_MASK;
            entry->listp++;
            break;
        case RUMBLE_CMD_STOP:
            entry->status = RUMBLE_STATUS_STOP;
            entry->wait = *entry->listp & RUMBLE_COMMAND_VALUE_MASK;
            entry->listp++;
            break;
        case RUMBLE_CMD_STOP_HARD:
            entry->status = RUMBLE_STATUS_STOP_HARD;
            entry->wait = *entry->listp & RUMBLE_COMMAND_VALUE_MASK;
            entry->listp++;
            break;
        case RUMBLE_CMD_LOOP:
            entry->loop_count = *entry->listp & RUMBLE_COMMAND_VALUE_MASK;
            entry->listp++;
            entry->stack = entry->listp;
            break;
        case RUMBLE_CMD_LOOP_END:
            if (--entry->loop_count != 0) {
                entry->listp = entry->stack;
            } else {
                entry->listp++;
            }
            break;
        }
    }
    *status = entry->status;
    entry->wait--;
    if (entry->frame != -1 && entry->frame != -2) {
        if (--entry->frame == 0) {
            return 1;
        }
    }
    return 0;
}

void HSD_PadRumbleInterpret(void)
{
    struct RumbleInfo* rumble_info = &HSD_PadLibData.rumble_info;
    HSD_RumbleData* rumble = HSD_Rumble_804C22E0;
    HSD_PadRumbleListData* entry;
    HSD_PadRumbleListData* next_entry;

    int channel;
    for (channel = 0; channel < PAD_MAX_CONTROLLERS; channel++, rumble++) {
        rumble->status = RUMBLE_STATUS_STOP_HARD;
        if (rumble_info->unk2 == 0) {
            rumble->status = rumble->direct_status;
            entry = rumble->listdatap;
            while (entry != NULL) {
                next_entry = entry->next;

                if (HSD_PadRumbleInterpret1(entry, &rumble->status) != 0) {
                    HSD_PadRumbleFree(rumble, entry);
                }
                entry = next_entry;
            }
        }
        if (rumble->status != rumble->last_status) {
            switch (rumble->status) {
            case RUMBLE_STATUS_STOP_HARD:
                PADControlMotor(channel, PAD_MOTOR_STOP_HARD);
                break;
            case RUMBLE_STATUS_STOP:
                PADControlMotor(channel, PAD_MOTOR_STOP);
                break;
            case RUMBLE_STATUS_RUMBLE:
                PADControlMotor(channel, PAD_MOTOR_RUMBLE);
                break;
            }
            rumble->last_status = rumble->status;
        }
    }
}

struct HSD_RumbleData HSD_Rumble_80406DE0 = { 0 };

void HSD_PadRumbleInit(u16 max_entries, void* entries)
{
    struct RumbleInfo* rumble_info = &HSD_PadLibData.rumble_info;
    int index;

    rumble_info->unk2 = 0;
    rumble_info->max_list = max_entries;
    rumble_info->listdatap = entries;
    if (max_entries != 0) {
        for (index = 0; index < max_entries - 1; index++) {
            rumble_info->listdatap[index].next =
                &rumble_info->listdatap[index + 1];
        }
        rumble_info->listdatap[index].next = NULL;
    }
    for (index = 0; index < PAD_MAX_CONTROLLERS; index++) {
        HSD_Rumble_804C22E0[index] = HSD_Rumble_80406DE0;
    }
}
