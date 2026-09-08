#ifndef MELEE_LB_LBTIME_H
#define MELEE_LB_LBTIME_H

#include <Runtime/platform.h>

#include <dolphin/os.h>

/// Add an unsigned increment, stopping at U32_MAX.
u32 lbTime_8000AEC8(u32 value, u32 increment);
/// Apply a signed delta, stopping at zero or U32_MAX.
u32 lbTime_8000AEE4(u32 value, int delta);
/// Apply a signed delta to a value in the range 0..U16_MAX.
u32 lbTime_8000AF24(u32 value, int delta);
/// Apply a signed delta to a value in the range 0..U8_MAX.
u32 lbTime_8000AF74(u32 value, int delta);
u32 lbTime_GetTimeInSeconds(void);
void lbTime_8000B028(OSCalendarTime* calendar, unsigned int seconds);

#endif
