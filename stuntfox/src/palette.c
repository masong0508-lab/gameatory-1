/* The palette: 15 materials x 4 light levels x 4 fog levels, plus a 16-colour sky ramp. */
#include "palette.h"

/* base colours, 5 bits per channel */
static const u8 base[16][3] = {
    {0, 0, 0},       /* sky row, filled separately */
    {7, 7, 10},      /* road */
    {19, 19, 18},    /* kerb */
    {6, 17, 7},      /* grass */
    {21, 17, 12},    /* plaza */
    {20, 20, 21},    /* concrete */
    {8, 15, 25},     /* glass */
    {23, 10, 8},     /* brick */
    {5, 21, 20},     /* teal */
    {27, 25, 18},    /* cream */
    {12, 13, 17},    /* steel */
    {5, 10, 29},     /* car body: Blue Falcon blue */
    {31, 27, 4},     /* accent yellow */
    {28, 28, 29},    /* ship white */
    {31, 14, 3},     /* engine glow */
    {31, 6, 11},     /* stunt red */
};
static const u8 light[4] = {12, 17, 22, 27};   /* of 27 */
u16 *palette_out = (u16 *)PAL_BG;

static u16 rgb(int r, int g, int b)
{
    if (r < 0) r = 0;
    if (g < 0) g = 0;
    if (b < 0) b = 0;
    if (r > 31) r = 31;
    if (g > 31) g = 31;
    if (b > 31) b = 31;
    return r | g << 5 | b << 10;
}

void palette_set(const u8 *zenith, const u8 *horizon, const u8 *fog)
{
    for (int i = 0; i < 16; i++) {           /* sky ramp: 0 zenith .. 15 horizon */
        palette_out[i] = rgb(zenith[0] + (horizon[0] - zenith[0]) * i / 15,
                        zenith[1] + (horizon[1] - zenith[1]) * i / 15,
                        zenith[2] + (horizon[2] - zenith[2]) * i / 15);
    }
    for (int m = 1; m < 16; m++)
        for (int l = 0; l < 4; l++)
            for (int f = 0; f < 4; f++) {
                int r = base[m][0] * light[l] / 27, g = base[m][1] * light[l] / 27, b = base[m][2] * light[l] / 27;
                int k = f * 5;                   /* fog weight of 16 */
                palette_out[m * 16 + l * 4 + f] = rgb(r + (fog[0] - r) * k / 16, g + (fog[1] - g) * k / 16,
                                                 b + (fog[2] - b) * k / 16);
            }
}
