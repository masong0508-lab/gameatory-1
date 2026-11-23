"""ROM-free page-profiling tests, including adversarial legacy pickle input."""
import collections
import hashlib
import io
import json
import pickle
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from working_set import page_indices, validate, capture, summarize, trace_fingerprint, LIVE_SOURCE, main as summary_main
from from_reference import load_counts
from sim_capture import controlled_mode, owner_rom_matches, PageRecorder, EW, IW, DESC0


def live(map_id, mode, phase, counts):
    data = capture(map_id, mode, phase, counts, source=LIVE_SOURCE)
    data.update(coverage_status='live_observed', sampled_present_frames=8,
                trace_sha256=trace_fingerprint(counts))
    return data


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
        samples=[live(0,'foot','play',{2:1000000}),
                 live(1,'foot','play',{5:100})]
        rep=summarize(samples, budget4k=2)
        self.assertEqual(rep['candidate_4k_pages'],[2,5])
        self.assertEqual(rep['missing_map_ids'], list(range(2,11)))
        self.assertFalse(rep['complete_11_map_coverage'])

    def test_11_map_coverage_flag_requires_actual_captures(self):
        samples=[live(m,'foot','play',{m:100}) for m in range(11)]
        rep=summarize(samples, budget4k=10)
        self.assertTrue(rep['complete_11_map_coverage'])
        self.assertEqual(len(rep['observed_map_ids']),11)
        self.assertEqual(rep['observed_vehicle_descriptor_indices'],[])

    def test_required_per_map_mode_matrix_cannot_be_faked_by_any_map_run(self):
        samples=[capture(mi,'unclassified','combined',{mi:5},source='stage7_snapdump_h_memrd') for mi in range(11)]
        rep=summarize(samples,budget4k=11,required_modes=['foot','vehicle_007'])
        self.assertFalse(rep['complete_11_map_coverage'])
        self.assertFalse(rep['complete_required_map_mode_matrix'])
        self.assertEqual(len(rep['missing_required_map_mode_pairs']),22)
        samples=[live(mi,mode,'play',{mi:(5 if mode=='foot' else 7)})
                 for mi in range(11) for mode in ('foot','vehicle_007')]
        rep=summarize(samples,budget4k=11,required_modes=['foot','vehicle_007'])
        self.assertTrue(rep['complete_required_map_mode_matrix'])
        self.assertEqual(rep['missing_required_map_mode_pairs'],[])

    def test_16k_aggregation(self):
        cap=live(0,'vehicle_007','play',{0:10,1:20,4:5})
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

    def test_reference_relabel_to_11_maps_never_counts_as_live(self):
        # A historical trace labeled map=0..10, mode=foot is NOT a capture.
        same = {13: 100, 22: 20}
        copies = [capture(mi, 'foot', 'play', same, source='stage7_snapdump_h_memrd')
                  for mi in range(11)]
        for cap in copies:
            cap.update(coverage_status='partial_unverified_route',
                       reference_trace_sha256='a'*64)
        rep = summarize(copies, required_modes=['foot'])
        self.assertEqual(rep['observed_map_ids'], [])
        self.assertEqual(rep['missing_map_ids'], list(range(11)))
        self.assertEqual(len(rep['missing_required_map_mode_pairs']), 11)
        self.assertFalse(rep['complete_required_map_mode_matrix'])

    def test_duplicate_live_trace_relabel_across_maps_is_rejected(self):
        repeated = {31: 9, 32: 5}
        records = [live(0, 'foot', 'play', repeated),
                   live(1, 'foot', 'play', repeated)]
        rep = summarize(records, required_modes=['foot'])
        self.assertEqual(rep['reused_trace_sha256_count'], 1)
        self.assertEqual(rep['observed_map_ids'], [])
        self.assertEqual(sum(s['coverage_eligible'] for s in rep['scenes']), 0)
        records.append(live(2, 'foot', 'play', {3: 17}))
        rep = summarize(records)
        self.assertEqual(rep['observed_map_ids'], [2])

    def test_claimed_live_trace_needs_matching_digest_and_sample_count(self):
        good = live(4, 'vehicle_011', 'play', {45: 11})
        for bad in (
            {**good, 'trace_sha256': '0'*64},
            {**good, 'sampled_present_frames': 0},
            {**good, 'sampled_present_frames': True},
            {**good, 'source': 'stage7_snapdump_h_memrd'},
            {**good, 'coverage_status': 'partial_unverified_route'},
        ):
            self.assertFalse(summarize([bad])['complete_11_map_coverage'])
            self.assertEqual(summarize([bad])['observed_map_ids'], [])
        self.assertEqual(summarize([good])['observed_map_ids'], [4])

    def test_require_mode_works_without_extra_complete_matrix_flag(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'sample.json'
            path.write_text(json.dumps(live(0,'foot','play',{0:10})))
            with redirect_stdout(io.StringIO()):
                rc = summary_main([str(path), '--require-mode', 'foot'])
            self.assertEqual(rc, 3)

    def test_prelevel_menu_reads_excluded_from_default_page_ranking(self):
        records = [live(0,'foot','play',{12:100}),
                   capture(0,'unclassified','pre_level',{1595:9999999},
                           source='unicorn_sim_h_memrd_cpu_data_only')]
        rep = summarize(records, budget4k=1)
        self.assertEqual(rep['candidate_4k_pages'], [12])
        self.assertEqual(rep['candidate_16k_groups_ranked'][0], 3)
        self.assertFalse(rep['scenes'][0]['coverage_eligible'] if rep['scenes'][0]['phase']=='pre_level' else rep['scenes'][1]['coverage_eligible'])

    def test_boolean_schema_and_nonstring_phase_are_clean_errors(self):
        a = live(0,'foot','play',{9:1})
        for bad in ({**a,'schema':True}, {**a,'phase':[]}, {**a,'reads4k':{'²':1}}):
            with self.assertRaises(ValueError):
                validate(bad)

    def test_malformed_primitive_pickle_is_clean_value_error(self):
        for data in (b'\\x80\\x04\\x95', b'\\x80\\x04}\\x94(', b''):
            with self.assertRaises(ValueError):
                load_counts(data)

    def test_simulator_rejects_wrong_rom_even_if_8mb_size_matches(self):
        zeroed = bytes(0x800000)
        correct_for_synthetic = hashlib.sha1(zeroed).hexdigest()
        self.assertTrue(owner_rom_matches(zeroed, correct_for_synthetic))
        self.assertFalse(owner_rom_matches(zeroed,
                         '08df2c6f1b932b8c6e5e1bc9c6ccbe738832d2b7'))
        self.assertFalse(owner_rom_matches(zeroed[:-1], correct_for_synthetic))

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