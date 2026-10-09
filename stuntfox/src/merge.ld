/* Stunt Fox inside Payback (Europe): where everything goes in Payback's memory.

   rom:   the space the patched ROM frees by moving Payback's map column table above 8 MiB,
          close enough to Payback's code for a direct call
   hot:   IWRAM code of Payback's world renderer (and a neighbour no interrupt uses); ours
          while sf_frame runs, then put back from Payback's ROM image
   hot2:  more of Payback's IWRAM code that nothing runs or reads in play (watched on foot, driving
          and flying), borrowed the same way
   hot3:  the same, but kept aside in keep (hot3_save) and put back from there, as one byte of
          it is not what the ROM image holds
   keep:  our variables, in EWRAM above everything Payback uses in its city (its highest
          write in play is 0x0203c8d3; its level loader clears this, and so do we start over).
          The first word is a canary: if anything else ever writes there, we start over.
   pool*, scr: buffers of Payback's world renderer, for what we rebuild every frame. Its
          per-entity effect records (0x02015bc4, 64 x 0x90 bytes) reach into poold after
          crashes, which is harmless for buffers rebuilt every frame. */
MEMORY {
    rom   (rx)  : ORIGIN = 0x081b0000, LENGTH = 0x146000
    hot   (rwx) : ORIGIN = 0x030030b0, LENGTH = 0x1950
    hot2  (rwx) : ORIGIN = 0x03005ec0, LENGTH = 0x300
    hot3  (rwx) : ORIGIN = 0x03004b00, LENGTH = 0x2f0
    keep  (rw)  : ORIGIN = 0x0203d000, LENGTH = 0x2f00
    poola (rw)  : ORIGIN = 0x02004374, LENGTH = 0x28bc
    scr   (rw)  : ORIGIN = 0x0201f7e0, LENGTH = 0x1fe0
    poolc (rw)  : ORIGIN = 0x0202f5e4, LENGTH = 0x818
    poold (rw)  : ORIGIN = 0x02017268, LENGTH = 0x2154
}
SECTIONS {
    .text : { KEEP(*(.text.sf_frame)) KEEP(*(.text.sf_keyhook)) KEEP(*(.text.sf_fade)) KEEP(*(.text.sf_fade_add)) KEEP(*(.text.sf_fade_mul)) KEEP(*(.text.sf_fade_mul2)) *(.text .text.*) *(.rodata .rodata.*) . = ALIGN(4); } > rom
    .hot : { __hot_start = .; *(.iwram .iwram.*) . = ALIGN(4); __hot_end = .; } > hot AT > rom
    __hot_lma = LOADADDR(.hot);
    .hot2 : { __hot2_start = .; *(.iwram2 .iwram2.*) . = ALIGN(4); __hot2_end = .; } > hot2 AT > rom
    __hot2_lma = LOADADDR(.hot2);
    .hot3 : { __hot3_start = .; *(.iwram3 .iwram3.*) . = ALIGN(4); __hot3_end = .; } > hot3 AT > rom
    __hot3_lma = LOADADDR(.hot3);
    .canary (NOLOAD) : { __keep_canary = .; . += 4; } > keep
    .data : { __data_start = .; *(.data .data.*) . = ALIGN(4); __data_end = .; } > keep AT > rom
    __data_lma = LOADADDR(.data);
    .bss (NOLOAD) : { __bss_start = .; *(.bss .bss.* COMMON .sbss .sbss.*) . = ALIGN(4); __bss_end = .; } > keep
    .noinit (NOLOAD) : { *(.noinit .noinit.*) } > keep
    .scratch (NOLOAD) : { *(.scratch .scratch.*) . = ALIGN(4); __pool_b = .; } > scr
    __pool_b_end = ORIGIN(scr) + LENGTH(scr);
    __pool_a = ORIGIN(poola);
    __pool_a_end = ORIGIN(poola) + LENGTH(poola);
    __pool_c = ORIGIN(poolc);
    __pool_c_end = ORIGIN(poolc) + LENGTH(poolc);
    __pool_d = ORIGIN(poold);
    __pool_d_end = ORIGIN(poold) + LENGTH(poold);
    .assets : { . = ALIGN(4); *(.assets) } > rom
    /DISCARD/ : { *(.ARM.exidx*) *(.ARM.attributes) *(.comment) }
}
