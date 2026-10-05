"""Writes CHEATS.txt: codes that switch on the Stunt Fox cheats built into the hook (asm/editor.c).

Each cheat is one byte in RAM that the hook checks every tick, so a code only has to keep
writing 1 there. Codes are given as raw writes, CodeBreaker, and GameShark / Action Replay
v1-v2 (encrypted).
"""
import os

CHEATS = [
    (0x0203ffc0, 'Moon gravity', 'Jumps float: most of the fall is cancelled while you are in the air.'),
    (0x0203ffc6, 'Heavy gravity', 'The opposite: you drop like a brick. Do not use with Moon gravity.'),
    (0x0203ffc2, 'Hover car', 'Hold R to lift your car off the ground. Let go to fall. Land on rooftops!'),
    (0x0203ffc1, 'Overdrive', 'Holding A keeps accelerating past top speed, up to almost double.'),
    (0x0203ffc3, 'Nitro', 'Tap B while holding A for about two seconds of full thrust.'),
    (0x0203ffc4, 'Loop master', 'You never fall off a loop, however slow you go. Steering off the side still throws you.'),
    (0x0203ffc5, 'Debug readout', 'Every few seconds the ticker shows your cell X and Y, height, speed and vertical speed.'),
]

SEEDS = (0x09F4FBBD, 0x9681884A, 0x352027E9, 0xF3DEE5A7)
DELTA = 0x9E3779B9
M = 0xffffffff


def gsa_encrypt(addr, val):
    s = 0
    for _ in range(32):
        s = (s + DELTA) & M
        addr = (addr + ((((val << 4) + SEEDS[0]) ^ (val + s) ^ ((val >> 5) + SEEDS[1])) & M)) & M
        val = (val + ((((addr << 4) + SEEDS[2]) ^ (addr + s) ^ ((addr >> 5) + SEEDS[3])) & M)) & M
    return addr, val


def gsa_decrypt(addr, val):
    s = 0xC6EF3720
    for _ in range(32):
        val = (val - ((((addr << 4) + SEEDS[2]) ^ (addr + s) ^ ((addr >> 5) + SEEDS[3])) & M)) & M
        addr = (addr - ((((val << 4) + SEEDS[0]) ^ (val + s) ^ ((val >> 5) + SEEDS[1])) & M)) & M
        s = (s - DELTA) & M
    return addr, val


def codes(addr, value=1):
    raw = '%08X:%02X' % (addr, value)
    cb = '%08X %04X' % (0x30000000 | (addr & 0x0fffffff), value)    # CodeBreaker 8-bit write
    a, v = addr & 0x0fffffff, value                                  # GameShark v1/v2 8-bit write
    ea, ev = gsa_encrypt(a, v)
    assert gsa_decrypt(ea, ev) == (a, v)
    return raw, cb, '%08X %08X' % (ea, ev)


def text():
    out = ['PAYBACK: STUNT FOX - CHEAT CODES', '=' * 32, '',
           'These switch on cheats built into the Stunt Fox ROM (v8 or later). They do nothing on',
           'the original Payback. Each code keeps writing 1 to a switch byte the mod reads every tick.',
           '',
           'Formats:',
           '  RAW         address:value   (emulators with a raw / "Pro Action Replay" style memory poke)',
           '  CodeBreaker unencrypted      (Pizza Boy: Cheats > add > CodeBreaker)',
           '  GameShark / Action Replay v1-v2, encrypted',
           '',
           'Turn a cheat off by disabling its code; the game clears the switches when a level loads.',
           '']
    for addr, name, desc in CHEATS:
        raw, cb, gs = codes(addr)
        out += [name, '-' * len(name), desc,
                '  RAW          ' + raw,
                '  CodeBreaker  ' + cb,
                '  GameShark/AR ' + gs, '']
    out += ['Adding your own', '---------------',
            'Any Payback RAM poke works too. Useful addresses (see docs/payback-notes.md):',
            '  03000C60  table of entity pointers; 02001DB8 (16-bit) = index of the vehicle you drive',
            '  entity +04 / +08 / +0C   X, Y, Z (32-bit; 2048 per map cell; Z is smaller when higher)',
            '  entity +40 / +42 / +44   X, Y, vertical speed (16-bit; vertical is positive downward)',
            '  02001D39  1 in free roam, 0 in the story',
            'Avoid 0203FFC0-0203FFFF: the mod keeps its loop, build mode and cheat state there.',
            'To bake a cheat into the ROM, add a line to cheats() in asm/editor.c, run asm/build.sh',
            'and build.py again.', '']
    return '\n'.join(out)


if __name__ == '__main__':
    here = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(here, '..', 'CHEATS.txt')
    open(path, 'w').write(text())
    print('wrote', os.path.normpath(path))
