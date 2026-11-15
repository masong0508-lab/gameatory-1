"""Pruning configuration: guest functions of Payback's software renderer replaced by stubs (RT_STUB records id,r0..r3 into the draw list).
id -> (guest entry, name).  Verified by the lockstep runs (stubbed on the ARM side too)."""
STUBS={
 1:(0x0806c82c,'gfx_fade_flip'),      # palette fade + page flip driver (RAM-code span template, 72.6% of boot MIPS insns)
 2:(0x08028ac4,'gfx_blit_image'),     # clip + dispatch of IWRAM row blitters (0x3005eb8) ROM image -> VRAM
 4:(0x08028c08,'gfx_blit_image_m4'),  # mode-4 merge blit (IWRAM 0x3005f68), 35% of ARM insns
 3:(0x080234be,'gfx_effect'),
 5:(0x03000580,'gfx_view3d'),         # IWRAM 3D view / texture-mapper entry (called from the main loop 0x8022f26)         # per-pixel colour effect + IWRAM mapper call
}
def stub_by_addr(): return {a:i for i,(a,n) in STUBS.items()}
def stub_dict(): return {a:(n,i) for i,(a,n) in STUBS.items()}
SWI_STUB=open(__file__.rsplit('/',1)[0]+'/t/swi5.bin','rb').read() if '/' in __file__ else open('t/swi5.bin','rb').read()
