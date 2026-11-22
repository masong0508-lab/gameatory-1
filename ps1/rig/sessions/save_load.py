#!/usr/bin/env python3
"""Session e: save and load.  Process 1 starts on a blank card, makes a profile (slot, name), plays a moment, quits to the
title through the pause menu, and reads the card image: directory entry (name, blocks) and the save payload.  Process 2 is a
NEW process (cold boot) with that card: the slot list must show the saved name, the game menu must come without name entry,
and a level must start.

  python3 sessions/save_load.py --disc DISC.cue --out runs/e [--syms payback.elf]
  (internal second phase: --phase load --card runs/e/card_after.mcd --out runs/e/reboot)"""
import os, sys, subprocess, json
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from payback import *


def extra(ap):
    ap.add_argument('--phase', default='save', choices=('save', 'load'))
    ap.add_argument('--play-ticks', type=int, default=45, help='level clock ticks to play before quitting')


def card_report(g, tag):
    c = g.card_now()
    fs = c.files()
    for f in fs:
        g.log('  card %s: file %-22s %d block(s) %s, %d bytes, title %r' % (tag, f['name'], f['blocks'], f['block_list'], f['size'], f.get('title')))
    if not fs:
        g.log('  card %s: formatted %s, no files' % (tag, c.formatted()))
    pb = c.payback_save()
    if pb:
        g.log('  card %s: payload magic ok %s, version %s, sequence %s, %s bytes, crc ok %s' % (tag, pb.get('magic_ok'), pb.get('version'), pb.get('seq'), pb.get('n'), pb.get('crc_ok')))
    return c, fs, pb


def phase_save(a):
    g = open_game(a, 'save_load', card='blank')
    f = g.boot_to_language()
    g.check(f is not None, 'language screen drawn', 'frame %s' % f)
    off = g.assist_off()
    g.note('menu assist: %s' % ('plan blanked in RAM by the rig' if off else 'left as built'))
    r = g.pad_language_to_title()
    g.check(r.get('title') is not None, 'title menu reached', r)
    if r.get('title') is None:
        return g.finish('save_load')
    c, fs, pb = card_report(g, 'at the title menu')
    g.check(len(fs) == 1 and pb is not None and pb.get('crc_ok'), 'the runtime created its save file on the blank card', '%s; TTY: %s' % ([(x['name'], x['blocks']) for x in fs], g.tty_lines('MC ')[:2]))
    r2 = g.pad_title_to_level()
    g.check('game_menu' in r2, 'slot 1 taken, name entered: game menu', 'name entry shown: %s; slot list before: %s' % ('name' in r2, r2.get('slot_lines')))
    g.check(r2.get('level') is not None, 'rampage level started', 'frame %s' % r2.get('level'))
    g.card_idle()
    c1, fs1, pb1 = card_report(g, 'after the name entry')
    ee1 = pb1.get('eeprom') if pb1 else b''
    g.check(pb1 is not None and pb1.get('crc_ok') and pb1.get('seq', 0) > (pb.get('seq', 0) if pb else 0), 'the profile was written to the card (sequence number rose)', 'sequence %s > %s' % (pb.get('seq') if pb else None, pb1.get('seq') if pb1 else None))
    used = sum(1 for v in (ee1 or b'') if v != 0xff)
    at = DEFAULT_NAME.find(ee1 or b'')
    g.check(used > 16, 'the saved data is not empty', '%d of %d bytes differ from 0xFF; the default name as ASCII is %s' % (used, len(ee1 or b''), 'at offset %d' % at if at >= 0 else 'not in it (stored in another form)'))
    if r2.get('level') is not None:
        g.wait_clock(a.play_ticks, 20000)
        g.snap('playing')
        w = g.tap('START', until=lambda: g.on('PAUSED'), wait=8000, what='pause menu')
        g.settle(2)
        g.check(w is not None, 'pause menu opens', g.text()[:80])
        n = g.menu_goto(PAUSE_QUIT, PAUSE_MENU)
        g.snap('pause: quit entry selected')
        w = g.tap('CROSS', until=lambda: g.on(QUIT_QUESTION), wait=6000, what='the question')
        g.settle(2)
        g.snap('quit question')
        g.check(w is not None, 'the quit entry asks for a confirmation (Yes / No)', '%s; selected: %s' % (g.text()[:60], g.selected(['Yes', 'No'])))
        for _ in range(4):
            if g.wait_selected(['Yes', 'No']) == 'Yes':
                break
            g.tap('LEFT', hold_polls=1)
        g.check(g.selected(['Yes', 'No'], frames=6) == 'Yes', 'Left moves the answer to Yes', g.selected(['Yes', 'No'], frames=6))
        w = g.tap('CROSS', until=lambda: g.at_title() or g.at_game_menu(), wait=30000, what='a menu after quitting')
        g.ready()
        g.snap('after quitting')
        g.check(w is not None, 'Yes leaves the level', '%s frames after Cross; now on: %s (%s)' % (w, g.where(), g.text()[:90]))
        g.note('TTY at the quit: %s' % g.tty_lines('CONFLICT', 're-init')[-2:])
        g.card_idle()
        if g.at_game_menu():
            g.ready()
            g.menu_goto(GM_RAMPAGE, GAME_MENU)
            g.tap('CROSS', until=g.at_rampage, what='rampage setup')
            g.ready()
            g.menu_goto(START, [START, 'Cancel'])
            r0 = g.v('st3_render')
            w = g.tap('CROSS', until=lambda: not g.at_rampage() and 0 < g.level_clock() < 60, wait=16000, what='level clock of the second level')
            ok2, det = level_view(g, r0) if w is not None else (False, 'the level clock did not start: %s' % g.text()[:60])
            g.snap('second level')
            g.check(ok2, 'a second level starts after quitting, with the 3D city', det)
            g.wait_clock(20, 9000)
            g.snap('second level, 20 ticks on')
    c2, fs2, pb2 = card_report(g, 'after quitting to the title')
    g.check(len(fs2) == 1 and fs2[0]['blocks'] >= 1 and fs2[0]['cksum_ok'], 'card directory: one save file', [(x['name'], '%d blocks' % x['blocks']) for x in fs2])
    g.check(pb2 is not None and pb2.get('magic_ok') and pb2.get('crc_ok'), 'save payload: magic and CRC are good', 'sequence %s' % (pb2.get('seq') if pb2 else None))
    g.note('quitting wrote the card again: %s (sequence %s > %s)' % (pb2 and pb1 and pb2.get('seq') != pb1.get('seq'), pb1.get('seq') if pb1 else None, pb2.get('seq') if pb2 else None))
    card_path = os.path.join(g.out, 'card_after.mcd')
    g.save_card(card_path)
    faults = g.tty_faults()
    g.check(not faults, 'no fault text on the TTY', faults[:3])
    rc = g.finish('save_load (process 1: save)', sheet_cols=4)
    # ---- process 2: cold boot with that card
    print('---- starting a new process with %s' % card_path, flush=True)
    cmd = [sys.executable, os.path.abspath(__file__), '--phase', 'load', '--disc', a.disc, '--core', a.core, '--out', os.path.join(g.out, 'reboot'), '--card', card_path, '--state-dir', a.state_dir]
    if a.syms:
        cmd += ['--syms', a.syms]
    rc2 = subprocess.call(cmd)
    print('save_load: process 1 %s, process 2 %s' % ('ok' if rc == 0 else 'has FAILs', 'ok' if rc2 == 0 else 'has FAILs'), flush=True)
    return 1 if (rc or rc2) else 0


def phase_load(a):
    g = open_game(a, 'save_load_reboot')
    c0, fs0, pb0 = card_report(g, 'as inserted')
    g.check(len(fs0) == 1, 'the card carried over holds the save file', [(x['name'], x['blocks']) for x in fs0])
    w = g.wait_until(lambda: (g.at_language() and g.on('Italiano')) or g.dispcnt() == 0x404 or g.at_title(), 9000, step=4, what='first screen')
    off = g.assist_off()
    first = 'language' if g.at_language() else ('title' if g.at_title() else 'logos')
    g.snap('first screen: %s' % first)
    loaded = [l for l in g.tty().splitlines() if l.startswith('MC ')]
    g.check(any('MC loaded' in l for l in loaded), 'the runtime reports the save as loaded', loaded[:3])
    g.note('first screen after the cold boot with a save: %s' % first)
    if first == 'language':
        g.settle(2, 3000)
        r = g.pad_language_to_title()
    elif first == 'logos':
        r = g.pad_logos_to_title()
    else:
        r = {'title': g.nrun}
    g.check(r.get('title') is not None, 'title menu reached', r)
    if r.get('title') is None:
        g.snap('stuck')
        return g.finish('save_load (process 2: cold boot with the card)')
    g.title_goto(0)
    w = g.tap('CROSS', until=g.at_slots, what='slot list')
    g.ready()
    g.snap('slot list')
    lines = [l for l in g.screen() if not same_text(l, SLOTS_HEADING) and l != 'Cancel']
    used = [l for l in lines if 'UNUSED' not in l]
    g.check(w is not None and bool(used), 'the slot list shows the saved game', 'slots: %s' % lines)
    g.check(any(contains(l, DEFAULT_NAME) for l in used), 'the saved name (the default one) is in slot 1', used)
    w = g.tap('CROSS', until=lambda: g.at_name() or g.at_game_menu(), what='game menu')
    g.ready()
    g.snap('after choosing the slot')
    g.check(w is not None and g.at_game_menu(), 'choosing the used slot goes straight to the game menu (no name entry)', g.text()[:80])
    if g.at_game_menu():
        n = g.menu_goto(GM_RAMPAGE, GAME_MENU)
        w = g.tap('CROSS', until=g.at_rampage, what='rampage setup')
        g.ready()
        g.snap('rampage setup')
        g.note('rampage setup: %s' % ' | '.join(g.screen()))
        g.menu_goto(START, [START, 'Cancel'])
        r0 = g.v('st3_render')
        w = g.tap('CROSS', until=lambda: g.level_clock() > 0, wait=14000, what='level clock')
        ok = w is not None and g.wait_clock(6, 9000) is not None
        okv, det = level_view(g, r0) if ok else (False, g.text()[:80])
        g.snap('level from the loaded profile')
        g.check(ok and okv, 'a level starts from the loaded profile, with the 3D city', det)
    c1, fs1, pb1 = card_report(g, 'at the end')
    g.check(pb1 is not None and pb1.get('crc_ok'), 'the save on the card is still valid', 'sequence %s' % (pb1.get('seq') if pb1 else None))
    faults = g.tty_faults()
    g.check(not faults, 'no fault text on the TTY', faults[:3])
    return g.finish('save_load (process 2: cold boot with the card)', sheet_cols=4)


if __name__ == '__main__':
    a = std_args(__doc__, extra)
    sys.exit(phase_save(a) if a.phase == 'save' else phase_load(a))
