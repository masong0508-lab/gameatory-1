.section .rodata
.balign 4
.global font_blob
font_blob: .incbin "build/maps/FONT.VRM"
.balign 4
.global maps_lba
maps_lba: .word 0x4D415053, 0x31424C41     /* patched in the ISO by tools/mkiso_maps.py (first word: LBA of MAPS.BIN) */
