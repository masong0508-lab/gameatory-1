"""Build small 32-bit little-endian MIPS ELF files for tests: no toolchain, no game data."""
from __future__ import annotations

import struct


def mips_elf(text_words: list[int], functions: list[tuple[str, int, int]], data_words: list[int] = (),
             text_address: int = 0x80010000, data_address: int = 0x80020000) -> bytes:
    """An executable with .text (code words), .data (data words) and STT_FUNC symbols (name, byte offset in .text, byte size)."""
    text = b''.join(struct.pack('<I', w) for w in text_words)
    data = b''.join(struct.pack('<I', w) for w in data_words)
    strtab = bytearray(b'\0')
    symbols = [bytes(16)]
    for name, offset, size in functions:
        symbols.append(struct.pack('<IIIBBH', len(strtab), text_address + offset, size, 0x12, 0, 1))
        strtab += name.encode() + b'\0'
    symtab = b''.join(symbols)
    names = [b'', b'.text', b'.data', b'.symtab', b'.strtab', b'.shstrtab']
    shstrtab, name_offsets = bytearray(), []
    for name in names:
        name_offsets.append(len(shstrtab))
        shstrtab += name + b'\0'
    blobs = [text, data, symtab, bytes(strtab), bytes(shstrtab)]
    offsets, position = [], 52
    for blob in blobs:
        position += -position % 4
        offsets.append(position)
        position += len(blob)
    position += -position % 4
    section_headers = position
    body = bytearray(section_headers + 40 * len(names))
    struct.pack_into('<16sHHIIIIIHHHHHH', body, 0, b'\x7fELF\x01\x01\x01' + bytes(9), 2, 8, 1, text_address, 0,
                     section_headers, 0x1000, 52, 32, 0, 40, len(names), 5)
    for blob, offset in zip(blobs, offsets):
        body[offset:offset + len(blob)] = blob
    #            name type flags address offset size link info align entsize
    headers = [(0, 0, 0, 0, 0, 0, 0, 0, 0, 0),
               (name_offsets[1], 1, 6, text_address, offsets[0], len(text), 0, 0, 4, 0),
               (name_offsets[2], 1, 3, data_address, offsets[1], len(data), 0, 0, 4, 0),
               (name_offsets[3], 2, 0, 0, offsets[2], len(symtab), 4, 1, 4, 16),
               (name_offsets[4], 3, 0, 0, offsets[3], len(strtab), 0, 0, 1, 0),
               (name_offsets[5], 3, 0, 0, offsets[4], len(shstrtab), 0, 0, 1, 0)]
    for index, header in enumerate(headers):
        struct.pack_into('<10I', body, section_headers + 40 * index, *header)
    return bytes(body)


NOP, JR_RA, ADDIU_SP = 0x00000000, 0x03e00008, 0x27bdfff0
DIVU_A0_A1 = 0x0085001b           # divu $a0,$a1
TEQ_A1_ZERO_7 = 0x00a001f4        # teq $a1,$zero,7: MIPS II, what clang puts after a division without -mno-check-zero-division


def clean_program() -> bytes:
    """Two functions of R3000A code."""
    return mips_elf([ADDIU_SP, DIVU_A0_A1, JR_RA, NOP, JR_RA, NOP], [('divide', 0, 16), ('leaf', 16, 8)])


def trapping_program() -> bytes:
    """A division followed by the MIPS II zero-divisor trap inside function `divide` (offset 8)."""
    return mips_elf([ADDIU_SP, DIVU_A0_A1, TEQ_A1_ZERO_7, JR_RA, NOP], [('divide', 0, 20)])
