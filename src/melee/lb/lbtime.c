#include "lbtime.h"

u32 lbTime_8000AEC8(u32 value, u32 increment)
{
    return U32_MAX - value > increment ? value + increment : U32_MAX;
}

u32 lbTime_8000AEE4(u32 value, int delta)
{
    if (delta > 0) {
        return U32_MAX - value > (unsigned) delta ? value + delta : U32_MAX;
    } else {
        return value > (unsigned) -delta ? value + delta : 0;
    }
}

u32 lbTime_8000AF24(u32 value, int delta)
{
    if (delta > 0) {
        unsigned int current = value & U16_MAX;
        int limit = U16_MAX;
        if (limit - current > (unsigned) delta) {
            return value + delta;
        } else {
            return limit;
        }
    } else {
        int current = value & U16_MAX;

        if (current > -delta) {
            return value + delta;
        } else {
            return 0;
        }
    }
}

u32 lbTime_8000AF74(u32 value, int delta)
{
    if (delta > 0) {
        u32 remaining = U8_MAX - (value & U8_MAX);
        return (remaining > delta) ? value + delta : U8_MAX;
    }
    {
        int current = value & U8_MAX;
        return (current > -delta) ? value + delta : 0;
    }
}

u32 lbTime_GetTimeInSeconds(void)
{
    u64 seconds = OSTicksToSeconds(OSGetTime());
    if (seconds > U32_MAX) {
        seconds = U32_MAX;
    }
    return seconds;
}

void lbTime_8000B028(OSCalendarTime* calendar, unsigned int seconds)
{
    OSTicksToCalendarTime(OSSecondsToTicks((u64) seconds), calendar);
}
