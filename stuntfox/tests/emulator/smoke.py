#!/usr/bin/env python3
"""Portable mGBA smoke test for a freshly built Stunt Fox GBA ROM.

Requires MGBA_CORE and the ELF produced with this ROM. Uses only real joypad
input and read-only memory inspection: no teleports, debug commands or states.
It is a short integration gate, not a campaign or hardware certification.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import struct
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "payback-mod/harness"))
from retro import Emu  # noqa: E402


def symbols(path):
    nm = shutil.which("llvm-nm") or shutil.which("nm")
    if not nm:
        raise RuntimeError("llvm-nm or nm is required to inspect the matching ELF")
    result = {}
    for line in subprocess.check_output([nm, "-S", "--defined-only", str(path)], text=True).splitlines():
        fields = line.split()
        if len(fields) == 3 and fields[1].upper() == "A":
            # GNU nm omits the size of linker-defined blob addresses; LLVM
            # prints zero. Both identify an address, never a sized RAM object.
            fields = [fields[0], "0", fields[1], fields[2]]
        if len(fields) == 4:
            address, size, kind, name = fields
            if name in result:
                result[name] = None  # ambiguous private symbols must not be guessed
            else:
                result[name] = (int(address, 16), int(size, 16))
    return result


class Smoke:
    def __init__(self, emu, syms, out):
        self.e, self.syms, self.out, self.checks = emu, syms, out, []

    def address(self, name, size=None):
        item = self.syms.get(name)
        if not item or (size is not None and item[1] != size):
            raise RuntimeError(f"ELF lacks an unambiguous {name} with the expected size")
        return item[0]

    def check(self, label, passed, **detail):
        self.checks.append({"name": label, "passed": bool(passed), **detail})
        print(f"{'PASS' if passed else 'FAIL'}  {label} {json.dumps(detail)}", flush=True)

    def shot(self, name):
        self.e.shot(self.out / f"{name}.png")

    def tap(self, key, after=60):
        self.e.press(key, hold=12, after=after)

    def vector(self, name):
        return struct.unpack("<3i", self.e.read(self.address(name), 12))

    def scalar(self, name):
        address = self.address(name)
        size = self.syms[name][1]
        if size not in (1, 2, 4):
            raise RuntimeError(f"unexpected scalar width for {name}: {size}")
        # Clang can narrow the private two-value vehicle enum to one byte.
        return int.from_bytes(self.e.read(address, size), "little")

    def frame(self):
        raw = self.e.read(self.address("s2f", 44), 44)
        return {"pos": struct.unpack_from("<3i", raw), "mode": raw[18],
                "docked": raw[19], "paused": raw[20], "map": raw[21],
                "story": raw[23], "airborne": raw[24],
                "ticks": struct.unpack_from("<I", raw, 32)[0],
                "clock": struct.unpack_from("<I", raw, 36)[0]}

    def merged(self):
        e = self.e
        e.run(400)
        self.tap("A", 1500)
        self.shot("title")
        self.tap("UP", 40)
        self.tap("A")
        pos, size = self.syms["pos"]
        initial = e.read(pos, size)
        self.tap("RIGHT", 30)
        changed = e.read(pos, size)
        self.shot("settings")
        self.tap("B")
        self.tap("A")
        reopened = e.read(pos, size)
        self.check("settings change and reopen", changed != initial and reopened == changed)
        self.tap("A")  # restore this line's default before starting the game
        self.tap("B")
        self.tap("DOWN", 40)
        self.tap("A", 100)
        for _ in range(11):
            self.tap("A", 80)
        e.run(400)
        start = self.frame()
        self.check("cold boot into story", start["mode"] == 0 and start["story"] == 1
                   and start["map"] == 0 and start["clock"] > 0, state=start)
        self.shot("city")
        e.run(180, ["UP"])
        walked = self.frame()
        moved = sum(abs(walked["pos"][i] - start["pos"][i]) for i in (0, 2))
        self.check("walk on foot", walked["mode"] == 0 and moved > 64, state=walked)
        e.run(300, ["SELECT"])
        e.run(300)
        boarded = self.frame()
        self.check("summon and board Arwing", boarded["mode"] == 2 and not boarded["docked"], state=boarded)
        self.shot("arwing")
        e.run(300, ["A"])
        flying = self.frame()
        self.check("take off and climb", flying["mode"] == 2 and flying["airborne"]
                   and flying["pos"][1] > boarded["pos"][1] + 500, state=flying)
        self.shot("flight")
        self.tap("START")
        pause = self.frame()
        e.run(90)
        self.check("pause holds game clock", pause["paused"] == 1
                   and self.frame()["clock"] == pause["clock"], state=pause)
        self.shot("pause")
        self.tap("A", 120)
        self.check("resume advances game clock", self.frame()["clock"] > pause["clock"])
        e.run(90, ["SELECT"])
        e.run(700)
        recovered = self.frame()
        bail = e.read(self.address("bail", 1), 1)[0]
        self.check("air bail-out recovers on foot", recovered["mode"] == 0 and bail == 0, state=recovered)
        self.shot("recovered")
        e.run(120, ["UP"])
        after = self.frame()
        moved = sum(abs(after["pos"][i] - recovered["pos"][i]) for i in (0, 2))
        self.check("walk after recovery", after["mode"] == 0 and moved > 64, state=after)

    def standalone(self):
        e = self.e
        e.run(240)
        start = self.vector("car")
        self.check("standalone boots in car", self.scalar("vehicle") == 0
                   and e.u32(self.address("frame_count", 4)) > 100)
        self.shot("start")
        e.run(300, ["A"])
        driven = self.vector("car")
        self.check("car accelerates", abs(driven[0] - start[0]) + abs(driven[2] - start[2]) > 256000,
                   start=start, end=driven)
        self.shot("driving")
        self.tap("START", 120)
        reset = self.vector("car")
        self.check("retry returns to start", abs(reset[0] // 256 - 43 * 1024) < 256
                   and abs(reset[2] // 256 - 37376) < 256, position=reset)
        self.tap("SELECT", 120)
        boarded = self.vector("ship")
        self.check("switch to Arwing", self.scalar("vehicle") == 1)
        e.run(300, ["A"])
        flown = self.vector("ship")
        self.check("Arwing takes off", self.scalar("vehicle") == 1 and flown[1] > boarded[1] + 500 * 256,
                   start=boarded, end=flown)
        self.shot("flight")
        self.tap("SELECT", 180)
        self.check("return to car", self.scalar("vehicle") == 0)
        self.tap("START", 180)
        counter = self.address("prof", 32) + 3 * 4
        before = e.u32(counter)
        e.run(120)
        rendered = (e.u32(counter) - before) & 0xffffffff
        fps = e.r32(self.address("game_fps", 4))
        self.check("renderer keeps updating", rendered > 0 and 1 <= fps <= 60,
                   new_rendered_frames=rendered, reported_fps_in_final_scene=fps)
        self.shot("return")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("rom", type=Path)
    parser.add_argument("--elf", required=True, type=Path)
    parser.add_argument("--mode", required=True, choices=("merge", "standalone"))
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    report = {"schema_version": 1, "mode": args.mode,
              "rom_sha256": hashlib.sha256(args.rom.read_bytes()).hexdigest(),
              "elf_sha256": hashlib.sha256(args.elf.read_bytes()).hexdigest(),
              "method": "mGBA libretro, cold boot, real buttons and read-only RAM inspection"}
    with Emu("gba", args.rom) as emu:
        smoke = Smoke(emu, symbols(args.elf), args.out)
        try:
            (smoke.merged if args.mode == "merge" else smoke.standalone)()
        except Exception as exc:
            smoke.check("test completed", False, error=str(exc))
        report["checks"] = smoke.checks
        report["video_frames"] = emu.frames
        report["passed"] = bool(smoke.checks) and all(c["passed"] for c in smoke.checks)
    (args.out / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
