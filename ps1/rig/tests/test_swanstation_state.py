"""ROM-free tests: the rig recognises SwanStation save states that the core cannot load again (ps1game.state_unloadable).

SwanStation serialises its timing events as the marker 'Events', a u32, the event count and per event its name and four s32
(downcount, ticks since the last run, period, interval).  Every state that retro_unserialize refused had events with a negative time since their last run
(rc8 at the level start, every setting), although most such states load; save_state_file steps on instead of writing one, and
load_state_file tries the core first and explains a refusal with it.
The states here are synthetic byte strings of that layout, no core is run."""
from __future__ import annotations
import pathlib
import struct
import sys
import types
import unittest

RIG = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RIG))
import ps1game  # noqa: E402

NAMES = ('CDROM Command Second Response Event', 'GPU CRTC Tick', 'SPU Sample', 'Timer SysClk Interrupt')


def table(since, word=0x8f16eaa9):
    out = struct.pack('<I', 6) + b'Events' + struct.pack('<Ii', word, len(NAMES))
    for name, t in zip(NAMES, since):
        out += struct.pack('<I', len(name)) + name.encode() + struct.pack('<4i', 1000, t, 1, 1)
    return out + struct.pack('<I', 9) + b'Overclock'


def state(since, ram=b''):
    return b'DUCC' + b'\0' * 64 + ram + b'MDEC' + b'\0' * 32 + table(since) + b'\0' * 64


class SwanStationStateTests(unittest.TestCase):
    def test_good_state(self):
        s = state((1217735, 25, 0, 27))
        ev = ps1game.swanstation_events(s)
        self.assertEqual([e[0] for e in ev], list(NAMES))
        self.assertEqual(ps1game.state_unloadable('swanstation', s), '')

    def test_negative_time_since_last_run(self):
        s = state((13, -1404301, -1404307, -1404301))
        why = ps1game.state_unloadable('swanstation', s)
        self.assertIn('GPU CRTC Tick -1404301', why)
        self.assertIn('SPU Sample -1404307', why)
        self.assertNotIn('CDROM', why)

    def test_a_downcount_that_spells_s_does_not_move_the_table(self):
        # a downcount whose low byte is 0x73 ('s') after '... Response Event' reads as 'Events' to a plain search
        s = state((13, -5, 0, 0)).replace(struct.pack('<4i', 1000, 13, 1, 1), struct.pack('<4i', 0x1e8473, 13, 1, 1), 1)
        self.assertIn(b'Events\x84\x1e', s)
        self.assertEqual([e[0] for e in ps1game.swanstation_events(s)], list(NAMES))
        self.assertIn('GPU CRTC Tick -5', ps1game.state_unloadable('swanstation', s))

    def test_marker_in_guest_ram_is_skipped(self):
        junk = struct.pack('<I', 6) + b'Events' + b'\xff' * 40       # the word in RAM, followed by no valid table
        s = state((0, 0, 0, 0), ram=junk)
        self.assertEqual(len(ps1game.swanstation_events(s)), 4)
        self.assertEqual(ps1game.state_unloadable('swanstation', s), '')

    def test_other_cores_and_unknown_layouts(self):
        self.assertEqual(ps1game.state_unloadable('beetle', state((0, -1, -1, -1))), '')
        self.assertIsNone(ps1game.swanstation_events(b'STv4 PCSX' + b'\0' * 100))
        self.assertEqual(ps1game.state_unloadable('swanstation', b'\0' * 100), '')

    def test_save_state_file_steps_past_an_unloadable_frame(self):
        frames = []
        states = [state((0, -9, -9, -9)), state((0, -9, -9, -9)), state((0, 1, 1, 1))]
        g = types.SimpleNamespace(core_name='swanstation', card_mode='none', nrun=0, opts={}, meta={}, logs=[])
        g.release = lambda: None
        g.in_present = lambda: False
        g.save_state = lambda: states[min(len(frames), 2)]
        def run(n=1, buttons=()):
            frames.append(n); g.nrun += n
        g.run = run
        g.log = g.logs.append
        import tempfile, os
        with tempfile.TemporaryDirectory(prefix='ps1rig-sstate-') as tmp:
            meta = ps1game.Game.save_state_file(g, os.path.join(tmp, 'x.state'), verify=0)
            self.assertIsNotNone(meta)
            self.assertEqual(frames, [1, 1])
            self.assertEqual(open(os.path.join(tmp, 'x.state'), 'rb').read(), states[2])
        self.assertTrue(any('a state of frame 0 has timing events behind' in m for m in g.logs))


    def _loader(self, st, ok):
        import tempfile, os
        calls = []
        g = types.SimpleNamespace(core_name='swanstation', card_mode='none', meta={}, logs=[])
        g._leave_present = lambda: calls.append('leave')
        def load_state(s):
            calls.append('load')
            if not ok:
                raise RuntimeError('unserialize failed')
        g.load_state = load_state
        g._ring_reset = lambda: calls.append('ring')
        g.run = lambda n=1, buttons=(): calls.append('run')
        tmp = tempfile.mkdtemp(prefix='ps1rig-sload-')
        p = os.path.join(tmp, 'x.state')
        open(p, 'wb').write(st)
        return g, p, calls

    def test_load_state_file_tries_the_core_first(self):
        # a state with timing events behind that the core accepts is loaded, not refused
        g, p, calls = self._loader(state((0, -9, -9, -9)), ok=True)
        ps1game.Game.load_state_file(g, p)
        self.assertEqual(calls, ['leave', 'load', 'ring', 'run'])

    def test_load_state_file_explains_a_refusal(self):
        g, p, calls = self._loader(state((0, -9, -9, -9)), ok=False)
        with self.assertRaisesRegex(RuntimeError, 'timing events behind .*GPU CRTC Tick -9'):
            ps1game.Game.load_state_file(g, p)
        g, p, calls = self._loader(state((0, 1, 1, 1)), ok=False)
        with self.assertRaisesRegex(RuntimeError, '^unserialize failed$'):
            ps1game.Game.load_state_file(g, p)


if __name__ == '__main__':
    unittest.main()
