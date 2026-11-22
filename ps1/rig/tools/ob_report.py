#!/usr/bin/env python3
"""ob_report.py RUNDIR [RUNDIR ...]: one line of facts per run directory written by obrun.py (summary.json, samples.csv,
tty.log, trace.txt): core, disc, firmware flags, when the level clock started, guest speed before / in the level, CD
fetches, trap counts, kernel calls, interrupts taken, pad and memory card counters, runtime error lines on the TTY."""
import csv, json, os, re, sys


def one(d):
    s = json.load(open(os.path.join(d, 'summary.json')))
    rows = list(csv.DictReader(open(os.path.join(d, 'samples.csv'))))
    fps = s.get('core_fps') or 59.94
    out = {'run': os.path.basename(d.rstrip('/')), 'core': s['core'], 'disc': os.path.basename(s['disc']), 'frames': s['frames']}
    opts = s.get('opts') or {}
    extra = {k.split('_', 1)[1]: v for k, v in opts.items() if any(t in k for t in ('Speedup', 'CropMode', 'ExecutionMode'))}
    extra = {k: v for k, v in extra.items() if not (k.endswith('Speedup') and v == '1')}
    if extra:
        out['options'] = extra
    t = s.get('trace') or {}
    if t:
        out['openboot_flags'] = '%#x' % t.get('flags', 0)
        exc = t.get('exc') or {}
        out['traps'] = {k: v for k, v in exc.items() if v} if isinstance(exc, dict) else exc
        out['irqs_taken'] = t.get('irq_total', 0)
        out['error'] = t.get('error', 0)
    else:
        out['firmware'] = 'no openboot trace table (other firmware)'
    if s.get('calls') is not None:
        out['kernel_calls'] = s['calls']
    lv = [r for r in rows if r.get('lvl_clock', '0').isdigit() and 0 < int(r['lvl_clock']) < 1000000 and int(r['frame']) > 600]
    def rate(rs, key):
        if len(rs) < 2:
            return None
        dt = (int(rs[-1]['frame']) - int(rs[0]['frame'])) / fps
        return round((int(rs[-1][key]) - int(rs[0][key])) / dt, 3) if dt > 0 else None
    if rows and 'g_gframes' in rows[0]:
        pre = [r for r in rows if int(r['frame']) > 600 and (not lv or int(r['frame']) < int(lv[0]['frame']))]
        if lv:
            out['level_clock_from'] = {'emu_frame': int(lv[0]['frame']), 'emu_s': round(int(lv[0]['frame']) / fps, 1), 'guest_frame': int(lv[0]['g_gframes'])}
            out['level'] = {'emu_s': round((int(lv[-1]['frame']) - int(lv[0]['frame'])) / fps, 1), 'guest_fps': rate(lv, 'g_gframes'), 'presents_per_s': rate(lv, 'g_pres'),
                            'cd_fetch_per_s': rate(lv, 'rom_miss_count'), 'pad_polls_per_s': rate(lv, 'pad_polls') if 'pad_polls' in rows[0] else None}
        else:
            out['level_clock_from'] = None
        out['before_level'] = {'guest_fps': rate(pre, 'g_gframes'), 'presents_per_s': rate(pre, 'g_pres'), 'cd_fetch_per_s': rate(pre, 'rom_miss_count'),
                               'pad_polls_per_s': rate(pre, 'pad_polls') if 'pad_polls' in rows[0] else None}
        last = rows[-1]
        out['last'] = {k: int(last[k]) for k in ('g_gframes', 'g_pres', 'cd_sectors', 'rom_miss_count', 'pad_polls', 'pad_fails', 'mc_reads', 'mc_writes', 'mc_err', 'sf3_ok') if k in last and last[k] != ''}
        stuck = None
        for r in rows:
            if stuck is None or r['g_gframes'] != stuck['g_gframes']:
                stuck = r
        out['guest_frame_last_changed_at_emu_s'] = round(int(stuck['frame']) / fps, 1)
    try:
        tty = open(os.path.join(d, 'tty.log'), 'rb').read().decode('latin-1')
        errs = {}
        for m in re.finditer(r'CD error int \d+|CD timeout|CD busy cmd \d+|MC [a-z /]*error[a-z /]*|MC no card|MC crc[^\n]*|RT_MISS[^\n]{0,30}|PANIC[^\n]{0,40}|FAULT[^\n]{0,40}', tty):
            errs[m.group(0).strip()] = errs.get(m.group(0).strip(), 0) + 1
        out['tty_error_lines'] = errs
        out['tty_bytes'] = len(tty)
    except OSError:
        pass
    for m in s.get('marks', []):
        if m.get('label') == 'level_end_state':
            out['player_end'] = m.get('player'); out['pad'] = {k: m[k] for k in ('pad_id', 'pad_analog', 'pad_cfg_tries', 'pad_fails') if k in m}
    return out


if __name__ == '__main__':
    for d in sys.argv[1:]:
        try:
            print(json.dumps(one(d)))
        except Exception as e:      # noqa
            print(json.dumps({'run': d, 'unreadable': repr(e)}))
