"""ROM-free synthetic regressions for PS1 pause-resume picture timing."""
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
        self.assertEqual(v['first_new_picture'],104)
        self.assertEqual(v['first_playable_picture'],104)
        self.assertEqual(v['visible_linger_after_resume_press_frames'],4)
        self.assertEqual(v['visible_linger_after_clock_restart_frames'],2)

    def test_menu_animation_before_clock_does_not_count_as_city_return(self):
        t=ResumeEvidence(100,b'pause',500,20,50)
        t.sample(101,500,b'menu_animation',21,50,False)
        self.assertEqual(t.summary()['first_any_picture_change'],101)
        self.assertIsNone(t.summary()['first_new_picture'])
        t.sample(103,501,b'city',22,51,True)
        self.assertEqual(t.summary()['first_new_picture'],103)
        self.assertEqual(t.summary()['first_playable_picture'],103)

    def test_counters_advance_on_unchanged_picture_without_early_credit(self):
        t=ResumeEvidence(100,b'pause',500,20,50)
        t.sample(101,501,b'pause',21,51,True)
        self.assertIsNone(t.summary()['first_gpu_flip'])
        self.assertIsNone(t.summary()['first_3d_render'])
        t.sample(185,505,b'fresh_city',21,51,True)
        v=t.summary()
        self.assertEqual(v['first_new_picture'],185)
        self.assertEqual(v['first_gpu_flip'],185)
        self.assertEqual(v['first_3d_render'],185)
        self.assertEqual(v['visible_linger_after_resume_press_frames'],85)

    def test_static_clock_does_not_report_playable_resumed_view(self):
        t=ResumeEvidence(100,b'pause',500,20,50)
        t.sample(200,500,b'new_city',21,51,True)
        self.assertIsNone(t.summary()['clock_restarted'])
        self.assertIsNone(t.summary()['first_playable_picture'])
        self.assertEqual(t.summary()['visible_linger_after_resume_press_frames'],100)

    def test_renderer_stale_does_not_claim_new_play(self):
        t=ResumeEvidence(100,b'pause',500,20,50)
        t.sample(110,501,b'city',21,50,True)
        self.assertIsNone(t.summary()['first_playable_picture'])
        t.sample(112,503,b'city2',22,51,True)
        self.assertEqual(t.summary()['first_3d_render'],112)
        self.assertEqual(t.summary()['first_playable_picture'],112)

    def test_press_linger_differs_from_clock_restart_lag(self):
        t=ResumeEvidence(100,b'pause',500,20,50)
        t.sample(102,500,b'city1',21,51,True)
        t.sample(110,501,b'city2',22,52,True)
        v=t.summary()
        self.assertEqual(v['first_new_picture_after_press_frames'],2)
        self.assertEqual(v['visible_linger_after_resume_press_frames'],2)
        self.assertEqual(v['first_playable_picture_after_press_frames'],10)
        self.assertEqual(v['visible_linger_after_clock_restart_frames'],0)

    def test_post_return_short_stalls_are_observed_and_reported(self):
        t=ResumeEvidence(100,b'pause',500,20,50)
        t.sample(102,501,b'city',21,51,True)
        for frame in (103,104,105):
            t.sample(frame,501,b'city',21,51,True)
        t.sample(106,502,b'city2',22,52,True)
        for frame in (107,108):
            t.sample(frame,502,b'city2',22,52,True)
        v=t.summary()
        self.assertEqual(v['post_new_frame_observed_frames'],6)
        self.assertEqual(v['post_new_frame_picture_changes'],1)
        self.assertEqual(v['post_new_frame_max_static_frames'],3)
        self.assertEqual([x['static_frames'] for x in v['post_new_frame_still_intervals']], [3,2])
        self.assertEqual(v['post_new_frame_still_intervals'][0]['start_after_press'],3)

    def test_counter_with_no_changed_picture_never_counts(self):
        t=ResumeEvidence(100,b'pause',500,20,50)
        for frame in range(101,130):
            t.sample(frame,500+frame-100,b'pause',20+frame-100,50+frame-100,True)
        v=t.summary()
        self.assertIsNone(v['first_new_picture'])
        self.assertIsNone(v['first_gpu_flip'])
        self.assertIsNone(v['first_3d_render'])
        self.assertIsNone(v['visible_linger_after_resume_press_frames'])

    def test_no_evidence_and_invalid_frame_rejected(self):
        t=ResumeEvidence(100,b'pause',500,20,50)
        self.assertIsNone(t.summary()['visible_linger_after_resume_press_frames'])
        self.assertIsNone(t.summary()['visible_linger_after_clock_restart_frames'])
        with self.assertRaises(ValueError):
            t.sample(99,501,b'new',22,51,True)


if __name__ == '__main__':
    unittest.main()
