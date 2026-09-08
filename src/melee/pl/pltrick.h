#ifndef MELEE_PL_PLTRICK_H
#define MELEE_PL_PLTRICK_H

#include <Runtime/platform.h>

#include <melee/ft/types.h>

struct plActionStats;
struct plAttackStats;

/* 037B2C */ int pl_80037B2C(struct plActionStats* action_stats, int h_player,
                             int attack_id);
/* 037BC0 */ void pl_80037BC0(struct plAttackStats* stats,
                              union Struct2070* attack_event);
/* 037C60 */ void pl_80037C60(Fighter_GObj* fighter_gobj,
                              volatile s32 previous_event_bits);
/* 037DF4 */ void pl_80037DF4(HSD_GObj* fighter_gobj,
                              union Struct2070* attack_event);
/* 037ECC */ void pl_80037ECC(HSD_GObj* fighter_gobj);
/* 038144 */ void pl_80038144(HSD_GObj* attacker_gobj, HSD_GObj* victim_gobj,
                              s32 attack_event_bits, ft_800898B4_t* hit_data,
                              u16 attack_instance, s32 grounded,
                              s32 previous_source_player);
/* 0384DC */ void pl_800384DC(HSD_GObj* fighter_gobj, int attack_event_bits,
                              void* hit_data_raw);
/* 038628 */ bool pl_80038628(HSD_GObj* fighter_gobj, int kind);

#endif
