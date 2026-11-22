"""ROM-free page-profiling tests, including adversarial legacy pickle input."""
import collections
import json
import pickle
import unittest
from working_set import page_indices, validate, capture, summarize
from from_reference import load_counts
from sim_capture import controlled_mode, PageRecorder, EW, IW, DESC0


class PageTests(unittest.TestCase):
    def test_data_rom_address_mirrors_and_page_boundaries(self):
        self.assertEqual(page_indices(0x08000000, 4), (0,))
        self.assertEqual(page_indices(0x0a000ffe, 4), (0,1))
        with self.assertRaises(ValueError): page_indices(0x0c800001, 1)
        self.assertEqual(page_indices(0x087ffffc, 4), (2047,))
        for addr in [0x02000000, 0x0d000000, 0x08800000, 0x087fffff]:
            with self.assertRaises(ValueError): page_indices(addr, 4)

    def test_invalid_samples_rejected(self):
        for name in ('map','mode','phase'):
            obj = capture(0, 'foot', 'play', {1:2}, source='synthetic')
            obj[name] = {'map':11,'mode':'not-a-valid vehicle','phase':'not_real'}[name]
            with self.assertRaises(ValueError): validate(obj)
        with self.assertRaises(ValueError): validate(capture(0,'foot','play',{2048:1},source='synthetic'))
        with self.assertRaises(ValueError): validate(capture(0,'foot','play',{1:0},source='synthetic'))

    def test_each_scene_equal_weight_versus_raw_hit_dominance(self):
        samples=[capture(0,'foot','play',{2:1000000},source='synthetic'),
                 capture(1,'foot','play',{5:100},source='synthetic')]
        rep=summarize(samples, budget4k=2)
        self.assertEqual(rep['candidate_4k_pages'],[2,5])
        self.assertEqual(rep['missing_map_ids'], list(range(2,11)))
        self.assertFalse(rep['complete_11_map_coverage'])

    def test_11_map_coverage_flag_requires_actual_captures(self):
        samples=[capture(m,'foot','play',{m:100},source='synthetic') for m in range(11)]
        rep=summarize(samples, budget4k=10)
        self.assertTrue(rep['complete_11_map_coverage'])
        self.assertEqual(len(rep['observed_map_ids']),11)
        self.assertEqual(rep['observed_vehicle_descriptor_indices'],[])

    def test_required_per_map_mode_matrix_cannot_be_faked_by_any_map_run(self):
        samples=[capture(mi,'unclassified','combined',{mi:5},source='synthetic') for mi in range(11)]
        rep=summarize(samples,budget4k=11,required_modes=['foot','vehicle_007'])
        self.assertTrue(rep['complete_11_map_coverage'])
        self.assertFalse(rep['complete_required_map_mode_matrix'])
        self.assertEqual(len(rep['missing_required_map_mode_pairs']),22)
        samples=[capture(mi,mode,'play',{mi:5},source='synthetic')
                 for mi in range(11) for mode in ('foot','vehicle_007')]
        rep=summarize(samples,budget4k=11,required_modes=['foot','vehicle_007'])
        self.assertTrue(rep['complete_required_map_mode_matrix'])
        self.assertEqual(rep['missing_required_map_mode_pairs'],[])

    def test_16k_aggregation(self):
        cap=capture(0,'vehicle_007','play',{0:10,1:20,4:5},source='synthetic')
        rep=summarize([cap],budget4k=2)
        self.assertEqual(rep['candidate_16k_groups_ranked'][:2],[0,1])
        self.assertEqual(rep['observed_vehicle_descriptor_indices'],['vehicle_007'])

    def test_safe_legacy_primitive_dict(self):
        payload=pickle.dumps({0:100, 2047:1},protocol=4)
        self.assertEqual(load_counts(payload),{0:100,2047:1})

    def test_dangerous_pickle_global_rejected(self):
        attack=b'cos\nsystem\n(S\'echo DONT_EXECUTE\'\ntR.'
        with self.assertRaises(ValueError): load_counts(attack)

    def test_legacy_invalid_counter_rejected(self):
        for bad in [{-1:2},{2048:2},{5:0},{1:'no'},{}]:
            with self.assertRaises(ValueError): load_counts(pickle.dumps(bad,protocol=4))

    def test_controlled_vehicle_class_uses_descriptor_id(self):
        regs={IW+0x0c:8,EW+0x1db8:2,IW+0xc60+2*4:0x02002000,
              EW+0x2000+0x1c:DESC0+7*0x3c}
        read16=lambda a:regs.get(a,0)
        read32=lambda a:regs.get(a,0)
        self.assertEqual(controlled_mode(read16,read32,lambda _:0),'vehicle_007')
        self.assertEqual(controlled_mode(read16,read32,lambda _:1),'foot')
        self.assertEqual(controlled_mode(read16,read32,lambda _:3),'unclassified')
        regs[IW+0x0c]=0xffff
        self.assertEqual(controlled_mode(read16,read32,lambda _:0),'unclassified')

    def test_rolling_prelevel_reads_are_attributed_only_on_level_start(self):
        p=PageRecorder(prelevel_present_frames=2)
        p.read(0x08001000,1); p.presented()
        p.read(0x08002000,1); p.presented()
        p.read(0x08003000,1); p.presented()
        p.read(0x08004000,1); p.presented(2,'foot','early_play')
        self.assertEqual(p.data[(2,'unclassified','pre_level')], {2:1,3:1,4:1})
        self.assertNotIn(1,p.data[(2,'unclassified','pre_level')])
        p.read(0x08005000,4);p.presented(2,'foot','early_play')
        self.assertEqual(p.data[(2,'foot','early_play')], {5:1})

    def test_prelevel_does_not_claim_a_map_if_level_never_starts(self):
        p=PageRecorder(2)
        p.read(0x08001000,2);p.presented()
        self.assertEqual(dict(p.data),{})

    def test_group_share_does_not_claim_misses(self):
        cap=capture(0,'foot','play',{1:1,2:2},source='synthetic')
        rep=summarize([cap],budget4k=1)
        self.assertIn('no_temporal_cache_model',rep['classification'])
        self.assertAlmostEqual(rep['per_scene_candidate_read_share'][0]['candidate_data_read_share'],2/3,places=4)


if __name__=='__main__': unittest.main()