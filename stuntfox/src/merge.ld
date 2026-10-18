/* Stunt Fox inside Payback (Europe): where everything goes in Payback's memory.

   rom:   the space the patched ROM frees by moving Payback's map column table above 8 MiB,
          close enough to Payback's code for a direct call
   hot:   IWRAM code of Payback's world renderer (and a neighbour no interrupt uses); ours from
          the first sf_frame on, and put back from Payback's ROM image only for its renderer
          (merge.c, hot_install)
   hot2:  more of Payback's IWRAM code, some of which it runs every frame: ours only while
          sf_frame runs, then put back from Payback's ROM image
   hot3:  the same, but kept aside in keep (hot3_save) and put back from there, as one byte of
          it is not what the ROM image holds
   hot4..hot11: more of Payback's IWRAM code, never run, read or written in play (it is only
          what its ROM image holds). hot4, hot6, hot7, hot8, hot10 and hot11 are not touched
          anywhere else either once Payback has copied its code in at power-on (watched: the
          menus, title, films, VIEW REPLAY, pause, deaths, a level's end and the loads), and what
          calls to their code can be traced come from Payback's world renderer: they stay ours
          like hot. hot5 (the menus run it), hot6b (VIEW REPLAY and the menus run code there)
          and hot9 (the pause menu runs it) are lent like hot2, hot6b kept aside in scr2
          (hot6b_save): what Payback left there is not its image. hot4 starts past 0x03005034, which the menus read; hot6b ends
          at 0x03007388, where a level load writes. hot6 ends at 0x030072c0: VIEW REPLAY's code at
          0x030072e8 (in hot6b) keeps nine words there, written while hot6 is ours. hot9 and hot11 leave out the word at
          0x03005c94 between them, which Payback's code writes (and hot2 ends where Payback's
          code that it runs outside our frame starts, 0x03006150)
   keep:  our variables, in EWRAM above everything Payback writes in play: its VIEW REPLAY
          recorder (from 0x0203c720) grows about 9 bytes a second and used to run on through
          here (and its clears with it), so build.py caps it at 0x0203cfe8. Up to STATE
          (0x0203ffd0, src/merge.c), where the checked copy of the player's progress lives.
          The first word is a canary: if anything else ever writes there, we start over.
   poola: slots 17 on of Payback's copies of the cells it changes (CUBE_BeginModify: 200 of
          64 bytes from 0x02003f24), for the polygons we rebuild every frame (Real Park from
          high up wants 9.8 of its 10.2 KB). The pool starts past the slots in use and gives
          the ones it covered back after drawing (render.c pool_floor, r_end)
   scr, scr2: what else we rebuild every frame, in EWRAM that nothing touches (watched, read
          and write, on all 11 maps in rampage with the mission phone answered, in the pause
          menu and across a level's end, load and start): scr behind Payback's effect records,
          scr2 between bits of its mission data (its first 253 bytes under the sentence of
          Payback's crime report, which a death or a bust writes in its tick and nothing reads:
          see memmap.txt; nothing in scr2 outlives our frame). Not past its goal list
          (0x0201a7e0, up to 99 goals of 0x24 bytes: Isla Nublar has 7) or in its command queue
          (0x0201b5f0, 0x28 a command), which grow into what looks free in a short watch
   radio: the car radio's state (src/radio.c), above STATE and the 5 words after it (the
          progress copy): only the boot clears it, so it lives through level loads, and the
          sound interrupt can use it at any time */
MEMORY {
    rom   (rx)  : ORIGIN = 0x081b0000, LENGTH = 0x146000
    hot   (rwx) : ORIGIN = 0x030030b0, LENGTH = 0x1a40
    hot2  (rwx) : ORIGIN = 0x03005ec0, LENGTH = 0x290
    hot3  (rwx) : ORIGIN = 0x03004b00, LENGTH = 0x2f0
    hot4  (rwx) : ORIGIN = 0x03005038, LENGTH = 0x6fc
    hot5  (rwx) : ORIGIN = 0x03000f0c, LENGTH = 0x394
    hot6  (rwx) : ORIGIN = 0x03006930, LENGTH = 0x990
    hot6b (rwx) : ORIGIN = 0x030072c8, LENGTH = 0xc0
    hot7  (rwx) : ORIGIN = 0x030012ac, LENGTH = 0x198
    hot8  (rwx) : ORIGIN = 0x0300212c, LENGTH = 0x130
    hot9  (rwx) : ORIGIN = 0x03005bd0, LENGTH = 0xc4
    hot10 (rwx) : ORIGIN = 0x03002260, LENGTH = 0x68
    hot11 (rwx) : ORIGIN = 0x03005c98, LENGTH = 0x64
    keep  (rw)  : ORIGIN = 0x0203d000, LENGTH = 0x2fc0
    radio (rw)  : ORIGIN = 0x0203ffec, LENGTH = 0x14
    poola (rw)  : ORIGIN = 0x02004374, LENGTH = 0x28bc
    scr   (rw)  : ORIGIN = 0x02017fc4, LENGTH = 0x1440
    scr2  (rw)  : ORIGIN = 0x020075a8, LENGTH = 0x3e4
}
SECTIONS {
    .text : { KEEP(*(.text.sf_frame)) KEEP(*(.text.sf_keyhook)) KEEP(*(.text.sf_menu)) KEEP(*(.text.sf_fade)) KEEP(*(.text.sf_fade_add)) KEEP(*(.text.sf_fade_zoom)) KEEP(*(.text.sf_fade_mul)) KEEP(*(.text.sf_fade_mul2)) KEEP(*(.text.sf_phys)) KEEP(*(.text.sf_pick_rand)) KEEP(*(.text.sf_studio_film)) KEEP(*(.text.sf_intro_film)) KEEP(*(.text.sf_mus)) KEEP(*(.text.sf_seq)) KEEP(*(.text.sf_play)) KEEP(*(.text.sf_eep)) KEEP(*(.rodata.sf_menu_logo)) *(.text .text.*) *(.coldtext) *(.rodata .rodata.*) . = ALIGN(4); } > rom
    .hot : { __hot_start = .; *(.iwram .iwram.*) . = ALIGN(4); __hot_end = .; } > hot AT > rom
    __hot_lma = LOADADDR(.hot);
    .hot2 : { __hot2_start = .; *(.iwram2 .iwram2.*) . = ALIGN(4); __hot2_end = .; } > hot2 AT > rom
    __hot2_lma = LOADADDR(.hot2);
    .hot3 : { __hot3_start = .; *(.iwram3 .iwram3.*) . = ALIGN(4); __hot3_end = .; } > hot3 AT > rom
    __hot3_lma = LOADADDR(.hot3);
    .hot4 : { __hot4_start = .; *(.iwram4 .iwram4.*) . = ALIGN(4); __hot4_end = .; } > hot4 AT > rom
    __hot4_lma = LOADADDR(.hot4);
    .hot5 : { __hot5_start = .; *(.iwram5 .iwram5.*) . = ALIGN(4); __hot5_end = .; } > hot5 AT > rom
    __hot5_lma = LOADADDR(.hot5);
    .hot6 : { __hot6_start = .; *(.iwram6 .iwram6.*) . = ALIGN(4); __hot6_end = .; } > hot6 AT > rom
    __hot6_lma = LOADADDR(.hot6);
    .hot6b : { __hot6b_start = .; *(.iwram6b .iwram6b.*) . = ALIGN(4); __hot6b_end = .; } > hot6b AT > rom
    __hot6b_lma = LOADADDR(.hot6b);
    .hot7 : { __hot7_start = .; *(.iwram7 .iwram7.*) . = ALIGN(4); __hot7_end = .; } > hot7 AT > rom
    __hot7_lma = LOADADDR(.hot7);
    .hot8 : { __hot8_start = .; *(.iwram8 .iwram8.*) . = ALIGN(4); __hot8_end = .; } > hot8 AT > rom
    __hot8_lma = LOADADDR(.hot8);
    .hot9 : { __hot9_start = .; *(.iwram9 .iwram9.*) . = ALIGN(4); __hot9_end = .; } > hot9 AT > rom
    __hot9_lma = LOADADDR(.hot9);
    .hot10 : { __hot10_start = .; *(.iwram10 .iwram10.*) . = ALIGN(4); __hot10_end = .; } > hot10 AT > rom
    __hot10_lma = LOADADDR(.hot10);
    .hot11 : { __hot11_start = .; *(.iwram11 .iwram11.*) . = ALIGN(4); __hot11_end = .; } > hot11 AT > rom
    __hot11_lma = LOADADDR(.hot11);
    .canary (NOLOAD) : { __keep_canary = .; . += 4; } > keep
    .data : { __data_start = .; *(.data .data.*) . = ALIGN(4); __data_end = .; } > keep AT > rom
    __data_lma = LOADADDR(.data);
    .bss (NOLOAD) : { __bss_start = .; *(.bss .bss.* COMMON .sbss .sbss.*) . = ALIGN(4); __bss_end = .; } > keep
    .noinit (NOLOAD) : { *(.noinit .noinit.*) } > keep
    .radio (NOLOAD) : { *(.radio) } > radio
    .scratch (NOLOAD) : { *(.scratch .scratch.*) . = ALIGN(4); } > scr
    .scratch2 (NOLOAD) : { *(.scratch2 .scratch2.*) . = ALIGN(4);
                           __hot6b_save = .; . += SIZEOF(.hot6b); } > scr2
    __pool_a = ORIGIN(poola);
    __pool_a_end = ORIGIN(poola) + LENGTH(poola);
    .assets : { . = ALIGN(4); *(.assets) } > rom
    .hooks : { KEEP(*(.text.sf_hook_*)) } > rom
    /DISCARD/ : { *(.ARM.exidx*) *(.ARM.attributes) *(.comment) }
}
