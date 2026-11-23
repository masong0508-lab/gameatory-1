"""ROM-free evidence rules for a PS1 GPU display-flip picture scan.

g_pres marks the *start* of present(), not the display-buffer flip. On rc8
the runtime exports g_flips, incremented after GP1 display-start changes.
No game data, framebuffer bytes or libretro dependency is used here.
"""


def choose_counter(lookup, *, allow_legacy=False):
    """Return (symbol, release_grade).

    Modern rc8 discs must have g_flips. Older discs may opt in to the
    g_pres fallback for diagnostic purposes, but it cannot certify GPU
    synchronization. In particular, rc7 can change pictures between two
    observations of g_pres even when the GPU flipped correctly.
    """
    if lookup('g_flips') is not None:
        return 'g_flips', True
    if allow_legacy and lookup('g_pres') is not None:
        return 'g_pres', False
    return None, False


def display_step(previous, digest, counter):
    """One consecutive emulator-frame comparison.

    Returns (next_previous, picture_changed, changed_without_counter_step).
    Advance the previous counter *on every frame*, not only when the image
    changes: otherwise a flip that displayed an identical frame could
    conceal a later in-place screen mutation.
    """
    if type(counter) is not int:
        raise ValueError('missing_or_invalid_display_flip_counter')
    if previous is None:
        return (digest, counter), False, False
    last_digest, last_counter = previous
    changed = digest != last_digest
    return (digest, counter), changed, changed and counter == last_counter
