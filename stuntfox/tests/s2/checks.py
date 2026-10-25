"""The build's three checks (memguard, pbapi_check, lint_text) pass on the tree and catch what they are for: each one is
run on copies of its input with one fault put in. No emulator; needs the linked ELF and Payback's ROM.

    ELF=build/merge/stuntfox-merge.elf PAYBACK_ROM=... python3 tests/s2/checks.py       (from stuntfox/)
"""
import os
import re
import sys
import tempfile

ROOT = os.getcwd()
sys.path.insert(0, os.path.join(ROOT, 'tools'))
import lint_text      # noqa: E402
import memguard       # noqa: E402
import pbapi_check    # noqa: E402

ELF = os.environ['ELF']
ORIG = open(os.environ['PAYBACK_ROM'], 'rb').read()
SRC = os.path.join(ROOT, 'src')
LD, MAP = os.path.join(SRC, 'merge.ld'), os.path.join(ROOT, 'memmap.txt')
bad = 0
tmp = tempfile.mkdtemp()


def case(name, ok, detail=''):
    global bad
    print('%s  %s%s' % ('PASS' if ok else 'FAIL', name, '  (' + detail + ')' if detail else ''), flush=True)
    bad += not ok


def fails(fn, *want):
    """The text of the SystemExit fn raised ('' if it did not), and whether it holds every phrase in want."""
    try:
        fn()
    except SystemExit as x:
        msg = str(x)
        return msg, all(w in msg for w in want)
    return '', False


def write(name, text):
    p = os.path.join(tmp, name)
    open(p, 'w').write(text)
    return p


# ---- memguard: the map in memmap.txt, with a line added or changed ----
def mm(extra='', sub=None):
    t = open(MAP).read()
    if sub:
        t = t.replace(*sub)
    return write('memmap.txt', t + '\n' + extra + '\n')


rep = memguard.check(ELF, LD, MAP)
case('memguard passes on the tree', 'memguard: OK' in rep, rep.split('\n')[1])
msg, ok = fails(lambda: memguard.check(ELF, LD, mm('0x0203d000-0x0203ff90 a Payback word in our keep')), "overlaps Payback's")
case('memguard: a Payback range over our keep is caught', ok, msg.split('\n')[0][:110])
msg, ok = fails(lambda: memguard.check(ELF, LD, mm('RESERVE 0x0203d000-0x0203ff90 stage 3 in our keep')), 'overlaps the stage 3 reserve')
case('memguard: the stage 3 reserve is kept clear', ok, msg.split('\n')[0][:110])
msg, ok = fails(lambda: memguard.check(ELF, LD, mm('SCRATCH 0x0203d000-0x0203ff90 per-frame data only')), 'per-frame scratch')
case('memguard: our variables in a per-frame scratch range are caught', ok, msg.split('\n')[0][:110])
msg, ok = fails(lambda: memguard.check(ELF, LD, mm(sub=('reserve=1024', 'reserve=4096'))), 'short of the stage 3 reserve')
case('memguard: a keep with less free than the reserve and margin is caught', ok, msg.split('\n')[0][:110])

# ---- pbapi_check: the header against Payback's ROM, the sources for raw addresses ----
hdr = open(os.path.join(SRC, 'pbapi.h')).read()


def retarget(name, value):
    """A copy of pbapi.h (in its own folder, as check_api reads it) with one address changed."""
    text, n = re.subn(r'(#define\s+%s\s+)0x[0-9a-fA-F]+' % name, lambda m: m.group(1) + value, hdr)
    assert n == 1, name
    d = os.path.join(tmp, 'h_' + name)
    os.makedirs(d, exist_ok=True)
    open(os.path.join(d, 'pbapi.h'), 'w').write(text)
    return os.path.join(d, 'pbapi.h')


rom = pbapi_check.Rom(ORIG)
api, b, notes = pbapi_check.check_api(rom, os.path.join(SRC, 'pbapi.h'))
case('pbapi_check passes on the header', not b, '%d addresses, %d notes' % (len(api), len(notes)))
for what, name, value in (
        ('a RAM word nothing in Payback addresses', 'PBA_CLOCK', '0x0203e000'),
        ('a function address that is not a function start', 'PBA_BANNER_RAW', '0x08039bcb'),
        ('a bl site that goes elsewhere', 'PBA_EEP_IDENT_SITE', '0x08027c7a'),
        ('a function without the Thumb bit', 'PBA_BANNER_IDX', '0x0807a684')):
    _, b, _ = pbapi_check.check_api(rom, retarget(name, value))
    case('pbapi_check: %s is caught' % what, any(x.startswith(name) for x in b), (b or ['nothing'])[0][:100])
raw = write('s2raw.c', 'void f(void) { *(volatile int *)0x02001e00 = 1; }\n')
case('pbapi_check: a raw EWRAM address in a stage-2 source is caught', pbapi_check.scan_files([raw]) != [], pbapi_check.scan_files([raw])[0])
raw = write('s2rom.c', 'int g(void) { return ((int (*)(int))0x08039bc9)(1); }\n')
case('pbapi_check: a raw Payback ROM address is caught', pbapi_check.scan_files([raw]) != [])
raw = write('s2cm.c', '/* PB_CLOCK is 0x02001e00 */\nint h(void) { return 7; }  // 0x03001000\n')
case('pbapi_check: addresses in comments only: nothing', pbapi_check.scan_files([raw]) == [])

# ---- lint_text ----
for what, code, want in (
        ('the ticker by name', 'void f(void) { say("hi"); }', 'the ticker'),
        ('a TICK_ constant', 'int g = TICK_NEWS;', 'the ticker'),
        ('the old game\'s news line', 'void f(void) { news_send(1, "x"); }', 'the ticker'),
        ('Payback\'s ticker function by address', 'void f(void) { ((void (*)(void))0x08039871)(); }', 'the ticker'),
        ('a write where the ticker\'s state is', 'void f(void) { *(volatile int *)0x02001df8 = 0; }', 'state'),
        ('a banner title of 20 letters', 'void f(void) { pb_banner_raw(0, "ABCDEFGHIJKLMNOPQRST"); }', 'letters, 19 at most'),
        ('text past the right edge', 'void f(void) { d_text(200, 5, "TOO LONG HERE"); }', 'runs off the screen'),
        ('letters the font lacks', 'void f(void) { d_text(4, 4, "a~b"); }', 'font lacks')):
    p = write('l_%d.c' % abs(hash(code)), code + '\n')
    r = lint_text.lint_stage2(p)
    case('lint_text: %s is caught' % what, any(want in x for x in r), (r or ['nothing'])[0][:100])
p = write('l_ok.c', '/* the ticker: say( TICK_X */ void f(void) { pb_banner_raw(0, "ABCDEFGHIJKLMNOPQRS"); d_text(4, 4, "SCORE 0"); }\n')
case('lint_text: a 19-letter banner, text that fits and the ticker in a comment are fine', lint_text.lint_stage2(p) == [], str(lint_text.lint_stage2(p)))
d = os.path.join(tmp, 'names')
os.makedirs(d)
open(os.path.join(d, 'x.py'), 'w').write('# written with %s\n' % ('Cl' + 'aude'))
r = lint_text.lint_names(d)
case('lint_text: a model name in a repo file is caught', len(r) == 1 and 'no model or tool names' in r[0], r[0] if r else 'nothing')
r = lint_text.lint_names(ROOT)
case('lint_text: none in this repo', r == [], '%d hits' % len(r))

print('ALL PASS' if not bad else '%d FAILED' % bad)
sys.exit(1 if bad else 0)
