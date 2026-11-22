#!/usr/bin/env python3
"""Session a: cold boot -> language -> logos -> (intro video) -> title menu; every title entry opens something and comes back.

  python3 sessions/boot_to_title.py --disc DISC.cue --out runs/a [--core pcsx_rearmed] [--syms payback.elf] [--save-state]
                                    [--entries controls,credits,language,delete,intro] [--no-idle-branch]
                                    [--intro-gframes 6000] [--intro-max-frames 60000]

Real pad input only.  Builds with a timed menu assist: the assist plan is blanked in RAM when --syms names it (stated in the
log); without that the assist's own presses arrive during the session and the entry checks may be cut short.

The intro checks are measured in GUEST frames (the runtime's g_gframes, i.e. GBA frames), against what the GBA original does
(payback.GBA_*; tools/gba_ref_intro.py): with no input the title menu comes 4590 GBA frames after the language press, after
the three logos and a video; A (Cross) during the video brings the title menu 100 frames later; the intro entry of the title
menu returns by itself after 4620 frames.  The budgets are --intro-gframes guest frames (default 6000, the GBA length plus 30 %), capped at
--intro-max-frames emulator frames.  Without symbols the guest frame count is not available and 4 emulator frames are taken
for one guest frame (the intro of RC v2 runs at about 14 guest frames per emulated second).
The title entries are named by payback.TITLE_ENTRIES: start, delete, intro, credits, controls, language."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from payback import *


def extra(ap):
    ap.add_argument('--save-state', action='store_true', help='write STATE_DIR/title.state when the title menu is reached')
    ap.add_argument('--entries', default='controls,credits,language,delete,intro',
                    help='title entries to open, by the names of payback.TITLE_ENTRIES')
    ap.add_argument('--no-idle-branch', action='store_true', help='skip the hands-off branch after the language screen')
    ap.add_argument('--intro-gframes', type=int, default=6000, help='guest frames to wait for the end of the intro video')
    ap.add_argument('--intro-max-frames', type=int, default=60000, help='emulator frame cap of that wait')


def gframes_or_est(g, f0):
    """Guest frames now; without symbols an estimate from emulator frames (4 per guest frame)."""
    x = g.gframes()
    return x if x is not None else (g.nrun - f0) // 4


def wait_guest(g, cond, gframes, max_frames, step=30):
    """Run until cond() or `gframes` more guest frames have passed (at most max_frames emulator frames).
    Returns (cond met, guest frames waited, emulator frames waited)."""
    f0 = g.nrun
    s0 = gframes_or_est(g, f0)
    g.wait_until(lambda: cond() or gframes_or_est(g, f0) - s0 >= gframes, max_frames, step=step)
    return cond(), gframes_or_est(g, f0) - s0, g.nrun - f0


def press_guest(g, button, cond, gframes, max_frames=12000):
    """Click a button (held until the runtime polled it twice), then wait up to `gframes` guest frames for cond()."""
    g.tap(button)
    return wait_guest(g, cond, gframes, max_frames, step=10)


def drawn_pictures(g, pics, ref):
    """Shape differences of the non-black pictures to a reference picture (0 = the same picture, also when faded)."""
    return [round(shape_diff(x, ref), 2) for x in pics if x is not None and not is_black(x) and ref is not None]


def main():
    a = std_args(__doc__, extra)
    g = open_game(a, 'boot_to_title')
    # ---- boot
    f = g.boot_to_language()
    g.snap('language')
    g.check(f is not None, 'language screen drawn', 'frame %s, text: %s' % (f, g.text()[:90]))
    g.check(all(g.on(x) for x in LANGUAGES), 'five languages listed')
    faults = g.tty_faults()
    g.check(not faults, 'no fault text on the TTY during boot', faults[:3])
    off = g.assist_off()
    g.note('menu assist: %s' % ('plan blanked in RAM by the rig (%s): pad input only from here' % ', '.join(off) if off
                                else 'no plan named by the symbols: whatever the build does stays active'))
    g.ready()
    g.snap('language, slid in')
    has_io = g.dispcnt() is not None
    logo3, logos = None, {}
    lang_state = os.path.join(g.out, 'language.state')
    if not has_io or g.save_state_file(lang_state, 'language screen, settled') is None:
        lang_state = None
    info = {}
    # ---- branch 1: language, then no input at all: the three logos, the intro video, and what comes after them
    if lang_state and not a.no_idle_branch:
        g.log('-- branch 1: Cross on the language screen, then hands off')
        gf_press, f_press = g.gframes(), g.nrun
        ok = g.tap('CROSS', until=lambda: not g.at_language(), wait=4000, what='language screen to close')
        g.wait_until(lambda: g.dispcnt() == 0x404, 4000, step=2, what='logo screen')
        g0 = g.gba_frame()
        prev = None
        for i, name in enumerate(('logo 1', 'logo 2', 'logo 3')):
            g.wait_until(lambda: g.gba_frame() >= g0 + 164 * i + 70, 6000, step=2)
            im = g.snap(name)
            d = diff(im, prev) if prev is not None else None
            g.check(not is_black(im) and g.dispcnt() == 0x404 and (d is None or d > 2.0), '%s is drawn (bitmap mode, differs from the one before)' % name,
                    'frame %d, GBA frame +%d, lit pixels %.1f %%, difference to previous %s' % (g.nrun, g.gba_frame() - g0, 100 * lit(im), None if d is None else round(d, 1)))
            prev = im
            logos[name] = im
        logo3 = prev
        # the intro video: on the GBA it plays from here and ends in the title menu (4590 GBA frames after the press)
        m0, f1 = g.v('rom_miss_count'), g.nrun
        pics = []
        for k in (600, 1500, 2500):          # guest frames after the language press, inside the video on the GBA
            wait_guest(g, g.at_title, max(0, gf_press + k - gframes_or_est(g, f_press)) if gf_press is not None else k, a.intro_max_frames // 3)
            if g.at_title():
                break
            pics.append(g.snap('intro, guest frame +%d' % (gframes_or_est(g, f_press) - (gf_press or 0))))
        ds = drawn_pictures(g, pics, logo3)
        g.check(bool(ds) and max(ds) > 0.10, 'the intro video is drawn (pictures other than the third logo)',
                'shape difference to logo 3 of the pictures taken at guest frames +600, +1500, +2500 after the press: %s (0 = the same picture, also when faded); GBA original: the developer\'s logo and the film' % ds)
        left = max(0, a.intro_gframes - (gframes_or_est(g, f_press) - (gf_press or 0)))
        w, gw, fw = wait_guest(g, g.at_title, left, a.intro_max_frames)
        im = g.snap('after the logos, no input')
        gtot = gframes_or_est(g, f_press) - (gf_press or 0)
        fetch = None if m0 is None else g.v('rom_miss_count') - m0
        info['intro_idle'] = {'title': w, 'guest_frames': gtot, 'frames': g.nrun - f_press, 'rom_fetches': fetch, 'last_cluster': g.rom_cluster_last()}
        g.check(w, 'with no input the title menu follows the logos and the intro video',
                '%s %d guest frames after the language press (GBA original: %d), %d emulator frames = %.0f s console time; text %r, DISPCNT %s, '
                'picture shape difference to logo 3 %.2f, ROM cluster fetches meanwhile %s, last cluster %s' % (
                    'title menu' if w else 'no title menu', gtot, GBA_INTRO_TITLE_AFTER, g.nrun - f_press, (g.nrun - f_press) / g.fps, g.text()[:60],
                    None if g.dispcnt() is None else hex(g.dispcnt()), shape_diff(im, logo3), fetch,
                    None if g.rom_cluster_last() is None else '%07x' % g.rom_cluster_last()))
        if not w:
            w2, gw2, fw2 = press_guest(g, 'CROSS', g.at_title, 6 * GBA_INTRO_SKIP_AFTER)
            g.snap('after the logos, Cross')
            info['intro_cross'] = {'title': w2, 'guest_frames': gw2, 'frames': fw2}
            g.check(w2, 'Cross during the intro brings the title menu',
                    '%s %d guest frames (%d emulator frames) after Cross; GBA original: title menu %d frames after A; text %r, DISPCNT %s; pad words seen by the runtime: %s' % (
                        'title menu' if w2 else 'no title menu', gw2, fw2, GBA_INTRO_SKIP_AFTER, g.text()[:60], None if g.dispcnt() is None else hex(g.dispcnt()),
                        [l for f_, l in g.tty_when('PADRAW', since=g.nrun - fw2 - 200)][:4] or 'no PADRAW lines (the build prints them only with PADDBG)'))
        g.load_state_file(lang_state)
        g.log('-- branch 2: back at the language screen (state reloaded)')
    # ---- language -> logos -> title
    t0 = g.nrun
    r = g.pad_language_to_title()
    g.check(r.get('language_left') is not None, 'Cross closes the language screen', 'frames: %s' % r)
    g.note('Cross during the second logo (first press at frame %s); the first logo cannot be skipped' % r.get('logo2_press'))
    w = r.get('title')
    g.ready()
    im = g.snap('title')
    title0 = im                     # the title picture with the cursor on the start entry
    g.check(w is not None, 'title menu reached with the pad', 'frame %d (%d frames after the language press)' % (g.nrun, g.nrun - t0))
    if w is None:
        return g.finish('boot_to_title', extra=info)
    g.check(all(g.on(x) for x in TITLE), 'title menu lists its six entries', g.text()[:100])
    g.check(g.title_cursor() == 0, 'title cursor starts on the start entry', g.title_cursor())
    g.check(not is_black(im) and ncolors(im) > 16, 'title picture has a backdrop', '%d colours' % ncolors(im))
    if a.save_state:
        sp = os.path.join(a.state_dir, 'title.state')
        m = g.save_state_file(sp, 'title menu, cursor on the start entry, pad path, assist %s' % ('blanked' if off else 'as built'))
        g.check(m is not None, 'title state saved and verified by a reload', sp)
    title_text = g.text()
    # ---- entries
    for name in [x.strip() for x in a.entries.split(',') if x.strip()]:
        if name not in TITLE_ENTRIES:
            g.check(False, 'title entry %r is known' % name, 'names: %s' % ', '.join(TITLE_ENTRIES))
            continue
        g.log('-- %s entry' % name)
        title_ims = []
        if name == 'intro':
            title_ims += [title0, g.image()]            # the title picture with the cursor on the start entry and where it is now
            if g.title_goto(name):
                g.ready()
                title_ims.append(g.image())             # and with the cursor on the intro entry
        title_ims = [t for t in title_ims if t is not None]

        def kind(x):
            """What a picture shows: black, the title menu, one of the boot logos (logo 1..3), or other."""
            if x is None or is_black(x):
                return 'black'
            if title_ims and min(shape_diff(x, t) for t in title_ims) <= 0.15:
                return 'title'
            if logos:
                k = min(logos, key=lambda n: shape_diff(x, logos[n]))
                if shape_diff(x, logos[k]) <= 0.10:
                    return k
            return 'other'
        h = g.title_open(name)
        if h is None:
            g.check(False, '%s entry opens' % name, 'title still shown')
            continue
        f_open, gf_open = g.nrun, gframes_or_est(g, g.nrun)          # the title menu has gone
        quick = None
        if name == 'intro':
            # some builds go straight back to the title menu: measure that before anything else (rc4), and sample the
            # picture every 30 frames meanwhile
            seen, firsts, last = {}, {}, [g.nrun - 30]

            def back():
                if g.at_title():
                    return True
                if g.nrun - last[0] >= 30:
                    last[0] = g.nrun
                    x = g.image()
                    k = kind(x)
                    seen[k] = seen.get(k, 0) + 1
                    if k not in ('black', 'title') and k not in firsts:
                        firsts[k] = (g.nrun, gframes_or_est(g, f_open) - gf_open, x)
                return False
            okq, gq, fq = wait_guest(g, back, 300, 6000, step=2)
            if okq:
                quick = (gq, fq)
                for k, (fr, gfo, x) in sorted(firsts.items(), key=lambda kv: kv[1][0]):
                    g.snap('intro entry, first picture of kind %s (+%d guest frames)' % (k, gfo), im=x, frame=fr)
                sampled = 'pictures sampled every 30 frames meanwhile: %s' % (', '.join('%s %d' % kv for kv in sorted(seen.items())) or 'none')
        if name != 'intro' or quick is not None:
            g.wait_frames_drawn(3, 3000)
            g.ready()           # (not for an intro that runs: it draws no 2D frames, these waits would eat 2000 guest frames)
        im = g.snap('%s entry' % name)
        if name == 'intro' and quick is None and is_black(im):       # a fade from black: wait for the first lit picture
            wait_guest(g, lambda: not is_black(g.image()), 600, 6000, step=30)
            im = g.snap('%s entry, first lit picture' % name)
        txt = g.text()
        g.check(True, '%s entry opens' % name, '%d frames after Cross the title menu was gone%s; text now: %s' % (
            h, '' if quick is None else ', back %d guest frames (%d emulator frames) later' % quick, txt[:110] or '(none)'))
        g.check(not is_black(im), '%s entry: picture is not black' % name, 'mean luminance %.1f, %d colours' % (lum(im), ncolors(im)))
        b = None
        if name == 'controls':
            g.check(g.on(TITLE_CONTROLS, 'Accelerate', 'Done', 'Cancel'), 'controls page lists the actions', txt[:60])
            n = g.menu_goto('Cancel', ['Done', 'Cancel'])
            g.check(n is not None, 'controls page: cursor on Cancel', 'taps %s' % n)
            b = 'CROSS' if g.tap('CROSS', until=g.at_title, wait=4000) is not None else None
        elif name == 'language':
            g.check(g.at_language(), 'language entry shows the language screen', txt[:60])
            b = 'CROSS' if g.tap('CROSS', until=g.at_title, wait=8000) is not None else None
        elif name == 'delete':
            g.check(g.on('Cancel'), 'delete entry shows a slot list with Cancel', txt[:80])
            n = g.menu_goto('Cancel', ['UNUSED', 'Cancel'])
            b = 'CROSS' if g.tap('CROSS', until=g.at_title, wait=4000) is not None else None
        elif name == 'credits':
            for k in range(2):
                g.run(1500)
                im2 = g.snap('%s entry +%d' % (name, 1500 * (k + 1)))
                g.log('  f%d text: %s | DISPCNT %s | luminance %.1f' % (g.nrun, g.text()[:110] or '(none)', g.dispcnt(), lum(im2)))
            g.check(g.text() != title_text, '%s entry shows something else than the title' % name, g.text()[:80] or '(no text)')
            b = 'none needed' if g.at_title() else None
            for btn in ('CROSS', 'START', 'CIRCLE'):
                if b is not None:
                    break
                if g.tap(btn, until=g.at_title, wait=2500) is not None:
                    b = btn
        elif name == 'intro' and quick is not None:
            g.check(seen.get('other', 0) > 0 and quick[0] >= GBA_VIEW_INTRO_BACK_AFTER // 2, 'intro entry plays the film (pictures other than the logos)',
                    'the title menu was back %d guest frames (%d emulator frames) after it had gone (GBA original: a logo, then the film, '
                    '%d guest frames); %s' % (quick[0], quick[1], GBA_VIEW_INTRO_BACK_AFTER, sampled))
            g.check(True, 'intro entry returns to the title menu by itself', '%d guest frames after the title menu had gone (GBA original: %d)' % (
                quick[0], GBA_VIEW_INTRO_BACK_AFTER))
            info['view_intro'] = {'title_by_itself': True, 'guest_frames': quick[0], 'frames': quick[1], 'pictures': seen}
            b = 'none needed'
        elif name == 'intro':
            # GBA original: a logo and the intro film, back at the title by itself after 4620 GBA frames, A ends it
            f_v, gf_v = f_open, gf_open
            pics, offs = [], []
            for k in (600, 1500, 2500):
                wait_guest(g, g.at_title, max(0, gf_v + k - gframes_or_est(g, f_v)), a.intro_max_frames // 3)
                if g.at_title():
                    break
                offs.append(gframes_or_est(g, f_v) - gf_v)
                pics.append(g.snap('intro entry +%d guest frames' % offs[-1]))
            ref = logo3 if logo3 is not None else (pics[0] if pics else None)
            ds = drawn_pictures(g, pics, ref)
            g.check(bool(ds) and max(ds) > 0.10, 'intro entry plays the film (pictures other than the logos)',
                    'first picture: %s; shape difference of the pictures at guest frames %s after Cross to %s: %s (0 = the same picture, also when faded); '
                    'GBA original: a logo, then the film' % (kind(im), ', '.join('+%d' % o for o in offs) or '(none: title menu back)',
                                                              'logo 3' if logo3 is not None else 'the first of them', ds))
            left = max(0, a.intro_gframes - (gframes_or_est(g, f_v) - gf_v))
            w, gw, fw = wait_guest(g, g.at_title, left, a.intro_max_frames)
            gtot = gframes_or_est(g, f_v) - gf_v
            g.check(w, 'intro entry returns to the title menu by itself', '%s %d guest frames (%d emulator frames, %.0f s console time) after Cross; GBA original: %d' % (
                'title menu back after' if w else 'no title menu after', gtot, g.nrun - f_v, (g.nrun - f_v) / g.fps, GBA_VIEW_INTRO_BACK_AFTER))
            info['view_intro'] = {'title_by_itself': w, 'guest_frames': gtot, 'frames': g.nrun - f_v}
            if w:
                b = 'none needed'
            else:
                for btn in ('CROSS', 'CIRCLE', 'START', 'TRIANGLE', 'SELECT'):
                    ok2, gw2, fw2 = press_guest(g, btn, g.at_title, 6 * GBA_INTRO_SKIP_AFTER)
                    if ok2:
                        b = btn
                        break
                    g.log('  intro entry: %s did not bring the title back within %d guest frames (%d emulator frames); text now %r' % (btn, gw2, fw2, g.text()[:60]))
                info['view_intro']['button'] = b
        g.ready()
        g.snap('%s entry closed' % name)
        g.check(b is not None and g.at_title(), '%s entry returns to the title menu' % name, 'by %s, frame %d, cursor %d' % (b, g.nrun, g.title_cursor()))
        if not g.at_title():
            g.note('stuck after the %s entry: text %r; CPU at %s' % (name, g.text()[:100], g.cpu_where(4, 13)))
            break
    faults = g.tty_faults()
    g.check(not faults, 'no fault text on the TTY', faults[:3])
    return g.finish('boot_to_title', extra=info, sheet_cols=5)


if __name__ == '__main__':
    sys.exit(main())
