"""Minimal remix: 16 bars over Payback song 1, using its own arpeggio notes and bass line with
our synths plus one of its samples. Shows every part of the toolchain in about 60 lines.

    PAYBACK_ROM=/path/to/Payback.gba python3 example_remix.py OUT_BASE   # writes OUT_BASE.wav/.mp3
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dsp    # noqa: E402
import mix    # noqa: E402
import synth  # noqa: E402
from synth import Inst  # noqa: E402


def build(out_base, bars=16):
    o = mix.Original(1)                                   # Payback song 1, from $PAYBACK_ROM
    m = mix.Mix(bpm=o.bpm, bars=bars, title=mix.remix_title(1), tail=3.0)
    m.bus('verb', lambda x: dsp.reverb(x, decay=2.8, wet_only=True), gain_db=-4)
    m.bus('echo', lambda x: dsp.delay(x, m.beats(0.75), feedback=0.4, mix=1.0) - x)

    # drums: our own sounds
    kick = m.track('kick', gain_db=-1)
    kick.pattern(0, bars, 'x...x...x...x...', Inst(synth.kick))
    hats = m.track('hats', gain_db=-10, pan=0.2, sends={'verb': 0.1})
    hats.pattern(2, bars - 2, '..x...x...x...x.', Inst(synth.hat), swing=0.08)
    clap = m.track('clap', gain_db=-6, sends={'verb': 0.25})
    clap.pattern(4, bars - 4, '....x.......x...', Inst(synth.clap))

    # bass: the original bass channel's notes (channel 1, sample 14) on our reese, ducked
    t0, _ = o.section(2)                                  # the original from order position 2
    src = [n for n in o.notes(channel=1, t0=t0, t1=t0 + m.bar(8)) if n.ins == 14]
    bass = m.track('bass', gain_db=-5, duck='kick', lp=[(m.bar(0), 250), (m.bar(8), 2500)])
    for rep in (0, 8):
        bass.notes(mix.retime(src, t0, m.bar(rep)), Inst(synth.reese, cutoff=700), transpose=12)

    # lead: the original arpeggio (channel 0) on our pluck, with echo
    arp = [n for n in o.notes(channel=0, t0=t0, t1=t0 + m.bar(8))]
    lead = m.track('lead', gain_db=-9, pan=-0.15, sends={'echo': 0.3, 'verb': 0.15}, duck='kick')
    lead.notes(mix.retime(arp, t0, m.bar(8)), Inst(synth.pluck), transpose=0)

    # pad on the song's chords, and one of Payback's own samples as a texture
    pad = m.track('pad', gain_db=-12, sends={'verb': 0.3}, duck=dict(key='kick', amount=0.5))
    saw_pad = Inst(synth.supersaw, attack=0.3, release=0.8)
    for i, (_, _, name, _) in enumerate(o.chords(t0, t0 + m.bar(8), beats=8)):
        notes = mix.chord(name if name != 'N.C.' else 'F#m', 3)
        for rep in (0, 8):
            pad.chord(m.bar(rep + 2 * i), saw_pad, notes, m.bar(2) - 0.05, 0.8)
    tex = m.track('texture', gain_db=-16, hp=400, sends={'verb': 0.5})
    tex.note(m.bar(0), o.sample_inst(13), 60 + o.tune.get(13, 0), m.bar(4))

    # transitions
    fx = m.track('fx', gain_db=-8, sends={'verb': 0.3})
    fx.clip(m.bar(6), synth.riser(m.bar(2)))
    fx.clip(m.bar(8), synth.impact(3.0))
    fx.clip(m.bar(8), synth.cymbal(2.5), gain_db=-6)

    audio, rep = m.render(lufs=-14.0, true_peak=-1.0, fade_out=4.0)
    rep.update(m.export(audio, out_base, kbps=320))
    return rep


if __name__ == '__main__':
    print(build(sys.argv[1] if len(sys.argv) > 1 else 'example_remix'))
