/* Campaign-specific Payback fields, extending the mission VM's measured mock.
 * Production campaign.c is compiled unchanged against these interfaces. */
#include "../vm/pbmock.h"
extern u8 cpm_rampage, cpm_was_rampage;
extern s16 cpm_sub, cpm_map, cpm_trophies[6];
extern s32 cpm_num_last;
#define PB_NUM_LAST cpm_num_last
#define PB_RAMPAGE cpm_rampage
#define PB_WAS_RAMPAGE cpm_was_rampage
#define PB_SUB cpm_sub
#define PB_MAP cpm_map
#define PB_TROPHIES cpm_trophies
