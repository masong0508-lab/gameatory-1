#!/usr/bin/env python3
"""Analyze ROM *data read* pages by map/mode; no ROM bytes or game text.

A scenario is a JSON object with map, mode, phase, 4K page->read-count pairs,
and provenance. Counts select candidate resident pages but do not directly
predict CD seeks or FPS; a temporal replay is still needed.
"""
from __future__ import annotations
import argparse
import collections
import json
import re
import sys
from pathlib import Path

NMAP = 11
NPAGE = 2048
PAGE = 4096
MODE_RE = re.compile(r'^(foot|vehicle_\d{1,3}|unclassified)$')
PHASES = {'pre_level', 'early_play', 'play', 'combined'}


def page_indices(address: int, size: int) -> tuple[int, ...]:
    """Return GBA original-8MiB ROM 4KiB page indices for one data read.

    This is a mirror-window address test; the caller must determine whether the
    access was DATA, not an opcode fetch, and whether DMA was captured.
    """
    if not isinstance(address, int) or not isinstance(size, int) or size < 1 or size > 4096:
        raise ValueError('invalid_read')
    if (address >> 24) not in (8, 10, 12):
        raise ValueError('not_rom')
    off = address & 0x01ffffff
    if off >= 8 * 1024 * 1024 or off + size > 8 * 1024 * 1024:
        raise ValueError('rom_outside_original_8m')
    return tuple(range(off // PAGE, (off + size - 1) // PAGE + 1))


def validate(raw):
    if not isinstance(raw, dict) or raw.get('schema') != 1:
        raise ValueError('wrong_capture_schema')
    mi = raw.get('map')
    if type(mi) is not int or not 0 <= mi < NMAP:
        raise ValueError('invalid_map')
    mode = raw.get('mode')
    if not isinstance(mode, str) or not MODE_RE.fullmatch(mode):
        raise ValueError('invalid_mode')
    phase = raw.get('phase')
    if phase not in PHASES:
        raise ValueError('invalid_phase')
    reads = raw.get('reads4k')
    if not isinstance(reads, dict) or not reads:
        raise ValueError('empty_reads4k')
    out = {}
    for p, n in reads.items():
        if not isinstance(p, str) or not p.isascii() or not p.isdecimal() or str(int(p)) != p:
            raise ValueError('invalid_page_id')
        page = int(p)
        if page < 0 or page >= NPAGE or type(n) is not int or n <= 0:
            raise ValueError('invalid_page_count')
        out[page] = n
    return (mi, mode, phase, out)


def capture(map_id, mode, phase, counts, *, source):
    return {'schema': 1, 'map': map_id, 'mode': mode, 'phase': phase,
            'reads4k': {str(k): counts[k] for k in sorted(counts)},
            'source': source, 'bytes_included': False}


def summarize(records, budget4k=56, required_modes=()):
    if not isinstance(budget4k, int) or budget4k < 1 or budget4k > NPAGE:
        raise ValueError('invalid_budget')
    for m in required_modes:
        if not isinstance(m, str) or not MODE_RE.fullmatch(m) or m == 'unclassified':
            raise ValueError('invalid_required_mode')
    required_modes = sorted(set(required_modes))
    scenes = []
    combined = collections.Counter()
    by_scene = {}
    for rec in records:
        mi, mode, phase, counts = validate(rec)
        key = (mi, mode, phase)
        by_scene.setdefault(key, collections.Counter()).update(counts)
    if not by_scene:
        raise ValueError('no_captures')
    for (mi, mode, phase), counts in sorted(by_scene.items()):
        total = sum(counts.values())
        # Equal weight per scene, so a long-running route does not drown out
        # shorter map/vehicle captures. No claim this predicts CD latency.
        for page, n in counts.items():
            combined[page] += n / total
        scenes.append({'map': mi, 'mode': mode, 'phase': phase,
                       'distinct_4k': len(counts), 'total_data_reads': total})
    selected = [k for k, _ in sorted(combined.items(), key=lambda kv: (-kv[1], kv[0]))[:budget4k]]
    aggregate16 = collections.Counter()
    for p, weight in combined.items():
        aggregate16[p // 4] += weight
    ranked16 = [p for p, _ in sorted(aggregate16.items(), key=lambda kv: (-kv[1], kv[0]))]
    maps = sorted({r['map'] for r in scenes if r['phase'] != 'pre_level'})
    veh = sorted({r['mode'] for r in scenes if r['mode'].startswith('vehicle_')})
    observed_pairs = {(r['map'], r['mode']) for r in scenes if r['phase'] != 'pre_level'}
    missing_pairs = [{'map': mi, 'mode': mode} for mi in range(NMAP)
                     for mode in required_modes if (mi, mode) not in observed_pairs]
    per_scene = []
    for (mi, mode, phase), counts in sorted(by_scene.items()):
        total = sum(counts.values())
        per_scene.append({'map': mi, 'mode': mode, 'phase': phase,
                          'candidate_data_read_share': round(sum(counts.get(p, 0) for p in selected) / total, 5)})
    return {'schema': 1, 'classification': 'read_frequency_only_no_temporal_cache_model',
            'budget_4k_pages': budget4k, 'candidate_4k_pages': sorted(selected),
            'candidate_16k_groups_ranked': ranked16,
            'observed_map_ids': maps, 'missing_map_ids': sorted(set(range(NMAP)) - set(maps)),
            'observed_vehicle_descriptor_indices': veh,
            'complete_11_map_coverage': len(maps) == NMAP,
            'required_modes': required_modes,
            'missing_required_map_mode_pairs': missing_pairs,
            'complete_required_map_mode_matrix': bool(required_modes) and not missing_pairs,
            'scenes': scenes, 'per_scene_candidate_read_share': per_scene,
            'warnings': ['No traffic/scene is certified unless its capture was observed.',
                         'CPU data read frequencies are not CD miss counts; validate with a temporal cache trace.',
                         'DMA data and original GBA hardware behavior may be missing from the simulator profile.']}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('captures', type=Path, nargs='+', help='public-safe page/count JSON captures')
    ap.add_argument('--budget4k', type=int, default=56,
                    help='candidate 4 KiB resident pages (not a PS1 RAM allocation)')
    ap.add_argument('--require-11-maps', action='store_true', help='return nonzero unless all 11 map IDs measured')
    ap.add_argument('--require-mode', action='append', default=[],
                    help='observed mode required on EVERY map (repeat e.g. foot, vehicle_007)')
    ap.add_argument('--require-complete-matrix', action='store_true',
                    help='return nonzero unless every listed --require-mode is observed on every map')
    ap.add_argument('--output', type=Path, help='sanitized analysis JSON output')
    a = ap.parse_args(argv)
    if a.require_complete_matrix and not a.require_mode:
        ap.error('--require-complete-matrix needs at least one --require-mode')
    try:
        records = [json.loads(p.read_text(encoding='utf-8')) for p in a.captures]
        report = summarize(records, a.budget4k, a.require_mode)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        ap.error(str(exc))
    text = json.dumps(report, indent=2, sort_keys=True) + '\n'
    if a.output:
        a.output.parent.mkdir(parents=True, exist_ok=True)
        a.output.write_text(text, encoding='utf-8')
    print(text, end='')
    incomplete = ((a.require_11_maps and not report['complete_11_map_coverage']) or
                  (a.require_complete_matrix and not report['complete_required_map_mode_matrix']))
    return 3 if incomplete else 0


if __name__ == '__main__':
    raise SystemExit(main())