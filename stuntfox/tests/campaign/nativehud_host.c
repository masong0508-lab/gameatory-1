/* Execute the production frame-overlay wrappers, including exact native
   argument forwarding and keep/docked guards. No cartridge data is needed. */
#include <stdio.h>
#include <stdlib.h>
#include "../../src/stage2.h"
#include "../../src/campaign.h"

S2Frame s2f;
static int ready, room, ending, banners, models, checks;
static int slot_seen, x_seen, y_seen, z_seen, scale_seen;
static void *model_seen;
#define CHECK(test) do { checks++; if (!(test)) { fprintf(stderr, "line %d: %s\n", __LINE__, #test); exit(1); } } while (0)
int s2_ready(void) { return ready; }
int st_active(void) { CHECK(ready); return room; }
int cp_ending(void) { CHECK(ready); return ending; }
static void native_banner(int slot) { banners++; slot_seen = slot; }
static void native_model(void *model, int x, int y, int z, int scale)
{
    models++; model_seen = model; x_seen = x; y_seen = y; z_seen = z; scale_seen = scale;
}
#define SF_PB_BANNER_DRAW native_banner
#define SF_PB_MODEL_DRAW native_model
#include "../../src/nativehud.c"

static void draw(int forwarded)
{
    int before_banners = banners, before_models = models, model = 42;
    sf_native_banner(3);
    sf_native_model(&model, -12345, 99999, -17, 100);
    CHECK(banners - before_banners == forwarded && models - before_models == forwarded);
    if (forwarded) {
        CHECK(slot_seen == 3 && model_seen == &model);
        CHECK(x_seen == -12345 && y_seen == 99999 && z_seen == -17 && scale_seen == 100);
    }
}

int main(void)
{
    ready = 0; s2f.docked = 1; room = 1; ending = CP_END_COMPLETE;
    draw(1);                         /* keep unavailable: never consult its packages */
    ready = 1; s2f.docked = 0;
    draw(1);                         /* normal flight/city: stale room state cannot hide objectives */
    s2f.docked = 1; room = 0; ending = CP_END_NONE;
    draw(1);                         /* ordinary hangar menu */
    ending = CP_END_RETURN;
    draw(1);                         /* pending return has no ending card yet */
    for (int page = CP_END_COMPLETE; page <= CP_END_STATION; page++) {
        ending = page;
        s2f.paused = 0; draw(0);
        s2f.paused = 1; draw(0);      /* the separate native pause menu still draws */
    }
    ending = CP_END_NONE; room = 1;
    s2f.paused = 0; draw(0);
    s2f.paused = 1; draw(0);
    room = 0; s2f.paused = 0; draw(1); /* closing the screen restores ordinary draws */
    printf("%d native HUD checks passed\n", checks);
    return 0;
}
