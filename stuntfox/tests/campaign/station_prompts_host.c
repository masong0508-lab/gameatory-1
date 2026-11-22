/* Exercise the exact station prompt helpers used by the GBA runtime. */
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "station_prompts.h"

#define CHECK(x) do { assert(x); checks++; } while (0)
static int checks;

static void valid(const char *s)
{
    CHECK(strlen(s) < 38);    /* 240-pixel screen, 6-pixel font at x=10 */
}

int main(void)
{
    for (int campaign = 0; campaign <= 1; campaign++)
        for (int cities = 0; cities <= 2; cities++)
            for (int claim = 0; claim <= 1; claim++)
                for (int remote = 0; remote <= 1; remote++) {
                    const char *p = st_city_board_prompt(campaign, cities, claim, remote);
                    valid(p);
                    CHECK(campaign && cities ? strstr(p, "A:") != NULL : strstr(p, "A:") == NULL);
                    if (campaign && cities && claim)
                        CHECK(strstr(p, "CLAIM") != NULL);
                    if (campaign && cities && !claim && remote)
                        CHECK(strstr(p, "TRAVEL") != NULL);
                    if (campaign && cities && !claim && !remote)
                        CHECK(strstr(p, "TAKE") != NULL);
                }

    for (int campaign = 0; campaign <= 1; campaign++)
        for (int pack = 0; pack <= 1; pack++)
            for (int row = 0; row < 4; row++)
                for (int active = 0; active <= 1; active++) {
                    const char *p = st_eva_board_prompt(campaign, pack, row, active);
                    valid(p);
                    if (row < 3) {
                        CHECK((strstr(p, "A: TAKE") != NULL) == (campaign && pack));
                        if (!campaign)
                            CHECK(strstr(p, "START CAMPAIGN") != NULL);
                        else if (!pack)
                            CHECK(strstr(p, "JET PACK") != NULL);
                    } else {
                        CHECK(strstr(p, "A:") != NULL);
                        CHECK((strstr(p, "CANCEL") != NULL) == active);
                    }
                }

    printf("%d station prompt checks passed\n", checks);
    return 0;
}
