#ifndef PS1_VRAM_H
#define PS1_VRAM_H

/* Coordinates and widths are VRAM halfwords, heights are rows. Keep the
 * complete persistent layout disjoint; tests cover the seven world pages,
 * both display buffers, both OBJ formats, HUD/font, models and PPU caches.
 */
#define PS1_VRAM_MODEL_X 960
#define PS1_VRAM_MODEL_Y 64
#define PS1_VRAM_MODEL_W 32
#define PS1_VRAM_MODEL_H 128
#define PS1_VRAM_MODEL_TPAGE_X 960
#define PS1_VRAM_MODEL_TPAGE_Y 0
#define PS1_VRAM_MODEL_CLUT_X 992
#define PS1_VRAM_MODEL_CLUT_Y 0
#define PS1_VRAM_MODEL_CLUT_W 16
#define PS1_VRAM_MODEL_CLUT_H 34

#define PS1_VRAM_PPU_ATLAS_X 576
#define PS1_VRAM_PPU_ATLAS_Y 256
#define PS1_VRAM_PPU_ATLAS_PAGES 2
#define PS1_VRAM_PPU_ATLAS_PAGE_W 128
#define PS1_VRAM_PPU_ATLAS_PAGE_H 256
#define PS1_VRAM_PPU_L1_X 832
#define PS1_VRAM_PPU_L1_Y 256
#define PS1_VRAM_PPU_L1_W 120
#define PS1_VRAM_PPU_L1_H 160
#define PS1_VRAM_PPU_OBJ_X 960
#define PS1_VRAM_PPU_OBJ4_Y 256
#define PS1_VRAM_PPU_OBJ8_Y 384
#define PS1_VRAM_PPU_OBJ_W 64
#define PS1_VRAM_PPU_OBJ_H 128
#define PS1_VRAM_PPU_CLUT_X 0
#define PS1_VRAM_PPU_CLUT_Y 496
#define PS1_VRAM_PPU_CLUT_W 256
#define PS1_VRAM_PPU_CLUT_H 4

/* The guest's pixel and tile formats fix these dimensions. Addresses can be
 * relocated, but changing shapes requires a corresponding converter change.
 */
_Static_assert(PS1_VRAM_PPU_ATLAS_PAGE_W == 128 && PS1_VRAM_PPU_ATLAS_PAGE_H == 256, "8-bit cache page dimensions");
_Static_assert(PS1_VRAM_PPU_L1_W == 120 && PS1_VRAM_PPU_L1_H == 160, "GBA mode 4 page dimensions");
_Static_assert(PS1_VRAM_PPU_OBJ_W == 64 && PS1_VRAM_PPU_OBJ_H == 128, "GBA OBJ conversion dimensions");
_Static_assert(PS1_VRAM_PPU_CLUT_W == 256 && PS1_VRAM_PPU_CLUT_H == 4, "GBA palette dimensions");
_Static_assert((PS1_VRAM_PPU_L1_X % 64) == 0 && (PS1_VRAM_PPU_L1_Y % 256) == 0, "L1 texture-page alignment");
_Static_assert((PS1_VRAM_PPU_OBJ_X % 64) == 0, "OBJ texture-page alignment");

#endif
