#!/usr/bin/env python3
"""Build a B3 resident-page candidate from measured private PS1 profiles.

Input is numeric-only JSON: schema=1, rom_bytes=16777216, page_bytes=4096,
metric="physical_miss_requests", scenes=[{"name":"walk","saturated":false,
"counts":{"0x123":12,"0x804":18}}, ...]. Each scene gets equal weight after
normalizing its physical-miss counts. The old remapped boot list contributes
a fixed, configurable small reserve. Do not feed a saturated counter or the
old B2 PGPROF diagnostic (it counted soft CLOCK hits as misses).

Output is page IDs only, suitable for RPG=/private/resident_b3.txt. This
predicts a working set, not an FPS or observed cache-miss result.
"""
import argparse
import json
from fractions import Fraction
from pathlib import Path

from mkpagelists_msb import pages, remap

ROM_BYTES = 16 * 1024 * 1024
PAGE_BYTES = 4096
PAGE_COUNT = ROM_BYTES // PAGE_BYTES
MAX_RESIDENT = 61


def parse_page(key):
    if not isinstance(key, str):
        raise ValueError("page ID must be a string")
    try:
        page = int(key, 16)
    except ValueError as exc:
        raise ValueError("invalid hex page ID") from exc
    if not 0 <= page < PAGE_COUNT:
        raise ValueError("page outside merged 16 MiB ROM")
    return page


def score_profiles(document):
    if (document.get("schema") != 1 or document.get("rom_bytes") != ROM_BYTES
            or document.get("page_bytes") != PAGE_BYTES
            or document.get("metric") != "physical_miss_requests"):
        raise ValueError("expected B3 physical 4 KiB miss profile for a 16 MiB ROM")
    scenes = document.get("scenes")
    if not isinstance(scenes, list) or len(scenes) < 2:
        raise ValueError("need multiple independently measured scenes")
    scores, seen = {}, set()
    for scene in scenes:
        name = scene.get("name")
        if not isinstance(name, str) or not name.strip() or name in seen:
            raise ValueError("scene names must be unique and nonempty")
        seen.add(name)
        if scene.get("saturated") is not False:
            raise ValueError("saturated or unqualified counters cannot rank residency")
        raw = scene.get("counts")
        if not isinstance(raw, dict):
            raise ValueError("counts must be an object of numeric physical misses")
        counts = {}
        for key, count in raw.items():
            page = parse_page(key)
            if page in counts:
                raise ValueError("duplicate normalized page ID")
            if type(count) is not int or count < 0:
                raise ValueError("miss count must be a nonnegative integer")
            counts[page] = count
        total = sum(counts.values())
        if not total:
            # A zero-miss scene is legitimate; it must not invent page weights.
            continue
        for page, count in counts.items():
            if count:
                scores[page] = scores.get(page, Fraction(0)) + Fraction(count, total)
    if not scores:
        raise ValueError("no observed physical miss requests")
    return scores


def choose_pages(boot_scores, measured_scores, limit=MAX_RESIDENT, keep_boot=16):
    if not 1 <= limit <= MAX_RESIDENT or not 0 <= keep_boot <= limit:
        raise ValueError("invalid resident/boot budget")
    boot = sorted(boot_scores, key=lambda p: (-boot_scores[p], p))
    measured = sorted(measured_scores, key=lambda p: (-measured_scores[p], p))
    out, seen = [], set()
    for page in boot[:keep_boot] + measured + boot:
        if type(page) is not int or not 0 <= page < PAGE_COUNT:
            raise ValueError("resident page outside merged image")
        if page not in seen:
            out.append(page)
            seen.add(page)
        if len(out) == limit:
            break
    if len(out) != limit:
        raise ValueError("insufficient unique boot/profile pages")
    return sorted(out)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--profile", type=Path, required=True)
    ap.add_argument("--original-boot-list", type=Path, required=True,
                    help="original-game resident62.txt; remapped before ranking")
    ap.add_argument("--out", type=Path, required=True,
                    help="new private output; existing files are never overwritten")
    ap.add_argument("--keep-boot", type=int, default=16)
    ap.add_argument("--limit", type=int, default=MAX_RESIDENT)
    args = ap.parse_args(argv)
    repo = Path(__file__).resolve().parents[2]
    if args.out.resolve().is_relative_to(repo):
        ap.error("write the candidate outside the source checkout")
    try:
        measured = score_profiles(json.loads(args.profile.read_text()))
        _, boot = remap(pages(args.original_boot_list), MAX_RESIDENT,
                        drop_last=(0x7d9,))
        selected = choose_pages(boot, measured, args.limit, args.keep_boot)
        with args.out.open("x", encoding="ascii") as f:
            f.write("# B3 private measured candidate; page IDs only\n")
            for i in range(0, len(selected), 16):
                f.write(" ".join("%03x" % p for p in selected[i:i+16]) + "\n")
    except (OSError, ValueError) as exc:
        ap.error(str(exc))
    print("B3 candidate: %d unique pages (%d observed in measured scenes), not a verified performance result" %
          (len(selected), sum(p in measured for p in selected)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
