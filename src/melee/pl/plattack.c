#include "plattack.h"

#include "player.h"
#include "types.h"

u16 unk_804D6480;

void plAttack_80037590(void)
{
    unk_804D6480 = 1;
}

static inline void clearAttackStats(struct plAttackStats* stats)
{
    int attack_id;
    for (attack_id = 0; attack_id < StatsAttack_Count; attack_id++) {
        stats->by_attack_counts[attack_id] = 0;
    }
    stats->total = 0;
    stats->thrown_item_count = 0;
    stats->aerials_count = 0;
    stats->specials_count = 0;
    stats->x1A0_count = 0;
    stats->x1A4_count = 0;
    stats->x1A8 = 0;
}

void plAttack_8003759C(u32 slot)
{
    plActionStats* stats;
    int counter_index;

    stats = Player_GetActionStats((s32) slot);

    clearAttackStats(&stats->attacks);
    clearAttackStats(&stats->hits);
    clearAttackStats(&stats->x358_hits);

    for (counter_index = 0; counter_index < StatsAttack_Count; counter_index++)
    {
        stats->x504[counter_index] = 0;
    }
    stats->x568 = 0;
    stats->x570 = 0;
    stats->x56C = 0;
    stats->x574 = 0;
    stats->x578 = 0;
    stats->x57C = 0;
    stats->x580 = 0;
    stats->x584 = 0;
    stats->x588 = 0;
    stats->x58C = 0;
    stats->x590 = 0;
    stats->x594 = 0;

    for (counter_index = 0; counter_index < 8; counter_index++) {
        stats->x598[counter_index] = 0;
    }
    stats->x5BC_b0 = 0;
    stats->x5BC_b1 = 0;
    stats->x5BC_b2 = 0;
    stats->x5BC_b3 = 0;
}

u16 plAttack_80037B08(void)
{
    u16 attack_instance = unk_804D6480;
    unk_804D6480 += 1;
    if (unk_804D6480 == 0) {
        unk_804D6480 = 1;
    }
    return attack_instance;
}
