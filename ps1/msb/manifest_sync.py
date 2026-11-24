#!/usr/bin/env python3
"""manifest_sync.py WT [target=source ...]: point targets at new full copies (dropping their patches), then refresh every stage19 sha256."""
import json, hashlib, sys, os
wt = sys.argv[1]; mp = os.path.join(wt, 'ps1/tools/source_manifest.json')
m = json.load(open(mp))
for a in sys.argv[2:]:
    tgt, src = a.split('=')
    hit = [f for f in m['files'] if f['target'] == tgt]
    if hit: hit[0]['source'] = src
    else: m['files'].append({'source': src, 'target': tgt, 'sha256': ''})
    m['patches'] = [p for p in m['patches'] if p['target'] != tgt]
for f in m['files']:
    if f['source'].startswith('stage19/') or f['source'].startswith('tools/'):
        h = hashlib.sha256(open(os.path.join(wt, 'ps1', f['source']), 'rb').read()).hexdigest()
        if h != f['sha256']:
            print('updated', f['source']); f['sha256'] = h
open(mp, 'w').write(json.dumps(m, indent=2) + '\n')
