"""payback.py - the flows of Payback (GBA game, PS1 port) on top of ps1game.Game.

Everything here is driven by what the game drew (text read from the runtime's draw ring) and by guest RAM at GBA addresses,
so it does not depend on one build.  Symbols (--syms) add counters, the pad poll count (shorter presses) and the menu
assist table; without them presses use fixed lengths.

Screens (what the disc draws; the game's own words are not quoted here, see the marks below):
  language   a prompt line and the five language names (Deutsch, English, Espanol, Francais, Italiano)
  logos      no text, DISPCNT 0x0404: three logo pictures, the first of which cannot be skipped
  title      six entries: start, delete, intro, Credits, controls, language
  slots      a heading, five save slots (an unused one reads UNUSED, a used one the player's name), Cancel
  name       a heading, the letter grid, the default name, OK and Cancel
  game menu  a heading and five entries: single player, multiplayer, rampage, rename, end
  rampage    a heading, the high score, city and difficulty lines, the start line and Cancel
  level      level clock (0x02001e00) counts, 30 per second
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ps1game import *

# ---- the game's own text, as Marks (length and sha256 of the lower-cased words, see ps1game.Mark); the labels are ours.
# Single UI words (Credits, Cancel, Done, OK, Yes, No, UNUSED, PAUSED, Accelerate, the language names) stay plain.
START = Mark('start entry', 9, '1e09614a793002c18f2b60a6364a9415c251fbf76ca281f847f6900162a44c9a')       # title entry 0; also the start line of the rampage setup page
TITLE_DELETE = Mark('delete entry', 11, 'e1457c190f0e342368e8381f62ad751804f621c21662de5c3a187a4b2e102fe6')
TITLE_INTRO = Mark('intro entry', 10, '58d37dcf2630ed8c78f9a968e33031df1b23be9a7932344fa0b167d16a723f5c')
TITLE_CONTROLS = Mark('controls entry', 13, '5157a4db39427ee85ff4717a8ef293c0300b67ad91e318f990ff24b9357bb34a')    # the heading of the page it opens is the same words
TITLE_LANGUAGE = Mark('language entry', 12, '3a9a6503e7561e5d67e56bc616ba063ca05dcfb0180d512060e8bbbdf5dc8c0b')
TITLE = [START, TITLE_DELETE, TITLE_INTRO, 'Credits', TITLE_CONTROLS, TITLE_LANGUAGE]
# the names a session uses for the title entries (sessions/boot_to_title.py --entries)
TITLE_ENTRIES = {'start': START, 'delete': TITLE_DELETE, 'intro': TITLE_INTRO, 'credits': 'Credits', 'controls': TITLE_CONTROLS,
                 'language': TITLE_LANGUAGE}
GM_SINGLE = Mark('single player entry', 23, 'bd63cb89c41996d17dce632970bb4c7a7b797514a62ec3576d7e9cdcab326e0f')
GM_MULTI = Mark('multiplayer entry', 22, 'ce44e90f1239fea542120dbaa83222722d1d50d00715eace304ae0b4d3e2fda0')
GM_RAMPAGE = Mark('rampage entry', 21, 'ad721d72f51d50b93e730e8984adffb4df1b3ab1815c4e5fcdf7e3f02fe2d813')
GM_RENAME = Mark('rename entry', 11, '0f3336900ef50ab7d24bde92c499da645b1e2ec95abb6de43cc8764dd253ec5a')
GM_END = Mark('end entry', 8, 'e79c0988fbf5b0d5d4ac12e7538779ced36455d944706b8b3c9b41421aa9e51a')
GAME_MENU = [GM_SINGLE, GM_MULTI, GM_RAMPAGE, GM_RENAME, GM_END]
LANGUAGE_PROMPT = Mark('language prompt', 20, 'b03ca4e95109db0b55fc36c7167981f20143bb90a7e3a232664a94625abb7357')
SLOTS_HEADING = Mark('slot list heading', 11, '737a3b9fcffb3a0a00a0b6c66b97f6eaf7b37f177f8ef2bcf106fade6ab6c95a')
NAME_HEADING = Mark('name entry heading', 10, 'bd046aa8e05fce3affba12d104ef46d22f94d41450ac245d8c703f36247b7fa2')
GAME_MENU_HEADING = Mark('game menu heading', 9, 'a9ccf0a24ae7af2b4d7ea1d857e536c7de244c9aa732dfa8bd3ec7fe4ed56c28')
RAMPAGE_HEADING = Mark('rampage setup heading', 13, '2be303bb3797c013edd20e216e989defef99e219e1f5df2b0a67cf734277fa3b')
PAUSE_RESUME = Mark('resume entry', 14, 'b0ea6243d32352d6e009ea497f814377263b1a76a2b429312d5199eb802d1a0b')
PAUSE_QUIT = Mark('quit entry', 13, '9e74b173a0835c0b80312c513216ed159b4a411cff91402f72714dd5b9bb399b')
PAUSE_MENU = [PAUSE_RESUME, PAUSE_QUIT]        # under the word PAUSED
QUIT_QUESTION = Mark('quit question', 12, 'cc76bf5045e486bdd53869101b9144b3ad46868dbd79bd5d2566199424116f17')
DEFAULT_NAME = Mark('default player name', 6, '9611d66d2d183aaa44936048ca4a32a5f9b043a615e663a39248653e3ff6ec2b')   # plain ASCII
LANGUAGES = ('Deutsch', 'English', 'Espanol', 'Francais', 'Italiano')

# What the GBA original does (the cartridge in mGBA, measured with tools/gba_ref_intro.py), in GBA frames:
# A on the language screen, then no input: three logos, the intro video (the developer's logo, then the film), title menu
# 4590 frames after the press; A or B during the video: title menu 100 frames later (Start does not skip it); title menu >
# intro entry: a logo and the same film, back at the title menu after 4620 frames, or 100 frames after A.
GBA_INTRO_TITLE_AFTER = 4590
GBA_INTRO_SKIP_AFTER = 100
GBA_VIEW_INTRO_BACK_AFTER = 4620
MAPS = 11
BODY_FONT = 0x0809ae94      # glyph table of the red menu font (ROM address); the selected line uses 0x0809b694


class Payback(Game):
    # ------------------------------------------------------------------ where are we
    def at_language(self):
        return self.on(LANGUAGE_PROMPT)

    def at_title(self):
        return self.on(START, TITLE_LANGUAGE)

    def at_slots(self):
        return self.on(SLOTS_HEADING)

    def at_name(self):
        return self.on(NAME_HEADING)

    def at_game_menu(self):
        return self.on(GAME_MENU_HEADING)

    def at_rampage(self):
        return self.on(RAMPAGE_HEADING)

    def where(self):
        for n in ('language', 'title', 'slots', 'name', 'game_menu', 'rampage'):
            if getattr(self, 'at_' + n)():
                return n
        if self.in_level():
            return 'level'
        return 'other'

    def ready(self, max_frames=9000):
        """A menu takes no input while it fades in, and the picture lags the drawn text: wait for two presented frames, the
        end of the fade and two identical drawn frames."""
        self.wait_presented(2)
        a = self.wait_fade(max_frames)
        b = self.settle(2, 4000)
        return None if a is None or b is None else a + b

    # ------------------------------------------------------------------ menus: the selected line pulses in a second font
    def selected(self, items=None, frames=4):
        """The menu line drawn in the highlight font (anything but the red body font) in one of the last `frames` complete
        2D frames, newest first: the selected line pulses between the two fonts in the big menus and is steady in the
        pause menu.  items: only these lines count (words or Marks, substring match, the item is returned); None: any line
        below the heading."""
        for f, ent in reversed(self._rframes[-frames:]):
            for l in self.text_lines(ent):
                if l['font'] == BODY_FONT or l['y'] <= 20:
                    continue
                if items is None:
                    return l['text']
                for it in items:
                    if contains(l['text'], it):
                        return it
        return None

    def wait_frames_drawn(self, n, max_frames=6000, buttons=()):
        """Run until n more complete 2D frames were drawn.  Returns emulator frames waited or None."""
        t = self.frames_drawn + n
        return self.wait_until(lambda: self.frames_drawn >= t, max_frames, buttons, step=2)

    def wait_selected(self, items=None, max_frames=6000):
        """Wait for fresh frames (a full pulse period) and return the selected line."""
        self._rframes = []          # forget the frames drawn before now
        n = 0
        while n < max_frames:
            self.run(2)
            n += 2
            if len(self._rframes) >= 1:
                s = self.selected(items, frames=len(self._rframes))
                if s is not None:
                    return s
            if len(self._rframes) >= 6:
                break
        return None

    def menu_goto(self, target, items, max_steps=12):
        """Move the cursor of a vertical menu to `target` (one of items) with Up/Down taps, checking the highlight after
        every tap.  Returns the number of taps, or None when it did not get there."""
        for step in range(max_steps):
            sel = self.wait_selected(items)
            if sel is None:
                self.log('  menu_goto: no highlighted line among %s (text: %s)' % (items, self.text()[:120]))
                return None
            if sel == target:
                return step
            b = 'DOWN' if items.index(target) > items.index(sel) else 'UP'
            self.tap(b, hold_polls=1, release_polls=1)
        return None

    # ------------------------------------------------------------------ boot
    def boot_to_language(self, max_frames=8000):
        """Cold boot until the language screen is drawn.  Returns the emulator frame or None."""
        if self.wait_until(lambda: self.at_language() and self.on('Deutsch', 'Italiano'), max_frames, step=4, what='language screen') is None:
            return None
        self.settle(2, 3000)
        return self.nrun

    def pad_language_to_title(self):
        """Real pad only: Cross on the language screen (keeps the preselected language), then Cross during the second logo
        (the first one cannot be skipped) which goes straight to the title menu.  Returns a dict of frame numbers, with
        'title' None on failure."""
        r = {'language_press': self.nrun}
        if self.tap('CROSS', until=lambda: not self.at_language(), wait=4000, what='language screen to close') is None:
            r['title'] = None
            return r
        r['language_left'] = self.nrun
        r.update(self.pad_logos_to_title())
        return r

    def pad_logos_to_title(self):
        """From the (coming) logo screens to the title menu: Cross for 6 GBA frames while the second logo is up."""
        r = {'title': None}
        if self.dispcnt() is not None:
            if self.wait_until(lambda: self.dispcnt() == 0x404, 4000, step=2, what='logo screen (DISPCNT 0x0404)') is None:
                return r
            r['logos'] = self.nrun
            g0 = self.gba_frame()
            r['logo2_press'] = None
            for at in (224, 262, 300):      # the second logo is up from +164 to +328; the assist of the builds presses at +224 for 6 frames
                self.wait_until(lambda: self.gba_frame() >= g0 + at, 6000, step=1)
                if r['logo2_press'] is None:
                    r['logo2_press'] = self.nrun
                h0 = self.gba_frame()
                self.wait_until(lambda: self.gba_frame() >= h0 + 6, 600, buttons=['CROSS'], step=1)
                if self.wait_until(lambda: self.dispcnt() != 0x404 or self.text() != '', 120, step=1) is not None:
                    break
        else:
            self.run(1300)
            r['logo2_press'] = self.nrun
            self.run(120, ['CROSS'])
        ok = self.wait_until(self.at_title, 8000, step=2, what='title menu')
        r['title'] = self.nrun if ok is not None else None
        return r

    def assist_wait(self, cond, max_frames, what):
        """No input: let the build's menu assist work until cond().  Logs every screen change.  Returns frames or None."""
        last = None
        n = 0
        while n < max_frames:
            if cond():
                return n
            self.run(10)
            n += 10
            w = self.where()
            if w != last:
                self.log('  f%d gba %s: screen %s  (assist keys down: %s)  text: %s' % (self.nrun, self.gba_frame(), w, self.assist_pressed(), self.text()[:90]))
                last = w
        self.log('  timeout after %d frames waiting for %s' % (max_frames, what))
        return None

    # ------------------------------------------------------------------ title menu
    def title_goto(self, item):
        """Move the title cursor (guest 0x03007e68) to TITLE[item]: item is an index, an element of TITLE or a name of
        TITLE_ENTRIES."""
        i = item if isinstance(item, int) else TITLE.index(TITLE_ENTRIES.get(item, item))
        self.ready()
        for _ in range(12):
            c = self.title_cursor()
            if c == i:
                return True
            if not 0 <= c < len(TITLE):
                return False
            self.tap('DOWN' if c < i else 'UP', until=lambda: self.title_cursor() != c, hold_polls=1, wait=3000, what='title cursor to move')
        return self.title_cursor() == i

    def title_open(self, item, wait=4000):
        """Cursor to the item, Cross, wait until the title menu is gone.  Returns frames or None."""
        if not self.title_goto(item):
            self.log('  title cursor did not reach %s (cursor %d)' % (item, self.title_cursor()))
            return None
        return self.tap('CROSS', until=lambda: not self.at_title(), wait=wait, what='%s to open' % (item,))

    # ------------------------------------------------------------------ title -> level
    def pad_title_to_level(self, max_load=12000):
        """Real pad from the title menu to a running rampage level on map 0:
        Cross (start entry) > Cross (first slot) > [Cross (name OK) on an unused slot] > Down, Down (rampage entry of the
        game menu) > Cross > Cross (start line of the rampage setup).  Returns a dict of frame numbers; r['level'] is None
        on failure."""
        r = {'title': self.nrun, 'level': None}
        if not self.title_goto(0):
            return r
        if self.tap('CROSS', until=self.at_slots, what='slot list') is None:
            return r
        r['slots'] = self.nrun
        self.ready()
        r['slot_lines'] = list(self.screen())
        if self.tap('CROSS', until=lambda: self.at_name() or self.at_game_menu(), what='name entry or game menu') is None:
            return r
        if self.at_name():
            r['name'] = self.nrun
            self.ready()
            if self.tap('CROSS', until=self.at_game_menu, what='game menu') is None:
                return r
        r['game_menu'] = self.nrun
        self.ready()
        if self.menu_goto(GM_RAMPAGE, GAME_MENU) is None:
            return r
        if self.tap('CROSS', until=self.at_rampage, what='rampage setup') is None:
            return r
        r['rampage'] = self.nrun
        self.ready()
        r['rampage_lines'] = list(self.screen())
        if self.menu_goto(START, [START, 'Cancel']) is None:
            return r
        r['st3_before'] = self.v('st3_render')
        if self.tap('CROSS', until=lambda: self.level_clock() > 0, wait=max_load, what='level clock') is None:
            return r
        r['level'] = self.tap_true_at          # first frame the level clock was seen counting (the click ends later)
        return r

    # ------------------------------------------------------------------ level helpers
    def wait_clock(self, ticks, max_frames, buttons=()):
        """Run until the level clock advanced by `ticks`.  Returns emulator frames or None."""
        c = self.level_clock() + ticks
        return self.wait_until(lambda: self.level_clock() >= c, max_frames, buttons, step=4)

    def level_report(self):
        p = self.player()
        return {'frame': self.nrun, 'clock': self.level_clock(), 'map': self.map_id(), 'grid': self.grid_id(), 'lives': self.lives(),
                'level_end': self.level_end(), 'respawn': self.respawn(), 'controlled': self.controlled(), 'nentity': self.nentity(),
                'player': None if p is None else {k: p[k] for k in ('x', 'y', 'z', 'heading', 'kind', 'k', 'health', 'state')}}


def open_game(args, name, **kw):
    """Game object of a session from the standard arguments."""
    if getattr(args, 'core_opts', None):
        kw['opts'] = dict(kw.get('opts') or {}, **args.core_opts)
    try:
        g = Payback(args.disc, args.out, core=args.core, card=kw.pop('card', args.card), syms=args.syms, **kw)
    except RigSetupError as ex:
        sys.exit('%s: %s' % (name, ex))
    g.session = name
    print('== %s  disc %s  core %s  card %s  syms %s%s' % (name, args.disc, args.core, g.meta['card'], args.syms, ('  options %s' % args.core_opts) if getattr(args, 'core_opts', None) else ''), flush=True)
    tty = ('on' if g.meta.get('tty') else 'off (unknown core binary: no MAPCHANGE / CONFLICT lines)') if g.core_name == 'pcsx_rearmed' else \
        'from the RAM ring of openboot (only when openboot is the firmware)'
    print('   PSX.EXE sha1 %s, guest TTY %s%s' % ((g.meta.get('exe_sha1') or '?')[:12], tty,
                                              ', %d files of an earlier run removed from the output directory' % g.cleaned if g.cleaned else ''), flush=True)
    if args.syms and g.meta.get('syms_match_disc') is False:
        print('WARNING: the symbol file does not match the PSX.EXE on this disc: symbols ignored', flush=True)
        g.sym, g.symsize = {}, {}
    if not args.syms:
        print('NOTE no --syms: runtime counters, pad poll counts, safe save states and the menu assist switch are not available', flush=True)
    return g


# ---------------------------------------------------------------------------------------------- level: picture and steering
def view_state(im):
    """What a picture shows, judged from the whole frame (calibrated on this game's screens, see RIG.md):
    'city'  - the 3D view of the level: nearly every pixel lit and a good part of them coloured;
    'black' - nothing; 'white' - more than half nearly white (the fade at a level start); 'dark' - text or a logo on
    black (pause menu, logos); 'menu' - lit but grey (the menus on the bridge photograph, the white-faded pages).
    A frame wider than 320 pixels (Beetle: 350x240, the game's 320x224 picture inside black borders of 15 columns and 8 lines
    on each side) is judged on its centred 320x224 area, as SwanStation's 320x224 frames are: the borders alone are 13 % of
    the frame and pushed the picture with the start-of-level message under the 'lit' threshold."""
    if im is None:
        return 'black'
    if im.size[0] > 320:
        x0, y0 = (im.size[0] - 320) // 2, max(0, (im.size[1] - 224) // 2)
        im = im.crop((x0, y0, x0 + 320, y0 + min(im.size[1], 224)))
    l, w, c = measures(im)
    if l < 0.005:
        return 'black'
    if w > 0.5:
        return 'white'
    if l < 0.45:
        return 'dark'
    # Some real city scenes are almost monochrome (pale streets or shaded
    # vehicles) even though the 3D view covers the frame. Preserve the
    # saturated-city rule and add a strictly high-coverage, low-chroma path;
    # a truly grey menu with c=0 and white fade still fail this gate.
    return 'city' if (l >= 0.8 and c >= 0.105) or (l >= 0.9 and c >= 0.02 and w < 0.35) else 'menu'


def heading_to(dx, dy):
    """Heading (5760 a turn) that walks along (dx, dy): heading 0 moves +y, Left raises the heading and turns towards +x."""
    import math
    return int(round(math.atan2(dx, dy) / (2 * math.pi) * 5760)) % 5760


def wrap(d):
    d %= 5760
    return d - 5760 if d > 2880 else d


def start_level(g, a):
    """Bring a session into a running level: --from-state, else cold boot and the pad path (assist path when the pad path fails
    or cannot be used).  Returns True when the level clock runs."""
    fs = getattr(a, 'from_state', None)
    if fs:
        fits, why = g.state_fits(fs)
        if fits:
            g.load_state_file(fs)
            g.note('started from state %s (frame counter restarts at 1)' % fs)
            return g.level_clock() > 0
        g.note('state %s not used: %s; cold boot instead' % (fs, why))
    if g.boot_to_language() is None:
        return False
    off = g.assist_off()
    g.note('menu assist: %s' % ('plan blanked in RAM by the rig (%s)' % ', '.join(off) if off else 'left as built'))
    r = g.pad_language_to_title()
    if r.get('title') is not None:
        r2 = g.pad_title_to_level()
        if r2.get('level') is not None:
            ok, det = level_view(g, r2.get('st3_before'))
            g.note('level reached with the pad at frame %d (level clock running); its picture: %s' % (r2['level'], det))
            return True
    g.note('pad path did not reach the level (at: %s); waiting for the build\'s assist' % (g.text()[:80] or g.where()))
    if g.assist_wait(lambda: g.level_clock() > 0, 90000, 'level clock') is None:
        return False
    ok, det = level_view(g)
    g.note('level reached by the build\'s assist; its picture: %s' % det)
    return True


def level_view(g, r0=None, budget=14000):
    """After a level start: wait until the level's own pictures are on screen (two frames presented since, and with symbols two
    3D frames rendered since r0 = st3_render before the start), then until the 3D city is seen.  Returns (ok, detail)."""
    f0 = g.nrun
    g.wait_presented(2, budget)
    if r0 is not None and 'st3_render' in g.sym:
        g.wait_until(lambda: g.v('st3_render') >= r0 + 2, budget, step=4)
    g.wait_until(lambda: view_state(g.image()) == 'city', 6000, step=60)
    vs = view_state(g.image())
    r1 = g.v('st3_render')
    ok = vs == 'city' and g.level_clock() > 0 and not g.at_rampage() and (r0 is None or r1 is None or r1 >= r0 + 2)
    return ok, 'view %s, clock %d, 3D frames rendered since the start %s, sf3_ok %s, %d frames after the start' % (
        vs, g.level_clock(), None if (r0 is None or r1 is None) else r1 - r0, g.v('sf3_ok'), g.nrun - f0)


class Scan:
    """Runs the game while sampling the picture: the longest stretch without the 3D city on screen, and without any picture.
    The first picture of the longest stretch without the city is kept (bad_im, bad_from) as evidence."""
    def __init__(self, g, step=120):
        self.g, self.step = g, step
        self.bad = self.bad_max = 0       # frames in a row with view_state != 'city'
        self.dark = self.dark_max = 0     # frames in a row with a completely black picture
        self.bad_at = self.dark_at = None
        self.bad_im = self.bad_from = None
        self._cur = None
        self.samples = 0
        self.states = {}

    def run(self, frames, buttons=(), until=None):
        g, n = self.g, 0
        while n < frames:
            if until is not None and until():
                break
            k = min(self.step, frames - n)
            g.run(k, buttons)
            n += k
            im = g.image()
            vs = view_state(im)
            self.samples += 1
            self.states[vs] = self.states.get(vs, 0) + 1
            if vs != 'city':
                if self.bad == 0:
                    self._cur = (im, g.nrun, vs)
                self.bad += k
                if self.bad > self.bad_max:
                    self.bad_max, self.bad_at = self.bad, g.nrun
                    self.bad_im, self.bad_from = self._cur[0], self._cur[1]
            else:
                self.bad = 0
            if is_black(im):
                self.dark += k
                if self.dark > self.dark_max:
                    self.dark_max, self.dark_at = self.dark, g.nrun
            else:
                self.dark = 0
        return n

    def evidence(self, tag):
        """Put the first picture of the longest stretch without the city on the contact sheet."""
        if self.bad_im is not None:
            self.g.snap(tag, im=self.bad_im, frame=self.bad_from)
