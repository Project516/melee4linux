#include "controller.h"

#include <math.h>

#include "rumble.h"
#include <dolphin/os.h>
#include <dolphin/pad.h>

HSD_PadStatus default_status_data = { 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
                                      0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1 };
PadLibData default_libinfo_data = { 0,    0,    0, 0,    0, 0,    0x2D, 8,
                                    0,    0x1E, 0, 0,    0, 0x7F, 0,    0,
                                    0xFF, 0,    0, 0xFF, 0, 0x7F, 0xFF, 0xFF };
PadLibData HSD_PadLibData;
HSD_PadStatus HSD_PadMasterStatus[PAD_MAX_CONTROLLERS];
HSD_PadStatus HSD_PadCopyStatus[PAD_MAX_CONTROLLERS];
HSD_PadStatus HSD_PadGameStatus[PAD_MAX_CONTROLLERS];
const u32 pad_bit[PAD_MAX_CONTROLLERS] = { PAD_CHAN0_BIT, PAD_CHAN1_BIT,
                                           PAD_CHAN2_BIT, PAD_CHAN3_BIT };

u8 HSD_PadGetRawQueueCount(void)
{
    u8 queue_count;
    u32 interrupts_enabled;
    PadLibData* pad_state;

    pad_state = &HSD_PadLibData;
    interrupts_enabled = OSDisableInterrupts();
    queue_count = pad_state->qcount;
    OSRestoreInterrupts(interrupts_enabled);

    return queue_count;
}

s32 HSD_PadGetResetSwitch(void)
{
    PadLibData* pad_state = &HSD_PadLibData;

    return (pad_state->reset_switch != 0) ? true : false;
}

static void HSD_PadRawQueueShift(u8 capacity, u8* queue_index)
{
    *queue_index = (*queue_index + 1) % capacity;
}

// Merge buttons only. Keep the destination analog values and error.
static void HSD_PadRawMerge(PADStatus* src1, PADStatus* src2, PADStatus* dst)
{
    int channel;
    for (channel = 0; channel < PAD_MAX_CONTROLLERS; channel++) {
        dst[channel].button = src1[channel].button | src2[channel].button;
    }
}

void HSD_PadRenewRawStatus(bool skip_if_all_invalid)
{
    int channel;
    u32 reset_mask;
    PadLibData* pad_state = &HSD_PadLibData;
    HSD_PadData* write_sample;
    PADStatus* retained_sample;
    HSD_PadData sample;

    HSD_PadRumbleInterpret();
    PADRead(sample.stat);
    if (skip_if_all_invalid) {
        for (channel = 0; channel < PAD_MAX_CONTROLLERS; channel++) {
            if (sample.stat[channel].err == PAD_ERR_NONE) {
                break;
            }
        }
        if (channel == PAD_MAX_CONTROLLERS) {
            return;
        }
    }

    write_sample = &pad_state->queue[pad_state->qwrite];
    if (pad_state->qcount == pad_state->qnum) {
        switch (pad_state->qtype) {
        case 0:
            HSD_PadRawQueueShift(pad_state->qnum, &pad_state->qread);
            retained_sample = pad_state->queue[pad_state->qread].stat;
            if (pad_state->qnum != 1) {
                HSD_PadRawMerge(write_sample->stat, retained_sample,
                                retained_sample);
            } else {
                HSD_PadRawMerge(sample.stat, retained_sample, sample.stat);
            }
            break;
        case 1:
            HSD_PadRawQueueShift(pad_state->qnum, &pad_state->qread);
            break;
        case 2:
            goto check_resets;
        }
    } else {
        pad_state->qcount += 1;
    }

    *write_sample = sample;
    HSD_PadRawQueueShift(pad_state->qnum, &pad_state->qwrite);

check_resets:
    reset_mask = 0;
    for (channel = 0; channel < PAD_MAX_CONTROLLERS; channel++) {
        if (sample.stat[channel].err == PAD_ERR_NO_CONTROLLER) {
            reset_mask |= pad_bit[channel];
        }
    }
    if (reset_mask != 0) {
        PADReset(reset_mask);
    }
    if (OSGetResetSwitchState()) {
        pad_state->reset_switch_status = 1;
    } else {
        if (pad_state->reset_switch_status != 0) {
            pad_state->reset_switch = 1;
            pad_state->reset_switch_status = 0;
        }
    }
}

void HSD_PadFlushQueue(HSD_FlushType flush_type)
{
    PadLibData* pad_state;
    PADStatus* destination;
    PADStatus* source;
    bool interrupts_enabled;

    pad_state = &HSD_PadLibData;
    interrupts_enabled = OSDisableInterrupts();
    switch (flush_type) {
    case HSD_PAD_FLUSH_QUEUE_MERGE:
        for (; pad_state->qcount > 1; pad_state->qcount -= 1) {
            source = pad_state->queue[pad_state->qread].stat;
            HSD_PadRawQueueShift(pad_state->qnum, &pad_state->qread);
            destination = pad_state->queue[pad_state->qread].stat;
            HSD_PadRawMerge(source, destination, destination);
        }
        break;
    case HSD_PAD_FLUSH_QUEUE_THROWAWAY:
        pad_state->qread = pad_state->qwrite;
        pad_state->qcount = 0;
        break;
    case HSD_PAD_FLUSH_QUEUE_LEAVE1:
        if (pad_state->qcount > 1) {
            pad_state->qread = pad_state->qwrite != 0 ? pad_state->qwrite - 1
                                                      : pad_state->qnum - 1;
            pad_state->qcount = 1;
        }
        break;
    default:
        break;
    }
    OSRestoreInterrupts(interrupts_enabled);
}

static void HSD_PadClampCheck1(u8* val, u8 shift, u8 min, u8 max)
{
    if (*val < min) {
        *val = 0;
        return;
    }
    if (*val > max) {
        *val = max;
    }
    if (shift != 1) {
        return;
    }
    *val = *val - min;
}

static void HSD_PadClampCheck3(s8* x, s8* y, u8 shift, s8 min, s8 max)
{
    f32 r;

    r = sqrtf(((f32) *x * (f32) *x) + ((f32) *y * (f32) *y));

    if (r < min) {
        *y = 0;
        *x = 0;
        return;
    }
    if (r > max) {
        *x = ((f32) *x * (f32) max) / r;
        *y = ((f32) *y * (f32) max) / r;
        r = sqrtf(((f32) *x * (f32) *x) + ((f32) *y * (f32) *y));
    }

    if (shift == 1 && r > 1.000000013351432e-10f) {
        *x = (f32) *x - (((f32) *x * (f32) min) / r);
        *y = (f32) *y - (((f32) *y * (f32) min) / r);
    }
}

static void HSD_PadClamp(HSD_PadStatus* mp)
{
    PadLibData* p = &HSD_PadLibData;

    switch (p->clamp_stickType) {
    case 0:
        HSD_PadClampCheck3(&mp->stickX, &mp->stickY, p->clamp_stickShift,
                           p->clamp_stickMin, p->clamp_stickMax);
        HSD_PadClampCheck3(&mp->subStickX, &mp->subStickY, p->clamp_stickShift,
                           p->clamp_stickMin, p->clamp_stickMax);
        break;
    default:
        break;
    }
    HSD_PadClampCheck1(&mp->analogL, HSD_PadLibData.clamp_analogLRShift,
                       p->clamp_analogLRMin, p->clamp_analogLRMax);
    HSD_PadClampCheck1(&mp->analogR, p->clamp_analogLRShift,
                       p->clamp_analogLRMin, p->clamp_analogLRMax);
    HSD_PadClampCheck1(&mp->analogA, p->clamp_analogABShift,
                       p->clamp_analogABMin, p->clamp_analogABMax);
    HSD_PadClampCheck1(&mp->analogB, p->clamp_analogABShift,
                       p->clamp_analogABMin, p->clamp_analogABMax);
}

static inline f32 sq(f32 x)
{
    return x * x;
}

static inline f32 vec2DSqDist(f32 x, f32 y)
{
    f32 ret;
    ret = (x * x) + (y * y);
    return ret;
}

static inline f32 vec2Dlen(s8 x, s8 y)
{
    return sqrtf(vec2DSqDist(x, y));
}

static void HSD_PadADConvertCheck1(HSD_PadStatus* mp, s8 x, s8 y, u32 up,
                                   u32 down, u32 left, u32 right)
{
    PadLibData* p = &HSD_PadLibData;
    f32 r;
    f32 a;
    f32 ha;

    r = sq(x);
    r = vec2Dlen(x, y);

    if (fabs(x) == 0.0f) {
        a = y >= 0 ? 1.5707963267948966 : -1.5707963267948966;
    } else {
        a = (f32) atan2f(y, x);
    }

    ha = 0.5F * p->adc_angle;
    if (r < p->adc_th) {
        return;
    }

    if (a < -2.356194490192345 + ha) {
        mp->button |= left;
    }
    if (a >= -2.356194490192345 - ha && a <= -0.7853981633974483 + ha) {
        mp->button |= down;
    }
    if (a > -0.7853981633974483 - ha && a < 0.7853981633974483 + ha) {
        mp->button |= right;
    }
    if (a >= 0.7853981633974483 - ha && a <= 2.356194490192345 + ha) {
        mp->button |= up;
    }
    if (a > 2.356194490192345 - ha) {
        mp->button |= left;
    }
}

static void HSD_PadADConvert(HSD_PadStatus* mp)
{
    PadLibData* p = &HSD_PadLibData;

    switch (p->adc_type) {
    case 0:
        HSD_PadADConvertCheck1(mp, mp->stickX, mp->stickY, PAD_STICK_UP,
                               PAD_STICK_DOWN, PAD_STICK_LEFT,
                               PAD_STICK_RIGHT);
        HSD_PadADConvertCheck1(mp, mp->subStickX, mp->subStickY,
                               PAD_SUBSTICK_UP, PAD_SUBSTICK_DOWN,
                               PAD_SUBSTICK_LEFT, PAD_SUBSTICK_RIGHT);
        break;
    default:
        return;
    }
}

static void HSD_PadScale(HSD_PadStatus* mp)
{
    PadLibData* p = &HSD_PadLibData;

    mp->nml_stickX = (f32) mp->stickX / (f32) p->scale_stick;
    mp->nml_stickY = (f32) mp->stickY / (f32) p->scale_stick;
    mp->nml_subStickX = (f32) mp->subStickX / (f32) p->scale_stick;
    mp->nml_subStickY = (f32) mp->subStickY / (f32) p->scale_stick;
    mp->nml_analogL = (f32) mp->analogL / (f32) p->scale_analogLR;
    mp->nml_analogR = (f32) mp->analogR / (f32) p->scale_analogLR;
    mp->nml_analogA = (f32) mp->analogA / (f32) p->scale_analogAB;
    mp->nml_analogB = (f32) mp->analogB / (f32) p->scale_analogAB;
}

static void HSD_PadCrossDir(HSD_PadStatus* mp)
{
    switch (HSD_PadLibData.cross_dir) {
    case 0:
        break;

    case 1:
        if ((mp->button & (PAD_BUTTON_DOWN | PAD_BUTTON_UP)) == 0) {
            return;
        }
        mp->button = mp->button & ~(PAD_BUTTON_LEFT | PAD_BUTTON_RIGHT);
        return;

    case 2:
        if ((mp->button & (PAD_BUTTON_LEFT | PAD_BUTTON_RIGHT)) == 0) {
            return;
        }
        mp->button = mp->button & ~(PAD_BUTTON_DOWN | PAD_BUTTON_UP);
        return;

    case 3:
        if ((mp->button & (PAD_BUTTON_DOWN | PAD_BUTTON_UP)) != 0) {
            if ((mp->button & (PAD_BUTTON_LEFT | PAD_BUTTON_RIGHT)) != 0) {
                if (mp->cross_dir == 1) {
                    mp->button =
                        mp->button & ~(PAD_BUTTON_LEFT | PAD_BUTTON_RIGHT);
                    return;
                }
                mp->button = mp->button & ~(PAD_BUTTON_DOWN | PAD_BUTTON_UP);
                return;
            } else {
                mp->cross_dir = 1;
                return;
            }
        }
        if ((mp->button & (PAD_BUTTON_LEFT | PAD_BUTTON_RIGHT)) != 0) {
            mp->cross_dir = 2;
            return;
        }
    }
}

static inline void updateButtonHistory(HSD_PadStatus* status,
                                       PadLibData* pad_state)
{
    int repeat_remaining;

    status->trigger = status->button & (status->last_button ^ status->button);
    status->release =
        status->last_button & (status->last_button ^ status->button);
    if (status->last_button ^ status->button) {
        status->repeat = status->trigger;
        status->repeat_count = pad_state->repeat_start;
    } else {
        repeat_remaining = status->repeat_count - 1;
        status->repeat_count = repeat_remaining;
        if (repeat_remaining != 0) {
            status->repeat = 0;
        } else {
            status->repeat = status->button;
            status->repeat_count = pad_state->repeat_interval;
        }
    }
}

void HSD_PadRenewMasterStatus(void)
{
    PadLibData* pad_state;
    HSD_PadStatus* master_status;
    PADStatus* raw_status;
    int channel;

    bool interrupts_enabled;

    pad_state = &HSD_PadLibData;
    master_status = &HSD_PadMasterStatus[0];
    interrupts_enabled = OSDisableInterrupts();
    if (pad_state->qcount != 0) {
        raw_status = pad_state->queue[pad_state->qread].stat;
        HSD_PadRawQueueShift(pad_state->qnum, &pad_state->qread);
        pad_state->qcount -= 1;

        for (channel = 0; channel < PAD_MAX_CONTROLLERS;
             channel++, master_status += 1, raw_status += 1)
        {
            master_status->last_button = master_status->button;
            master_status->err = raw_status->err;
            if (master_status->err == PAD_ERR_NONE) {
                master_status->button = raw_status->button;
                master_status->stickX = raw_status->stickX;
                master_status->stickY = raw_status->stickY;
                master_status->subStickX = raw_status->substickX;
                master_status->subStickY = raw_status->substickY;
                master_status->analogL = raw_status->triggerLeft;
                master_status->analogR = raw_status->triggerRight;
                master_status->analogA = raw_status->analogA;
                master_status->analogB = raw_status->analogB;
                HSD_PadClamp(master_status);
                HSD_PadADConvert(master_status);
                HSD_PadScale(master_status);
                HSD_PadCrossDir(master_status);
            } else if (master_status->err == PAD_ERR_TRANSFER) {
                // A transfer error keeps the previous sample for this pad.
                master_status->err = PAD_ERR_NONE;
            } else {
                master_status->button = 0;
                master_status->subStickY = 0;
                master_status->subStickX = 0;
                master_status->stickY = 0;
                master_status->stickX = 0;
                master_status->analogB = 0;
                master_status->analogA = 0;
                master_status->analogR = 0;
                master_status->analogL = 0;
                master_status->nml_subStickY = 0.0;
                master_status->nml_subStickX = 0.0;
                master_status->nml_stickY = 0.0;
                master_status->nml_stickX = 0.0;
                master_status->nml_analogB = 0.0;
                master_status->nml_analogA = 0.0;
                master_status->nml_analogR = 0.0;
                master_status->nml_analogL = 0.0;
            }
            updateButtonHistory(master_status, pad_state);
        }
    }
    OSRestoreInterrupts(interrupts_enabled);
}

static inline void HSD_PadCopyStatusFields(HSD_PadStatus* dst,
                                           HSD_PadStatus* src)
{
    dst->button = src->button;
    dst->stickX = src->stickX;
    dst->stickY = src->stickY;
    dst->subStickX = src->subStickX;
    dst->subStickY = src->subStickY;
    dst->analogL = src->analogL;
    dst->analogR = src->analogR;
    dst->analogA = src->analogA;
    dst->analogB = src->analogB;
    dst->nml_stickX = src->nml_stickX;
    dst->nml_stickY = src->nml_stickY;
    dst->nml_subStickX = src->nml_subStickX;
    dst->nml_subStickY = src->nml_subStickY;
    dst->nml_analogL = src->nml_analogL;
    dst->nml_analogR = src->nml_analogR;
    dst->nml_analogA = src->nml_analogA;
    dst->nml_analogB = src->nml_analogB;
}

static inline void HSD_PadClearStatusFields(HSD_PadStatus* dst)
{
    dst->button = 0;
    dst->subStickY = 0;
    dst->subStickX = 0;
    dst->stickY = 0;
    dst->stickX = 0;
    dst->analogB = 0;
    dst->analogA = 0;
    dst->analogR = 0;
    dst->analogL = 0;
    dst->nml_subStickY = 0.0;
    dst->nml_subStickX = 0.0;
    dst->nml_stickY = 0.0;
    dst->nml_stickX = 0.0;
    dst->nml_analogB = 0.0;
    dst->nml_analogA = 0.0;
    dst->nml_analogR = 0.0;
    dst->nml_analogL = 0.0;
}

void HSD_PadRenewCopyStatus(void)
{
    HSD_PadStatus* master_status;
    HSD_PadStatus* copy_status;
    PadLibData* pad_state;

    int channel;

    pad_state = &HSD_PadLibData;
    for (channel = 0; channel < PAD_MAX_CONTROLLERS; channel++) {
        master_status = &HSD_PadMasterStatus[channel];
        copy_status = &HSD_PadCopyStatus[channel];

        copy_status->last_button = copy_status->button;
        copy_status->err = master_status->err;
        if (copy_status->err == PAD_ERR_NONE) {
            HSD_PadCopyStatusFields(copy_status, master_status);
        } else {
            HSD_PadClearStatusFields(copy_status);
        }
        updateButtonHistory(copy_status, pad_state);
    }
}

void HSD_PadRenewGameStatus(void)
{
    HSD_PadStatus* master_status;
    HSD_PadStatus* game_status;
    PadLibData* pad_state;

    int channel;

    pad_state = &HSD_PadLibData;
    for (channel = 0; channel < PAD_MAX_CONTROLLERS; channel++) {
        master_status = &HSD_PadMasterStatus[channel];
        game_status = &HSD_PadGameStatus[channel];

        game_status->last_button = game_status->button;
        game_status->err = master_status->err;
        if (game_status->err == PAD_ERR_NONE) {
            HSD_PadCopyStatusFields(game_status, master_status);
        } else {
            HSD_PadClearStatusFields(game_status);
        }
        updateButtonHistory(game_status, pad_state);
    }
}

// Keep these four update calls separate in the matching build.
#ifdef MUST_MATCH
#pragma push
#pragma dont_inline on
#endif
void HSD_PadRenewStatus(void)
{
    HSD_PadRenewRawStatus(0);
    HSD_PadRenewMasterStatus();
    HSD_PadRenewCopyStatus();
    HSD_PadRenewGameStatus();
}
#ifdef MUST_MATCH
#pragma pop
#endif

void HSD_PadReset(void)
{
    PadLibData* pad_state;
    bool interrupts_enabled;
    int channel;

    pad_state = &HSD_PadLibData;
    interrupts_enabled = OSDisableInterrupts();

    HSD_PadRumbleRemoveAll();

    for (channel = 0; channel < PAD_MAX_CONTROLLERS; ++channel) {
        HSD_PadRumbleOffN(channel);
    }

    HSD_PadFlushQueue(HSD_PAD_FLUSH_QUEUE_THROWAWAY);
    PADRecalibrate(PAD_CHAN0_BIT | PAD_CHAN1_BIT | PAD_CHAN2_BIT |
                   PAD_CHAN3_BIT);
    pad_state->reset_switch = 0;

    OSRestoreInterrupts(interrupts_enabled);
}

void HSD_PadInit(u8 queue_capacity, HSD_PadData* queue, u16 rumble_capacity,
                 HSD_PadRumbleListData* rumble_list)
{
    int channel;
    PadLibData* pad_state = &HSD_PadLibData;

    *pad_state = default_libinfo_data;
    pad_state->qnum = queue_capacity;
    pad_state->queue = queue;
    HSD_PadRumbleInit(rumble_capacity, rumble_list);
    for (channel = 0; channel < PAD_MAX_CONTROLLERS; channel++) {
        HSD_PadMasterStatus[channel] = default_status_data;
        HSD_PadCopyStatus[channel] = default_status_data;
        HSD_PadGameStatus[channel] = default_status_data;
    }
    PADInit();
}
