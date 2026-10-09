/* Stunt Fox inside Payback (Europe): where everything goes in Payback's memory.

   rom:   the space the patched ROM frees by moving Payback's map column table above 8 MiB,
          close enough to Payback's code for a direct call
   hot:   IWRAM code of Payback's world renderer (and a neighbour no interrupt uses); ours
          while sf_frame runs, then put back from Payback's ROM image
   keep:  our variables, in EWRAM above everything Payback uses in Freedom City (its highest
          write in play is 0x0203c8d3; its level loader clears this, and so do we start over).
          The first word is a canary: if anything else ever writes there, we start over.
   pool*, scr: buffers of Payback's world renderer, for what we rebuild every frame. Its
          per-entity effect records (0x02015bc4, 64 x 0x90 bytes) reach into poold after
          crashes, which is harmless for buffers rebuilt every frame. */
MEMORY {
    rom   (rx)  : ORIGIN = 0x081b0000, LENGTH = 0x146000
    hot   (rwx) : ORIGIN = 0x030030b0, LENGTH = 3352
    keep  (rw)  : ORIGIN = 0x0203d000, LENGTH = 0x2f00
    poola (rw)  : ORIGIN = 0x02004374, LENGTH = 0x28bc
    scr   (rw)  : ORIGIN = 0x0201f7e0, LENGTH = 0x1fe0
    poolc (rw)  : ORIGIN = 0x0202f5e4, LENGTH = 0x818
    poold (rw)  : ORIGIN = 0x02017268, LENGTH = 0x2154
}
SECTIONS {
    .text : { KEEP(*(.text.sf_frame)) KEEP(*(.text.sf_keyhook)) KEEP(*(.text.sf_fade)) *(.text .text.*) *(.rodata .rodata.*) . = ALIGN(4); } > rom
    .hot : { __hot_start = .; *(.iwram .iwram.*) . = ALIGN(4); __hot_end = .; } > hot AT > rom
    __hot_lma = LOADADDR(.hot);
    .canary (NOLOAD) : { __keep_canary = .; . += 4; } > keep
    .data : { __data_start = .; *(.data .data.*) . = ALIGN(4); __data_end = .; } > keep AT > rom
    __data_lma = LOADADDR(.data);
    .bss (NOLOAD) : { __bss_start = .; *(.bss .bss.* COMMON .sbss .sbss.*) . = ALIGN(4); __bss_end = .; } > keep
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
