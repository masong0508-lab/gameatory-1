#!/usr/bin/env python3
"""Host test of src/radio.c's choice of song (modes, skip), its banner and Street Jungle's loop: the file is compiled
for the PC with its hardware registers and Payback's functions replaced by stand-ins (tests/radio/radio_host.c).

    python3 tests/radio/run.py
"""
import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, '..', '..', 'src')

PRE = '''#include <stdint.h>
typedef unsigned char u8; typedef unsigned short u16; typedef unsigned int u32; typedef signed char s8; typedef short s16; typedef int s32;
#define TEXT_W 6
#define COLOR(m,l,f) 0
#define M_ROAD 1
#define M_GLOW 2
enum { KEY_SELECT = 4, KEY_R = 256 };
u16 fake_ime, fake_key = 0xffff;
extern int fake_rand(int); extern void fake_play(int); extern const char *fake_text(int);
static int last_w; static char last_text[64];
char *d_cat(char *, const char *); void d_fill(int,int,int,int,int); void d_text(int,int,const char*,int);
extern u8 opt_theme;
#define PB_SONG_V (*(volatile s16 *)0x020001c8)
#define PB_VOL_V (*(volatile s16 *)0x020001ca)
#define PB_ENDED_V (*(volatile u8 *)0x02001ce6)
'''


def main():
    s = open(os.path.join(SRC, 'radio.c')).read()
    s = re.sub(r'#include "[a-z0-9_.]+"\n', '', s)
    for old, new in (('REG_IME', 'fake_ime'), ('REG_KEYINPUT', 'fake_key'),
                     ('#define PB_PLAY ((void (*)(int))0x08076c99)', '#define PB_PLAY fake_play'),
                     ('#define PB_TEXT ((const char *(*)(int))0x0803dc8d)', '#define PB_TEXT fake_text'),
                     ('#define PB_RADIO_RAND ((int (*)(int))0x08077eb1)', '#define PB_RADIO_RAND fake_rand'),
                     ('struct radio radio __attribute__((section(".radio")));', 'struct radio radio;')):
        assert old in s, old
        s = s.replace(old, new)
    h = re.sub(r'#include "gba.h"\n', '', open(os.path.join(SRC, 'radio.h')).read())
    with tempfile.TemporaryDirectory() as d:
        open(os.path.join(d, 'radio_h.c'), 'w').write(PRE + h + s)
        subprocess.run(['cc', '-O1', '-w', '-I', d, '-o', os.path.join(d, 't'), os.path.join(HERE, 'radio_host.c')], check=True)
        r = subprocess.run([os.path.join(d, 't')])
    sys.exit(r.returncode)


if __name__ == '__main__':
    main()
