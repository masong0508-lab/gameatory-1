# Music tools (remixes of Payback's songs)

Python 3 + numpy + scipy, and ffmpeg (libmp3lame) for the MP3s (`MIX_WAV_ONLY=1` writes WAVs only, as
the ROM build does). Everything is read from your own Payback ROM at run time
(`export PAYBACK_ROM=...`); this folder holds code and remix scripts only, never audio.

| module | |
|---|---|
| `pbsong.py` | songs 0-4 as data (samples, patterns, order list); reference .mod writer |
| `render.py` | faithful renders: Payback's own player (fixed 50 Hz effect ticks, its effect set) or ProTracker; stems, row timeline, note events |
| `dsp.py` | filters and sweeps, oscillators, envelopes, delay, reverb, compressor, ducking, limiter, LUFS and true peak, mastering |
| `synth.py` | our own synthesised instruments (drums, basses, leads, pads, FX), deterministic |
| `mix.py` | arranger/mixer (tracks, buses, automation, sidechain), WAV/MP3 export with ID3 title, and `Original` to reuse a song's notes, chords and samples |
| `analyze.py` | Markdown analysis of a song (tempo, key, structure, channels, samples, hooks, chords) |
| `example_remix.py` | a 16-bar remix over song 1 using all of the above |

    python3 render.py "$PAYBACK_ROM" 1 /tmp/song1.wav
    python3 example_remix.py /tmp/example        # /tmp/example.wav and .mp3, -14 LUFS, -1 dBTP

Each module's docstring documents its API.
