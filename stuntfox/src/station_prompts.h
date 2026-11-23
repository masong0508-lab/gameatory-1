/* Station menu help: only advertise A for an action the player may take.
 * Keep this logic independent of the renderer so ROM-free host tests can
 * check the same prompts the GBA draws. No allocations, no per-frame state. */
#ifndef STUNTFOX_STATION_PROMPTS_H
#define STUNTFOX_STATION_PROMPTS_H

static inline const char *st_city_board_prompt(int campaign_on, int ncity,
                                                int can_claim, int other_city)
{
    if (!ncity)
        return "B: BACK";
    if (!campaign_on)
        return "HANGAR L: CAMPAIGN  B: BACK";
    if (can_claim)
        return "A: CLAIM   < >: THIS CITY   B: BACK";
    if (other_city)
        return "A: TRAVEL   < >: THIS CITY   B: BACK";
    return "A: TAKE   < >: THIS CITY   B: BACK";
}

static inline const char *st_eva_board_prompt(int campaign_on, int pack,
                                               int row, int active_job)
{
    if (row >= 3)
        return active_job ? "A: CANCEL WALK  <: MAP  B: BACK"
                          : "A: CLOSE  <: MAP  B: BACK";
    if (!campaign_on)
        return "HANGAR L: CAMPAIGN  <: MAP  B: BACK";
    if (!pack)
        return "JET PACK: SHOP  <: MAP  B: BACK";
    return "A: TAKE + LAUNCH  <: MAP  B: BACK";
}

#endif
