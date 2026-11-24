/* Exercise the production SgProgress codec and settings packer, including its
   private ship fields. Unused gameplay sections are removed by the host linker. */
#include <stdio.h>
#include <string.h>
#include <limits.h>
#include "../../src/spacegame.c"
#include "../../src/tree_lod.h"

u16 car_vmax_k, car_grip_k, ship_speed_k, draw_k, ent_far;
u16 car_accel_k, car_steer_k, car_boost_k, car_drift_mu, sw_pack_k;
u8 car_grav_k, car_boost_inf, rag_grav_k, rag_bounce, view_cut, far_fs;
u8 ship_engine, rag_on, rag_fall, rag_wacky, rag_unlock;
s32 tex_wall_far, tex_floor_far, tex_far;
static int host_radio;
int radio_mode(void) { return host_radio; }
void radio_set_mode(int m) { host_radio = m; }
void radio_retheme(void) {}

static int failures, checks;
#define CHECK(ok, label) do { checks++; if (!(ok)) { fprintf(stderr, "FAIL: %s\n", label); failures++; } } while (0)

static void options_default(void)
{
    const u8 zero[OPT_PROGRESS_BYTES] = {0};
    opt_set_progress(zero);
}

static void tree_detail_checks(void)
{
    u8 options[OPT_PROGRESS_BYTES] = {0}, packed[OPT_PROGRESS_BYTES];
    options_default();
    CHECK(opt_tree_detail == SF_TREE_NORMAL, "old zero-reserved options retain normal trees");
    CHECK(tree_detail_lod(2599, SF_TREE_NORMAL) == SF_TREE_NORMAL &&
          tree_detail_lod(2600, SF_TREE_NORMAL) == SF_TREE_MEDIUM &&
          tree_detail_lod(4199, SF_TREE_NORMAL) == SF_TREE_MEDIUM &&
          tree_detail_lod(4200, SF_TREE_NORMAL) == SF_TREE_SIMPLE,
          "normal distance tier boundaries are unchanged");
    CHECK(tree_detail_lod(1000, SF_TREE_MEDIUM) == SF_TREE_MEDIUM &&
          tree_detail_lod(4199, SF_TREE_MEDIUM) == SF_TREE_MEDIUM &&
          tree_detail_lod(4200, SF_TREE_MEDIUM) == SF_TREE_SIMPLE,
          "medium removes near crown detail without changing far tier");
    CHECK(tree_detail_lod(1000, SF_TREE_SIMPLE) == SF_TREE_SIMPLE &&
          tree_detail_lod(6000, SF_TREE_SIMPLE) == SF_TREE_SIMPLE &&
          tree_detail_lod(1000, 255) == SF_TREE_NORMAL,
          "simple caps all crown geometry; invalid cap uses normal");
    for (int code = 1; code <= 3; code++) {
        /* Existing option word 4: bit 29 is title-music, formerly zero
           bits 30-31 now store tree detail. Keep the former bit intact. */
        options[12] = (u8)(0x20 | code << 6);
        opt_set_progress(options);
        CHECK(opt_tree_detail == (code == 3 ? SF_TREE_NORMAL : code - 1),
              "tree choice decodes, invalid code returns to normal");
        CHECK(draw_k == 256 && prop_k == 256 && opt_tex,
              "tree detail does not shorten city/prop reach or disable textures");
        SgProgress image;
        sg_get_progress(&image);
        options_default();
        sg_set_progress(&image);
        opt_get_progress(packed);
        options[12] = (u8)(0x20 | (code == 3 ? 0 : code) << 6);
        CHECK(!memcmp(packed, options, sizeof packed),
              "detail survives whole equipment save and keeps other packed choices");
    }
    options_default();
}

static void example(void)
{
    credits = 12345; medals = 5; paints_got = 0x13f;
    laser_lv = 2; engine_lv = 1; rack_lv = 2; shield_lv = 1;
    missiles = 7; paint = 8; jobs_done = 9;
    sg_invert = 1; sg_autoaim = 0; sw_pack = 1;
    rag_on = 1; rag_fall = 1; rag_wacky = 1; rag_unlock = 1;
    radio_set_mode(2);
}

int main(void)
{
    SgProgress saved, got, old;
    u8 options[OPT_PROGRESS_BYTES], before[OPT_PROGRESS_BYTES], after[OPT_PROGRESS_BYTES];
    tree_detail_checks();
    options_default();
    example();
    sg_get_progress(&saved);
    CHECK(sizeof saved == 32, "SgProgress stays 32 bytes");
    CHECK(saved.spare[0] == 'S' && saved.spare[1] == 1, "extension has a magic and version");
    CHECK(saved.spare[2] == (31 | 2 << 5), "pack, ragdoll and radio flags are serialized");

    /* Different bit patterns cover every packed option word and invalid codes.
       Compare the canonical, range-checked image after a real codec round trip. */
    for (int k = 0; k < 128; k++) {
        for (int i = 0; i < OPT_PROGRESS_BYTES; i++)
            options[i] = k * 37 + i * 19;
        opt_set_progress(options);
        example();
        sg_get_progress(&saved);
        options_default();
        credits = 0; missiles = 0; sw_pack = rag_on = rag_fall = rag_wacky = rag_unlock = 0;
        radio_set_mode(0);
        sg_set_progress(&saved);
        sg_get_progress(&got);
        CHECK(!memcmp(&saved, &got, sizeof got), "all settings and ship progress round trip");
        CHECK(credits == 12345 && rack_lv == 2 && missiles == 7 && paint == 8,
              "paid equipment and selected paint restore");
        CHECK(sw_pack && rag_on && rag_fall && rag_wacky && rag_unlock && radio_mode() == 2,
              "jet pack, ragdolls and radio restore");
    }

    old = saved;
    memset(old.spare, 0, sizeof old.spare);
    options_default();
    opt_get_progress(before);
    sw_pack = 0; rag_on = rag_fall = rag_wacky = rag_unlock = 0; radio_set_mode(1);
    sg_set_progress(&old);
    opt_get_progress(after);
    CHECK(!memcmp(before, after, sizeof before) && !sw_pack && !rag_on && radio_mode() == 1,
          "old zero-spare saves preserve current extras and load on cold defaults");
    CHECK(credits == old.credits && rack_lv == old.rack && paint == old.paint,
          "legacy saves still restore their original fields");
    old.spare[0] = 'S'; old.spare[1] = 99;
    memset(old.spare + 2, 0xff, sizeof old.spare - 2);
    sg_set_progress(&old);
    opt_get_progress(after);
    CHECK(!memcmp(before, after, sizeof before) && !sw_pack && radio_mode() == 1,
          "unknown extension versions do not apply unrecognized bytes");

    memset(&old, 0xff, sizeof old);
    old.credits = -1;
    old.spare[0] = 'S'; old.spare[1] = 1;
    sg_set_progress(&old);
    CHECK(credits == 0 && medals == 0xfff && paints_got == 0xfff,
          "credits and unlock masks are bounded");
    CHECK(laser_lv == 2 && engine_lv == 2 && rack_lv == 2 && shield_lv == 2 && missiles == 8 && paint == 0,
          "out-of-range equipment and paint are clamped");
    CHECK(sg_invert == 1 && sg_autoaim == 1 && sw_pack == 1 && radio_mode() == 0,
          "boolean flags and invalid radio mode are sanitized");
    CHECK(car_vmax_k == 256 && ship_speed_k == 256 && sg_shield_k == 4 && car_accel_k == 256,
          "invalid multi-choice setting codes use their defaults");
    old.credits = INT_MAX;
    sg_set_progress(&old);
    CHECK(credits == 9999999, "credit upper limit is retained");
    printf("progress codec: %d checks, %d failures\n", checks, failures);
    return failures != 0;
}
