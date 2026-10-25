/* The Fox Campaign (stage 2, P): the saved progress image, and what the rest of the game asks of it. campaign.c
   runs the chapters over the mission engine's blob, holds Payback's level open until the acts are done, picks the
   next level and travels; save.c keeps the image in EEPROM (or as a password). Plain C: the image and its codec
   build on the PC (tests/save). */
#ifndef CAMPAIGN_H
#define CAMPAIGN_H
#include "gba.h"

#define CP_CHAPS 12                /* eleven cities and the reserved twelfth (stage 3) */
#define CP_BEST 64                 /* best times kept: 5 a chapter */
#define PROG_MAGIC 0x32504653      /* 'SFP2' */
#define PROG_VER 1

/* the progress, as it is saved (little-endian, no pointers). Bit i of acts[c] is act i + 1 of chapter c (the
   chapter's number in the campaign blob: its order, not its map) done; chal[c] and medals[c] bit i the i-th
   challenge or medal of the chapter; contracts[c] the contracts done, saturating */
typedef struct {
    u32 magic;                     /* PROG_MAGIC */
    u16 ver, crc;                  /* PROG_VER; crc16 of every byte after this word */
    u8 chap_unlocked, chap_cur, flags, ace;   /* the furthest chapter open; the one playing; CPF_*; the finale was won (Ace mode) */
    u8 acts[CP_CHAPS];
    u16 chal[CP_CHAPS];
    u8 medals[CP_CHAPS];
    u8 contracts[CP_CHAPS];
    u8 sg[32];                     /* SgProgress: credits, upgrades, paint, the space medals (spacegame.h) */
    u8 story[8];                   /* [0] bit n - 1 the campaign flag n (CP_FLAG_*: 1 Kestrel defected, 2 the finale was won); [1] bit n - 1 the unlock n (CP_UNLOCK_*) */
    u16 best[CP_BEST];             /* best times, 1/10 s, 0 none */
    u8 spare[20];
} Prog;                            /* 260 bytes */
#ifdef __arm__
_Static_assert(sizeof(Prog) == 260, "Prog");
#endif
enum { CPF_ON = 1, CPF_PW = 2 };   /* flags: the campaign is running; the image came from a password (no best times, medals) */
enum { CP_FLAG_KESTREL = 1, CP_FLAG_FINALE = 2 };   /* campaign.sfc's FLAG_* numbers: OP_SET's `a` */
enum { CP_UNLOCK_QUARTERS = 1, CP_UNLOCK_GHOST = 2 };   /* campaign.sfc's UNLOCK_*: OP_UNLOCK's `a`; 16 + n is paint n */

/* ---- save.c: the codec and the slots (plain C) ---- */
u16 sv_crc16(const void *p, int n);
void prog_seal(Prog *p);           /* magic, version and crc */
int prog_ok(const Prog *p);        /* sealed and in range */
#define PW_LEN 16
#define PW_ALPHA "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
void pw_encode(const Prog *p, char out[PW_LEN + 1]);
int pw_decode(const char *s, Prog *p);   /* 1: a good code, p rebuilt from it (zeroed first); 0: wrong */

/* ---- campaign.c: for the other packages ---- */
extern Prog cp_prog;
int cp_active(void);               /* the campaign is running */
int cp_flag(int f);                /* campaign flag f (CP_FLAG_*) is set */
int cp_unlocked(int what);         /* CP_UNLOCK_QUARTERS, CP_UNLOCK_GHOST */
int cp_ace(void);                  /* Ace mode: the finale was won (foes hp x 1.5, pars x 0.8: E and K ask) */
/* travel to chapter c (its index in the blob): 1 now (a rampage level is left through its end screens), 2 booked for the end
   of this story level, 0 not open */
int cp_travel(int c);
void cp_open(void);                /* the campaign's quick menu (the station's own menu opens it) */
int cp_pw_apply(const char *code); /* a typed code: 1 and the campaign continues from it, 0 wrong */

#endif
