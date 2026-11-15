.section .rodata
.balign 4
.global world_blob
world_blob: .incbin "build/w0/WORLD.SFW"
.balign 4
.global atlas_blob
atlas_blob: .incbin "build/w0/ATLAS.VRM"
.balign 4
.global clut_blob
clut_blob: .incbin "build/w0/CLUT.BIN"
.balign 4
.global side_blob
side_blob: .incbin "build/w0/SIDE.BIN"
.balign 4
.global font_blob
font_blob: .incbin "build/w0/FONT.VRM"
