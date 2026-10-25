/* Saving the campaign (stage 2, P). The progress image (campaign.h) goes to Payback's EEPROM, in blocks of 8 bytes
   from block 64 up, in two slots so a cut in the middle of a save leaves the last good one; or, when the chip is only
   4 Kbit (or the emulator's save is), nowhere, and the player writes down a 16-letter password.
   Everything but the three functions at the end is plain C over a block device (SvDev), so a memory-card backend
   for another machine replaces sv_read / sv_write and nothing else. */
#ifndef SAVE_H
#define SAVE_H
#include "campaign.h"

#define SV_BLK 8                   /* bytes a block */
#define SV_DIR 64                  /* the directory block: proof that blocks 64 and up are ours */
#define SV_SLOT_A 72
#define SV_SLOT_B 112
#define SV_SLOT_BLKS 40            /* a header and up to 39 blocks of image */
#define SV_PAY_MAX 39

typedef struct {
    int (*rd)(int blk, u8 *b8);    /* 0: read */
    int (*wr)(int blk, const u8 *b8);   /* 0: written (and verified) */
} SvDev;

typedef struct {                   /* the slot the image was loaded from, and the next save's */
    u16 seq;
    u8 slot, valid;
} SvPick;

/* load the newest good slot into img (n bytes): 1, with pk set; 0 when neither slot is good */
int sv_load(const SvDev *d, u8 *img, int n, SvPick *pk);

/* a save in steps of one block: begin, then step until it returns 0 (done) or < 0 (the device failed) */
typedef struct {
    u16 seq, crc;                  /* the new slot's sequence number, the image's crc when the save began */
    u8 slot, k, nb, busy;          /* the slot to write, the next block, blocks in the image, a save is under way */
} SvW;
void sv_begin(SvW *w, const u8 *img, int n, const SvPick *pk);
int sv_step(const SvDev *d, SvW *w, const u8 *img, int n);
int sv_img_crc(const u8 *img, int n);   /* what a save of this image would keep: it changed if this is not w->crc */

/* the identify step (Payback's boot load): is the chip 64 Kbit? Everything it touches goes through SvEep */
typedef struct {
    int (*ident)(int kbit);        /* Payback's own: 4 or 64 sets the addressing of rd and wr */
    int (*rd)(int blk, u8 *b8);
    int (*wr)(int blk, const u8 *b8);
} SvEep;
enum { SV_4K, SV_64K };
int sv_probe(const SvEep *e);      /* only reads: SV_64K if a proof was made on this chip before, else SV_4K (addressing set to the answer) */
int sv_identify(const SvEep *e);   /* the whole proof, with the writes it needs; leaves the addressing set to the answer */

/* ---- the machine's ---- */
int sv_mode(void);                 /* SV_64K once the identify has proved the chip, else SV_4K (password only) */
extern const SvDev sv_eeprom;      /* blocks of Payback's EEPROM */
int sv_prove(void);                /* sv_identify on Payback's chip: 1 if blocks 64 and up are ours now */
int sf_eep_identify(int kbit);     /* build.py puts it in place of Payback's identify (the bl in its boot load) */

#endif
