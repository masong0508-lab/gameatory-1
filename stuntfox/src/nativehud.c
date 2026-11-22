/* Payback draws these bitmap overlays after our world/frame callback returns.
   Keep their state updates and ordinary gameplay rendering, but let the
   station and campaign ending own their full-screen picture. build.py redirects
   only the two banner draws and three model/arrow draws in the gameplay frame;
   other model calls (including Payback's menus) remain untouched. */
#include "stage2.h"
#include "campaign.h"

#ifndef SF_PB_BANNER_DRAW
#define SF_PB_BANNER_DRAW ((void (*)(int))0x08039c19)
#endif
#ifndef SF_PB_MODEL_DRAW
#define SF_PB_MODEL_DRAW ((void (*)(void *, int, int, int, int))0x0806d821)
#endif

static int screen_owned(void)
{
    /* These calls can also run before our keep is initialized or on a map
       rendered entirely by Payback. Its pause menu has separate drawing calls
       and remains available over a station/ending background. */
    return s2_ready() && s2f.docked && (st_active() || cp_ending() >= CP_END_COMPLETE);
}

void sf_native_banner(int slot)
{
    if (!screen_owned())
        SF_PB_BANNER_DRAW(slot);
}

void sf_native_model(void *model, int x, int y, int z, int scale)
{
    if (!screen_owned())
        SF_PB_MODEL_DRAW(model, x, y, z, scale);
}
