#!/usr/bin/env python3
"""Exercise the actual campaign ending with an explicitly instrumented fixture.

Cold-boots the supplied merged ROM. Existing debug commands seed earlier act
completion and advance the final mission; this is not an earned campaign
playthrough. The ending, back/continue controls and station movement use real
joypad input. No savestates or ROM modification are used.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct

from smoke import Emu, Smoke, symbols

PB_LEVEL_END = 0x02001E08
CP_END_NONE, CP_END_RETURN, CP_END_COMPLETE, CP_END_ACE, CP_END_STATION = range(5)


class Ending(Smoke):
    def __init__(self, *args):
        super().__init__(*args)
        self.setup = {}

    def debug(self, command, argument=0):
        address = self.address("s2_dbg", 16)
        seq = self.e.u32(address + 12)
        self.e.write16(address + 4, command)
        self.e.write16(address + 6, argument)
        self.e.write32(address, 0x42443253)
        for _ in range(120):
            self.e.run(1)
            if self.e.u32(address + 12) != seq:
                return self.e.r32(address + 8)
        raise RuntimeError(f"debug mailbox did not service {command}:{argument}")

    def cp(self, field):
        return self.debug(17, field)

    def level_end(self):
        return int.from_bytes(self.e.read(PB_LEVEL_END, 2), "little")

    def progress(self):
        raw = self.e.read(self.address("cp_prog", 260), 260)
        return {"unlocked": raw[8], "chapter": raw[9], "flags": raw[10],
                "ace": raw[11], "acts": list(raw[12:24]),
                "medals": list(raw[48:60]), "story": list(raw[104:112]),
                "eva_receipts": raw[249]}

    def final_mission(self):
        base = self.address("s2_blob") - 0x08000000
        blob = self.e.romdata[base:]
        magic, version, count = struct.unpack_from("<IHH", blob)
        if magic != 0x31433253 or version != 1:
            raise RuntimeError("matching ROM does not contain the expected mission blob")
        chapters_at, missions_at = struct.unpack_from("<II", blob, 16)
        chapters = []
        for c in range(count):
            rec = struct.unpack_from("<4B4H2BH", blob, chapters_at + 16 * c)
            chapters.append({"map": rec[0], "flags": rec[1], "acts": rec[2],
                             "first": rec[4], "count": rec[5]})
        finals = [c for c, ch in enumerate(chapters) if ch["flags"] & 4]
        if len(finals) != 1:
            raise RuntimeError("campaign must contain one final chapter")
        c = finals[0]
        ch = chapters[c]
        for m in range(ch["first"], ch["first"] + ch["count"]):
            rec = struct.unpack_from("<H4B4H2B4H", blob, missions_at + 24 * m)
            if rec[2] == 0 and rec[3] == ch["acts"]:
                return chapters, c, m, rec[-2]
        raise RuntimeError("final chapter has no final act")

    def wait_level(self, map_id, *, story_end=False, confirm_debrief=False, limit=2400):
        # Story debrief screens take SELECT once, then A; a held SELECT calls
        # the Arwing, and repeated SELECT can undo the end-screen selection.
        if story_end:
            self.e.press("SELECT", hold=4, after=60)
        for _ in range(limit // 60):
            f = self.frame()
            if f["map"] == map_id and self.level_end() == 0 and f["clock"] < 400:
                self.e.run(90)
                return True
            if story_end or confirm_debrief:
                self.e.press("A", hold=4, after=56)
            else:
                self.e.run(60)
        return False

    def prepare(self):
        e = self.e
        e.run(400)
        self.tap("A", 1500)
        self.tap("A", 100)
        for _ in range(11):
            self.tap("A", 80)
        e.run(400)
        f = self.frame()
        self.check("cold boot into story", f["mode"] == 0 and f["story"] == 1
                   and f["map"] == 0 and f["clock"] > 0, state=f)
        if f["map"] != 0 or not f["story"]:
            raise RuntimeError("cold-boot story fixture failed")
        chapters, c, mission, pay = self.final_mission()
        self.setup = {"method": "existing debug mailbox plus one forced story-level end",
                      "earned_playthrough": False, "final_chapter": c,
                      "final_map": chapters[c]["map"], "final_mission": mission,
                      "normal_final_mission_pay": pay, "seeded_act_masks": {}}
        self.debug(16, 0)
        self.debug(24, c)
        for i, ch in enumerate(chapters[:c + 1]):
            mask = (1 << ch["acts"]) - 1
            if i == c:
                mask &= ~(1 << (ch["acts"] - 1))
            self.debug(18, (i << 8) | mask)
            self.setup["seeded_act_masks"][str(i)] = mask
        if self.debug(19, c) != 2:
            raise RuntimeError("initial story fixture did not book travel")
        e.write16(PB_LEVEL_END, 3)
        arrived = self.wait_level(chapters[c]["map"], story_end=True)
        self.check("fixture loads real final map", arrived and self.cp(1) == c,
                   state=self.frame(), chapter=self.cp(1))
        if not arrived:
            self.shot("fixture-travel-failed")
            raise RuntimeError("late-game fixture did not reach final map")
        # The prior acts include the orbital drop, so this level starts on foot.
        e.run(300, ["SELECT"])
        e.run(300)
        e.run(120, ["A"])
        f = self.frame()
        self.check("fixture boards and flies real Arwing", f["mode"] == 2
                   and not f["docked"] and f["airborne"], state=f)
        if f["mode"] != 2:
            raise RuntimeError("final mission fixture has no controlled Arwing")
        self.shot("final-map-flight")
        return chapters, c, mission, pay

    def run_ending(self, chapters, chapter, mission, pay):
        e = self.e
        before = self.progress()
        credits = self.cp(6)
        self.debug(1, mission)
        # Force only the mission's objective predicates. Its real SET, FINISH,
        # payment, campaign event, docking and HUD code still execute normally.
        forced = 0
        for _ in range(30):
            if self.cp(18) >= CP_END_COMPLETE:
                break
            self.debug(2)
            forced += 1
            e.run(10)
        self.setup["forced_final_objective_steps"] = forced
        after = self.progress()
        final_mask = (1 << chapters[chapter]["acts"]) - 1
        self.check("final act commits finale and Ace mode", after["acts"][chapter] == final_mask
                   and after["story"][0] & 2 and after["ace"] == 1, progress=after)
        self.check("normal final-act payment once", self.cp(6) == credits + pay,
                   before=credits, after=self.cp(6), expected_pay=pay)
        self.check("prior progress is retained", after["acts"][:chapter] == before["acts"][:chapter]
                   and after["medals"] == before["medals"]
                   and after["eva_receipts"] == before["eva_receipts"]
                   and after["unlocked"] == chapter)
        e.run(90)
        f = self.frame()
        self.check("completion docks without ending the level", self.cp(18) == CP_END_COMPLETE
                   and f["docked"] and self.level_end() == 0 and self.cp(19), state=f)
        self.shot("ending-1-complete")
        if self.cp(18) != CP_END_COMPLETE:
            raise RuntimeError("completion card did not appear")

        e.run(180)
        self.check("ending waits for the player", self.cp(18) == CP_END_COMPLETE)
        e.run(180, ["A"])
        self.check("held A advances only one card", self.cp(18) == CP_END_ACE)
        e.run(60)
        self.shot("ending-2-ace")
        self.tap("B", 90)
        self.check("B revisits previous card", self.cp(18) == CP_END_COMPLETE)
        self.tap("START", 60)
        paused = self.frame()
        e.run(90)
        self.check("ending can be paused", paused["paused"] == 1
                   and self.frame()["clock"] == paused["clock"]
                   and self.cp(18) == CP_END_COMPLETE)
        self.shot("ending-paused")
        self.tap("A", 90)
        self.check("resume does not dismiss ending card", not self.frame()["paused"]
                   and self.cp(18) == CP_END_COMPLETE)
        self.tap("A", 90)
        self.tap("A", 90)
        self.check("player reaches final card", self.cp(18) == CP_END_STATION)
        self.shot("ending-3-home")
        self.tap("A", 90)
        stw = self.address("stw")
        room = e.read(stw + 16, 1)[0]
        self.check("final A enters Fox Station hub", self.cp(18) == CP_END_NONE
                   and room == 1 and self.frame()["docked"], room=room)
        self.shot("postgame-station")
        start = struct.unpack("<hh", e.read(stw, 4))
        e.run(60, ["UP"])
        end = struct.unpack("<hh", e.read(stw, 4))
        self.check("station controls work after ending", start != end, start=start, end=end)
        e.run(180)
        self.check("postgame remains open", self.cp(19) == 1 and self.cp(18) == CP_END_NONE
                   and self.level_end() == 0 and self.cp(6) == credits + pay)
        self.debug(25, mission)  # duplicate completion event; does not invoke payment
        e.run(60)
        self.check("duplicate event cannot restart ending", self.cp(18) == CP_END_NONE
                   and self.level_end() == 0 and self.cp(6) == credits + pay)

        # Route coverage is instrumented; the player-facing cards and station
        # controls above are not. Both destination loads use normal game code.
        go = self.debug(19, 0)
        arrived = self.wait_level(chapters[0]["map"])
        self.check("postgame travels to completed story city", go == 1 and arrived
                   and self.cp(1) == 0 and self.cp(19) == 1 and self.cp(18) == CP_END_NONE,
                   state=self.frame())
        self.shot("postgame-story-city")
        go = self.debug(19, chapter)
        arrived = self.wait_level(chapters[chapter]["map"], confirm_debrief=True)
        self.check("completed story city allows immediate return", go == 1 and arrived
                   and self.cp(1) == chapter and self.cp(19) == 1 and self.cp(18) == CP_END_NONE,
                   state=self.frame())
        self.shot("postgame-final-city")
        self.check("postgame travel preserves completion", self.progress() == after
                   and self.cp(6) == credits + pay)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("rom", type=Path)
    parser.add_argument("--elf", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--prepare-only", action="store_true",
                        help="validate only the late-game fixture (also works on the pre-ending baseline)")
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    report = {"schema_version": 1,
              "rom_sha256": hashlib.sha256(args.rom.read_bytes()).hexdigest(),
              "elf_sha256": hashlib.sha256(args.elf.read_bytes()).hexdigest(),
              "method": "mGBA cold boot, instrumented late-game setup, real ending/station buttons",
              "full_campaign_playthrough": False, "prepare_only": args.prepare_only}
    with Emu("gba", args.rom) as emu:
        test = Ending(emu, symbols(args.elf), args.out)
        try:
            fixture = test.prepare()
            if not args.prepare_only:
                test.run_ending(*fixture)
        except Exception as exc:
            test.check("test completed", False, error=str(exc))
        report.update(setup=test.setup, checks=test.checks, video_frames=emu.frames)
        report["passed"] = bool(test.checks) and all(c["passed"] for c in test.checks)
    (args.out / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
