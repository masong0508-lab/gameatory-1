#!/usr/bin/env python3
"""gba_ref_intro.py: what the ORIGINAL GBA game does after the three logos, as a reference for sessions/boot_to_title.py.

  python3 tools/gba_ref_intro.py --rom GAME.gba --out runs/gba_ref [--frames 9000] [--harness DIR]

GAME.gba is your own dump of the cartridge (never part of the repository).  Runs it in mGBA through the repository's
libmgba harness (ps1/stage7/integration/mgba/emu.py, needs libmgba; --harness DIR or RIG_MGBA_HARNESS picks another copy):
  branch 'idle':  A on the language screen, then no input; a picture every --every frames, scene changes listed, and the
                  frame at which the title menu appears (idle_title.png);
  branch 'title': A during the second logo (the way the PS1 rig reaches the title menu), for a reference title picture
                  (title_ref.png);
  branch 'skip':  from the same point, A, START or B pressed at --skip-at frames after the third logo appeared: frames until
                  the title menu (sheet_skip_A/START/B.png);
  branch 'view':  title menu, intro entry, then no input (sheet_view_idle.png) or A after 600 frames (sheet_view_A.png):
                  frames until the title menu is back.
Writes those sheets and OUT/ref.json (GBA frame numbers of every scene change and the figures above).  The pictures show
the game: keep OUT out of the repository.
GBA frames here are frames emulated by mGBA since power-on (one per vblank)."""
import argparse, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
RIG = os.path.dirname(HERE)
sys.path.insert(0, RIG)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--rom', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--harness', default=os.environ.get('RIG_MGBA_HARNESS') or os.path.join(RIG, '..', 'stage7', 'integration', 'mgba'),
                    help='directory of the mGBA harness emu.py (default: $RIG_MGBA_HARNESS, else ps1/stage7/integration/mgba)')
    ap.add_argument('--frames', type=int, default=9000, help='GBA frames to watch after the language screen')
    ap.add_argument('--every', type=int, default=30)
    ap.add_argument('--skip-at', type=int, default=600, help='frames after the third logo at which the skip branch presses')
    a = ap.parse_args()
    if not os.path.isfile(os.path.join(a.harness, 'emu.py')):
        sys.exit('no mGBA harness: %s has no emu.py (give --harness DIR or set RIG_MGBA_HARNESS)' % os.path.abspath(a.harness))
    if not os.path.isfile(a.rom):
        sys.exit('no cartridge image at %s' % a.rom)
    sys.path.insert(0, os.path.abspath(a.harness))
    from emu import Emu
    from PIL import Image
    from ps1game import contact_sheet, diff, lum
    os.makedirs(a.out, exist_ok=True)
    e = Emu(a.rom)

    def pic():
        return Image.fromarray(e.frame)

    # power on, language screen
    e.run(240, [])
    lang = pic()
    st_lang = e.save_state()
    st_lang = bytes(st_lang)
    ref = {'language_frame': e.frames}

    # ---------------- branch idle
    e.run(6, ['A']); e.run(24, [])
    items, changes, prev, logo3_at, last_scene = [(lang, 'f%d language' % ref['language_frame'])], [], None, None, None
    t0 = e.frames
    while e.frames - t0 < a.frames:
        e.run(a.every, [])
        im = pic()
        d = diff(im, prev) if prev is not None else 255.0
        if d > 6.0:
            changes.append({'frame': e.frames, 'lum': round(lum(im), 1), 'diff_prev': round(d, 1)})
            if len(items) < 60:
                items.append((im, 'f%d change %.0f' % (e.frames, d)))
        prev = im
    contact_sheet(items, os.path.join(a.out, 'sheet_idle.png'), cols=6, cell=(240, 160), title='GBA original, A on the language screen, then no input')
    ref['idle_scene_changes'] = changes
    # the first picture of the idle branch that is the title menu (the video pictures differ from it by 60 and more)
    # ---------------- branch title: A during the second logo (same as the PS1 rig's pad path)
    lf = ref['language_frame']
    e.load_state(st_lang)
    e.run(6, ['A']); e.run(24, [])
    e.run(224, [])
    e.run(6, ['A']); e.run(240, [])
    title = pic()
    ref['title_frame'] = lf + 30 + 224 + 6 + 240
    title.save(os.path.join(a.out, 'title_ref.png'))
    # ---------------- branch idle again, looking for the title picture (power-on relative frames)
    e.load_state(st_lang)
    e.run(6, ['A']); e.run(24, [])
    n = lf + 30
    ref['idle_title_frame'] = None
    while n < lf + 30 + a.frames:
        e.run(10, []); n += 10
        if diff(pic(), title) < 35.0:
            ref['idle_title_frame'] = n
            pic().save(os.path.join(a.out, 'idle_title.png'))
            break
    # ---------------- branch skip: no input until the third logo + skip_at, then A, later Start
    e.load_state(st_lang)
    e.run(6, ['A']); e.run(24, [])
    t1 = lf + 30
    e.run(3 * 164 + a.skip_at, [])
    f0 = t1 + 3 * 164 + a.skip_at
    before = pic()
    res = {}
    for key in ('A', 'START', 'B'):
        st = e.save_state()
        e.run(6, [key]); e.run(4, [])
        after = None
        n = 10
        while n < 3000:
            e.run(10, []); n += 10
            if diff(pic(), title) < 35.0:
                after = n
                break
        res[key] = {'pressed_at': f0, 'pressed_after_language_press': f0 - t1, 'title_after': after, 'diff_to_title_ref': round(diff(pic(), title), 1)}
        items2 = [(before, 'f%d before %s' % (f0, key)), (pic(), 'f%d %s +%d' % (f0 + n, key, n))]
        contact_sheet(items2 + [(title, 'title reference')], os.path.join(a.out, 'sheet_skip_%s.png' % key), cols=3, cell=(240, 160))
        e.load_state(st)
    ref['skip'] = res
    # ---------------- branch view: title menu, Down Down A (the intro entry), then no input until the title menu is back;
    # and the same with A pressed 600 frames into the video
    for label, press_at in (('view_idle', None), ('view_A', 600)):
        e.load_state(st_lang)
        e.run(6, ['A']); e.run(24, [])
        e.run(224, [])
        e.run(6, ['A']); e.run(240, [])
        for k in ('DOWN', 'DOWN'):
            e.run(6, [k]); e.run(30, [])
        e.run(6, ['A']); e.run(4, [])
        n, left, back, seq = 10, None, None, []
        while n < a.frames:
            e.run(10, [])
            n += 10
            d = diff(pic(), title)
            if left is None and d > 50.0:
                left = n
            if press_at is not None and n == press_at:
                e.run(6, ['A']); e.run(4, []); n += 10
            if left is not None and d < 35.0:
                back = n
                break
            if n % 300 == 0 and len(seq) < 18:
                seq.append((pic(), '%s +%d' % (label, n)))
        ref[label] = {'left_title_after': left, 'title_back_after': back, 'pressed_A_at': press_at}
        contact_sheet(seq + [(pic(), '%s end +%d' % (label, n))], os.path.join(a.out, 'sheet_%s.png' % label), cols=5, cell=(240, 160))
    json.dump(ref, open(os.path.join(a.out, 'ref.json'), 'w'), indent=1)
    print(json.dumps({k: v for k, v in ref.items() if k != 'idle_scene_changes'}, indent=1))
    print('scene changes (idle):', [(c['frame'], c['lum']) for c in changes][:80])


if __name__ == '__main__':
    main()
