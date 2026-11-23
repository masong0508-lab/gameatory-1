#!/usr/bin/env python3
"""Safely convert legacy Track B ROM-data-read count pickles to public page IDs.

Only primitive protocol 4/5 integer-key/integer-value dict pickles are accepted.
No Python classes, reduce/build opcodes, arbitrary constructors, or ROM bytes.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import pickle
import pickletools
import struct
from pathlib import Path
from working_set import capture, validate

ALLOWED = frozenset({'PROTO', 'FRAME', 'EMPTY_DICT', 'MEMOIZE', 'MARK',
                     'BININT', 'BININT1', 'BININT2', 'SETITEMS', 'STOP'})


def load_counts(raw: bytes):
    if not raw or len(raw) > 5_000_000:
        raise ValueError('bad_trace_size')
    try:
        ops = []
        for op, _arg, _offset in pickletools.genops(raw):
            ops.append(op.name)
            if len(ops) > 100_000:
                raise ValueError('pickle_opcode_budget_exceeded')
    except (ValueError, IndexError, EOFError, TypeError, OverflowError,
            RecursionError, UnicodeError, struct.error):
        raise ValueError('malformed_pickle') from None
    if not ops or ops[-1] != 'STOP' or any(x not in ALLOWED for x in ops):
        raise ValueError('unsafe_or_unsupported_pickle_opcode')
    # With only these opcodes, unpickling performs primitive dict and integer
    # construction: there is no callable or arbitrary code execution opcode.
    try:
        obj = pickle.loads(raw)
    except (pickle.UnpicklingError, EOFError, ValueError, TypeError,
            OverflowError, RecursionError, UnicodeError, struct.error):
        raise ValueError('malformed_pickle') from None
    if type(obj) is not dict or not obj:
        raise ValueError('not_a_nonempty_counter')
    for page, n in obj.items():
        if type(page) is not int or not 0 <= page < 2048 or type(n) is not int or n < 1:
            raise ValueError('out_of_range_page_or_count')
    return obj


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('trace', type=Path, help='private .rompages trace containing ONLY page IDs and hit counts')
    ap.add_argument('--map', type=int, required=True)
    ap.add_argument('--mode', default='unclassified', help='do not assert on-foot/vehicle until independently verified')
    ap.add_argument('--phase', default='combined', choices=('combined','early_play','play','pre_level'))
    ap.add_argument('--output', type=Path, required=True, help='sanitized JSON with page numbers only')
    a = ap.parse_args(argv)
    try:
        raw = a.trace.read_bytes()
        counts = load_counts(raw)
        report = capture(a.map, a.mode, a.phase, counts, source='stage7_snapdump_h_memrd')
        report['reference_trace_sha256'] = hashlib.sha256(raw).hexdigest()
        report['coverage_status'] = 'partial_unverified_route'
        validate(report)
    except (OSError, ValueError) as e:
        ap.error(str(e))
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    print('wrote page/count-only capture: %d 4K pages, %d reads (not CD misses)' % (len(counts), sum(counts.values())))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())