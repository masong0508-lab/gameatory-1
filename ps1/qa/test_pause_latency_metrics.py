"""ROM-free numeric regressions for PS1 pause-resume timing detection."""
import sys
from pathlib import Path
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parent))
from pause_latency_metrics import ResumeEvidence


class ResumeEvidenceTests(unittest.TestCase):
    def test_nominal_clock_then_flip_and_render(self):
        t=ResumeEvidence(100,b'pause',500,20,50)
        t.sample(101,500,b'pause',20,50,False)
        t.sample(102,501,b'pause',20,50,False)
        t.sample(104,502,b'city',21,51,True)
        v=t.summary()
        self.assertEqual(v['clock_restarted'],102)
        self.assertEqual(v['first_playable_picture'],104)
        self.assertEqual(v['visible_linger_after_clock_restart_frames'],2)

    def test_menu_animation_before_clock_does_not_count_as_resume(self):
        t=ResumeEvidence(100,b'pause',500,20,50)
        t.sample(101,500,b'menu_animation',21,50,True)
        self.assertIsNone(t.summary()['first_playable_picture'])
        t.sample(103,501,b'city',22,51,True)
        self.assertEqual(t.summary()['first_playable_picture'],103)

    def test_counter_change_without_picture_is_not_a_returned_view(self):
        t=ResumeEvidence(100,b'pause',500,20,50)
        t.sample(101,501,b'pause',21,51,True)
        self.assertIsNone(t.summary()['first_playable_picture'])
        t.sample(102,501,b'changed',21,51,True)
        self.assertEqual(t.summary()['first_playable_picture'],102)

    def test_static_clock_does_not_report_resumed_view(self):
        t=ResumeEvidence(100,b'pause',500,20,50)
        t.sample(200,500,b'new_city',21,51,True)
        self.assertIsNone(t.summary()['clock_restarted'])
        self.assertIsNone(t.summary()['first_playable_picture'])

    def test_renderer_stale_does_not_claim_new_play(self):
        t=ResumeEvidence(100,b'pause',500,20,50)
        t.sample(110,501,b'city',21,50,True)
        self.assertIsNone(t.summary()['first_playable_picture'])
        t.sample(112,503,b'city2',22,51,True)
        self.assertEqual(t.summary()['first_playable_picture'],112)

    def test_no_evidence_yields_none_and_invalid_frames_rejected(self):
        t=ResumeEvidence(100,b'pause',500,20,50)
        self.assertIsNone(t.summary()['visible_linger_after_clock_restart_frames'])
        with self.assertRaises(ValueError):
            t.sample(99,501,b'new',22,51,True)


if __name__ == '__main__': unittest.main()