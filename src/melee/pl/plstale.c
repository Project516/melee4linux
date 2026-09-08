#include "plstale.h"

#include "player.h"
#include "types.h"
#include <melee/ft/ftlib.h>
#include <melee/ft/inlines.h>
#include <melee/ft/types.h>
#include <melee/it/inlines.h>
#include <melee/it/types.h>

u16 staleAttackInstance;

void plStale_InitAttackInstance(void)
{
    staleAttackInstance = 1;
}

void plStale_ResetStaleMoveTableForPlayer(s32 slot)
{
    int entry_index;
    StaleMoveTable* stale_table = Player_GetStaleMoveTableIndexPtr(slot);
    stale_table->current_index = 0;
    for (entry_index = 0; entry_index < 10; entry_index++) {
        stale_table->StaleMoves[entry_index].move_id = 0;
        stale_table->StaleMoves[entry_index].attack_instance = 0;
    }
}

u16 plStale_IncrementAttackInstance(void)
{
    u16 attack_instance = staleAttackInstance;
    staleAttackInstance += 1;
    // Keep zero reserved for cleared queue entries.
    if (staleAttackInstance == 0) {
        staleAttackInstance = 1;
    }
    return attack_instance;
}

static inline void recordStaleMove(StaleMoveTable* stale_table, s32 attack_id,
                                   u16 attack_instance)
{
    int entry_index;

    if (attack_id != 1) {
        // Do not enqueue the same attack again while it is in the queue.
        for (entry_index = 0; entry_index < 10; entry_index++) {
            if (attack_id == stale_table->StaleMoves[entry_index].move_id &&
                attack_instance ==
                    stale_table->StaleMoves[entry_index].attack_instance)
            {
                return;
            }
        }
        stale_table->StaleMoves[stale_table->current_index].move_id =
            attack_id;
        stale_table->StaleMoves[stale_table->current_index].attack_instance =
            attack_instance;
        stale_table->current_index = stale_table->current_index == 9
                                         ? 0
                                         : stale_table->current_index + 1;
    }
}

void plStale_UpdateStaleMovesFromFighter(HSD_GObj* attacker_gobj,
                                         HSD_GObj* victim_gobj)
{
    s32 attack_id;
    u16 attack_instance;
    StaleMoveTable* stale_table;

    if (attacker_gobj != victim_gobj) {
        Fighter* attacker = GET_FIGHTER(attacker_gobj);

        attack_instance = attacker->x206C_attack_instance;
        attack_id = attacker->x2068_attackID;
        stale_table = Player_GetStaleMoveTableIndexPtr(attacker->player_id);
        recordStaleMove(stale_table, attack_id, attack_instance);
    }
}

void plStale_UpdateStaleMovesFromItem(HSD_GObj* item_gobj,
                                      HSD_GObj* victim_gobj)
{
    s32 attack_id;
    u16 attack_instance;
    StaleMoveTable* stale_table;
    HSD_GObj* owner;
    Item* item;

    item = GET_ITEM(item_gobj);
    owner = item->owner;
    if (ftLib_80086960(owner) && owner != victim_gobj) {
        attack_instance = item->xD8C_attack_instance;
        attack_id = item->xD88_attackID;
        stale_table =
            Player_GetStaleMoveTableIndexPtr(GET_FIGHTER(owner)->player_id);
        recordStaleMove(stale_table, attack_id, attack_instance);
    }
}
