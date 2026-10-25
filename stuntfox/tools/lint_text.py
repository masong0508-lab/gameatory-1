#!/usr/bin/env python3
"""What stage-2 code may say and write, checked on its sources (the build runs this after linking).

Stage-2 files (S2_SOURCES in tools/s2build.py that exist, stage2.h, pbapi.h):
  - no ticker: Payback's ticker (0x08039871, its line queue) and ours (say, news_send, sg_note, shout, the
    TICK_ names) are for Payback's own words and the old game's; a stage-2 title goes through Payback's raw
    banner, the steady line at y117 through the HUD, and nothing else prints.
  - no writes where the ticker's state is (0x02001df8, 0x020000c0), by any name.
  - a banner title is at most 19 letters (Payback copies it into a slot of 20 bytes).
  - text drawn with d_text uses the letters of the font (A-Z, digits and punctuation up to _, lower case drawn
    as upper) and fits the screen from where it starts.
Every text file of the repo (stuntfox/ and below, not build/): no model or tool names.

    python3 tools/lint_text.py
"""
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

TICKER = [r'\bPB_TICKER\b', r'\bTICK_\w*', r'\bTICKER\w*', r'\bsay\s*\(', r'\bnews_send\s*\(', r'\bsg_note\s*\(',
          r'\bshout\s*\(', r'\b0[xX]0*8039871\b', r'\b0[xX]0*8039870\b']
BANNED_WRITE = [r'\b0[xX]0*2001df8\b', r'\b0[xX]0*20000c0\b']
BANNER_MAX = 19                 # letters (pb_banner_raw: strcpy into 20 bytes)
SCREEN_W, TEXT_W = 240, 6       # (draw2d.h)
# the names an assistant or a model goes by: none in the repo (written in pieces: this file is in the repo)
NAMES = re.compile(r'\b(' + '|'.join(w[0] + w[1:] for w in (
    'cl' + 'aude', 'anth' + 'ropic', 'cha' + 'tgpt', 'g' + 'pt-?[0-9]', 'open' + 'ai', 'cop' + 'ilot', 'gem' + 'ini',
    'son' + 'net', 'hai' + 'ku', 'o' + 'pus', 'l' + 'lm')) + r')\b', re.I)

STRING = r'"((?:[^"\\\n]|\\.)*)"'


def strip_comments(s):
    return re.sub(r'/\*.*?\*/|//[^\n]*', lambda m: '\n' * m.group(0).count('\n'), s, flags=re.S)


def strip_strings(s):
    return re.sub(STRING, lambda m: '""', s)


def unescape(lit):
    return re.sub(r'\\(.)', lambda m: {'n': '\n', 't': '\t'}.get(m.group(1), m.group(1)), lit)


def lint_stage2(path):
    bad, name = [], os.path.basename(path)
    raw = open(path).read()
    code = strip_comments(raw)
    plain = strip_strings(code)
    for n, line in enumerate(plain.split('\n'), 1):
        for pat in TICKER:
            if re.search(pat, line):
                bad.append('%s:%d: the ticker (%s)' % (name, n, pat.strip('\\b')))
        for pat in BANNED_WRITE:
            if re.search(pat, line):
                bad.append('%s:%d: the ticker\'s state (%s)' % (name, n, pat.strip('\\b')))
    for n, line in enumerate(code.split('\n'), 1):
        for m in re.finditer(r'\bpb_banner_raw\s*\(\s*[^,()]+,\s*' + STRING, line):
            t = unescape(m.group(1))
            if len(t) > BANNER_MAX:
                bad.append('%s:%d: banner "%s" is %d letters, %d at most' % (name, n, t, len(t), BANNER_MAX))
        for m in re.finditer(r'\bd_text\s*\(\s*([^,()]+),\s*[^,()]+,\s*' + STRING, line):
            t = unescape(m.group(2))
            odd = sorted({c for c in t if not 32 <= ord(c.upper()) <= 95})
            if odd:
                bad.append('%s:%d: "%s" has letters the font lacks: %s' % (name, n, t, ' '.join(repr(c) for c in odd)))
            x = m.group(1).strip()
            if re.fullmatch(r'\d+', x) and int(x) + TEXT_W * len(t) > SCREEN_W:
                bad.append('%s:%d: "%s" from x %s runs off the screen (%d letters)' % (name, n, t, x, len(t)))
    return bad


def repo_files(root):
    try:
        out = subprocess.run(['git', '-C', root, 'ls-files', '--cached', '--others', '--exclude-standard'],
                             capture_output=True, text=True, check=True).stdout.split('\n')
        return [os.path.join(root, f) for f in out if f]
    except (OSError, subprocess.CalledProcessError):
        return [os.path.join(d, f) for d, _, fs in os.walk(root) if '/build' not in d for f in fs]


def lint_names(root):
    bad = []
    for f in repo_files(root):
        if not f.endswith(('.c', '.h', '.s', '.py', '.md', '.txt', '.ld', '.json', '.sh', '.js')) or not os.path.isfile(f):
            continue
        try:
            text = open(f, encoding='utf-8').read()
        except (UnicodeDecodeError, OSError):
            continue
        for n, line in enumerate(text.split('\n'), 1):
            m = NAMES.search(line)
            if m:
                bad.append('%s:%d: "%s" (no model or tool names in the repo)' % (os.path.relpath(f, root), n, m.group(0)))
    return bad


def check(root, files):
    """The report; SystemExit with what is wrong. files: the stage-2 sources that were built."""
    src = os.path.join(root, 'src')
    stage2 = sorted({os.path.abspath(f) for f in files if os.path.dirname(os.path.abspath(f)) == os.path.abspath(src)}
                    | {os.path.join(src, h) for h in ('stage2.h', 'pbapi.h') if os.path.exists(os.path.join(src, h))})
    bad = []
    for f in stage2:
        bad += lint_stage2(f)
    bad += lint_names(root)
    if bad:
        sys.exit('\n'.join('lint_text: ' + b for b in bad) + '\nlint_text: failed')
    return 'lint_text: OK, %d stage-2 files without the ticker, none over a limit; no model or tool names in the repo' \
        % len(stage2)


if __name__ == '__main__':
    sys.path.insert(0, HERE)
    import s2build
    print(check(ROOT, s2build.sources()))
