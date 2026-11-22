#!/usr/bin/env python3
"""Space-walk integration using real station menus and physical objective checks.

The fixture shortens travel: it sets the docking approach, grants the missing
600-credit jet-pack budget, and positions the walker outside each beacon or
above the moon post. It never writes assignment state, completion receipts,
contact flags, rewards or boarding flags. Controls perform purchases, launch,
beacon approaches, ship recall, cancellation and saving. This is not a natural
end-to-end campaign playthrough. Native reload uses a separate OS process.
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

from campaign_save import Campaign, forbid_savestates
from smoke import Emu, symbols


class Eva(Campaign):
    def station(self):
        raw = self.e.read(self.address("stw"), 52)
        return {"x": struct.unpack_from("<h", raw)[0],
                "z": struct.unpack_from("<h", raw, 2)[0],
                "room": raw[16], "term": raw[22], "cursor": raw[23],
                "confirm": raw[26]}

    def receipts(self):
        return self.e.read(self.address("cp_prog", 260) + 249, 1)[0]

    def assignment(self):
        return self.scalar("obj_n"), self.scalar("obj_s")

    def active(self):
        return self.e.read(self.address("swk") + 54, 1)[0]

    def check_markers(self):
        # The original HUD font had no '*' glyph: valid saved receipts were
        # invisible. Check actual captured pixels, not just the receipt bits.
        visible = []
        for row in range(3):
            y = 36 + row * 14
            colors = {self.e.frame.getpixel((x, yy))
                      for x in range(111, 119) for yy in range(y, y + 8)}
            visible.append(len(colors) > 1)
        self.require("all three first-clear stars are visibly drawn", all(visible), visible=visible)

    def inspect_save(self):
        self.boot()
        self.require("earned completion save loads on final ROM", self.receipts() == 7
                     and self.scalar("credits") == 1000 and self.scalar("sw_pack") == 1)
        self.dock()
        self.board()
        self.check_markers()
        self.shot("all-walks-cleared")
        return {"credits": self.scalar("credits"), "receipts": self.receipts(), "pack": self.scalar("sw_pack")}

    def board(self):
        self.tap("B")  # hangar -> hub
        self.require("B enters station hub", self.station()["room"] == 1)
        self.tap("L")
        for _ in range(5):
            self.tap("DOWN", 24)
        self.shot("quick-menu")
        self.tap("A")
        self.require("quick menu opens SPACE WALKS", self.station()["term"] == 13)

    def hangar(self):
        if self.station()["term"]:
            self.tap("B")
        if self.station()["room"] != 1:
            self.tap("B")
        if self.station()["room"] == 1:
            self.tap("B")
        self.require("back controls return to hangar", self.station()["room"] == 0)
        self.e.run(120)  # allow the station's deliberate door cooldown

    def move(self, axis, target, *, room=None):
        keys = ("RIGHT", "LEFT") if axis == "x" else ("UP", "DOWN")
        for _ in range(150):
            state = self.station()
            if room is not None and state["room"] == room:
                self.e.run(60)
                return
            delta = target - state[axis]
            if abs(delta) < 45 and room is None:
                self.e.run(30)
                return
            self.e.run(3, [keys[delta < 0]])
        raise AssertionError(f"station walk did not reach {axis}={target}: {self.station()}")

    def uses(self, room):
        base = self.address("st_blob") - 0x08000000
        data = self.e.romdata[base:]
        off_room = struct.unpack_from("<I", data, 16)[0]
        record = off_room + room * 48
        count = data[record + 3]
        offset = struct.unpack_from("<I", data, record + 28)[0]
        return [dict(zip(("x", "z", "sx", "sz", "r4", "kind", "arg", "flags", "ly", "label"),
                         struct.unpack_from("<4h4BhH", data, offset + 16 * i)))
                for i in range(count)]

    def workshop(self):
        self.tap("B")
        self.require("hangar opens hub before workshop walk", self.station()["room"] == 1)
        door = next(u for u in self.uses(1) if u["kind"] == 1 and u["arg"] == 3)
        self.move("x", door["x"])
        self.move("z", door["z"], room=3)
        console = next(u for u in self.uses(3) if u["kind"] == 3 and u["arg"] == 4)
        self.move("x", console["x"])
        self.tap("A")
        self.require("walk to workshop opens upgrades", self.station()["term"] == 4)
        for _ in range(5):
            self.tap("DOWN", 24)
        self.shot("workshop-jet-pack")
        before = self.scalar("credits")
        self.tap("A")
        self.require("jet-pack purchase asks before spending", not self.scalar("sw_pack")
                     and self.scalar("credits") == before and self.station()["confirm"] == 6)
        self.tap("A")
        self.require("workshop fits the jet pack for 900 credits", self.scalar("sw_pack") == 1
                     and self.scalar("credits") == before - 900)
        self.shot("workshop-pack-fitted")
        self.hangar()

    def take(self, job):
        for _ in range(job - 1):
            self.tap("DOWN", 24)
        self.shot(f"assignment-{job}-brief")
        self.tap("A")
        for _ in range(40):
            self.e.run(30)
            if not self.frame()["docked"] and self.scalar("sg_state") == 0:
                break
        self.require(f"board accepts assignment {job} and launches", self.assignment() == (job, 0)
                     and not self.frame()["docked"] and self.frame()["mode"] == 2,
                     assignment=self.assignment(), frame=self.frame())

    def bail(self):
        self.mailbox(83, 3750, "Shorten ascent to 60,000 units before a real SELECT bail-out.")
        self.e.run(90, ["SELECT"])
        self.e.run(30)
        self.require("real SELECT starts the space walk", bool(self.active()))

    def place_walker(self, point, purpose):
        address = self.address("swk")
        words = [*(value * 256 for value in point), 0, 0, 0,
                 0, 0, 16384, 0, 16384, 0]
        self.setup.append({"type": "walker travel pose", "point": point, "purpose": purpose,
                           "writes": "position, velocity and facing only; no contact or objective flags"})
        for i, value in enumerate(words):
            self.e.write32(address + 4 * i, value & 0xffffffff)

    def beacon(self, index, expected):
        offsets = [(-5200, 800, -3000), (3800, 2400, -5200), (6200, -1200, 2400)]
        station = self.vector("station_pos")
        moon = [station[0] - 17000, station[1] + 2500, station[2] + 13000]
        point = [moon[i] + offsets[index][i] for i in range(3)]
        point[2] -= 1800
        self.place_walker(point, "Start 1,800 units short of a 900-unit beacon; UP must reach it.")
        self.e.run(2)
        before = self.assignment()
        self.require(f"beacon {index} fixture starts outside contact", before != expected)
        for _ in range(70):
            self.e.run(20, ["UP"])
            if self.assignment() == expected:
                break
        self.require(f"real jet-pack movement reaches beacon {index}", self.assignment() == expected,
                     assignment=self.assignment(), before=before, position=self.frame()["pos"])
        self.e.run(90, ["L"])

    def recall(self):
        for _ in range(80):
            self.e.run(30, ["SELECT"])
            if not self.active() and self.frame()["mode"] == 2:
                break
        self.e.run(30)
        self.require("real SELECT recalls and boards the Arwing", not self.active()
                     and self.frame()["mode"] == 2, frame=self.frame())

    def redock(self):
        if self.active():
            self.recall()
        ship = self.address("ship")
        sx, sy, sz = self.vector("station_pos")
        pose = [(sx + 3000) * 256, (sy - 140) * 256, (sz + 9000) * 256,
                0, 0, -90 * 256, -16384, 0, 0, 0, 16384, 0, 0, 0, -16384]
        self.setup.append({"type": "ship docking pose", "purpose": "Shorten return travel; SELECT invokes real docking."})
        for i, value in enumerate(pose):
            self.e.write32(ship + i * 4, value & 0xffffffff)
        self.e.run(20, ["A"])
        self.e.run(40, ["SELECT"])
        for _ in range(40):
            self.e.run(30)
            if self.scalar("sg_state") == 2:
                break
        self.e.run(60)
        self.require("return docks through flight controls", self.frame()["docked"]
                     and self.scalar("sg_state") == 2)

    def run_jobs(self):
        self.boot()
        self.dock()
        self.board()
        self.tap("A")
        self.require("board requires a campaign", self.assignment() == (0, 0)
                     and self.frame()["docked"] and not self.prog()["flags"] & 1)
        self.shot("campaign-required")
        self.hangar()
        self.tap("L")
        self.e.press("A", hold=12, after=0)
        self.wait_save()
        self.e.run(60)
        self.board()
        self.tap("A")
        self.require("board requires purchased jet pack", self.assignment() == (0, 0)
                     and self.frame()["docked"] and not self.scalar("sw_pack"))
        self.shot("jet-pack-required")
        self.tap("LEFT")
        self.require("left opens the Nav map", self.station()["term"] == 6)
        self.tap("RIGHT")
        self.require("right returns to space walks", self.station()["term"] == 13)
        self.tap("B")
        self.require("Nav board back returns to the map", self.station()["term"] == 6)
        self.hangar()
        self.mailbox(28, 600, "Add 600 to the initial 300 credits to test a paid workshop jet pack.")
        self.workshop()

        self.board()
        self.take(1)
        self.bail()
        before = self.scalar("credits")
        self.beacon(0, (0, 0))
        self.require("first beacon patrol pays 150 and records completion", self.scalar("credits") == before + 150
                     and self.receipts() == 1)
        self.shot("beacon-patrol-complete")
        self.redock()
        self.board()
        self.shot("first-clear-board")
        self.take(1)
        self.bail()
        before = self.scalar("credits")
        self.beacon(0, (0, 0))
        self.require("replay pays 50 without a second first-clear bonus", self.scalar("credits") == before + 50
                     and self.receipts() == 1)
        self.redock()

        self.board()
        self.take(2)
        self.bail()
        before = self.scalar("credits")
        post = self.vector("post_at")
        self.place_walker(post, "Start above the moon post; the physics must land the walker.")
        self.require("moon fixture is not already complete", self.assignment() == (2, 0))
        for _ in range(60):
            self.e.run(20)
            if self.assignment() == (0, 0):
                break
        self.require("physical moon landing pays 300 and records completion", self.assignment() == (0, 0)
                     and self.scalar("credits") == before + 300 and self.receipts() == 3,
                     assignment=self.assignment(), credits=self.scalar("credits"))
        self.shot("moon-survey-complete")
        self.redock()

        self.board()
        self.take(3)
        self.redock()
        self.board()
        self.tap("DOWN")
        self.tap("A")
        self.require("selecting another walk preserves the active relay", self.assignment() == (3, 0)
                     and self.frame()["docked"])
        self.tap("DOWN")
        self.tap("DOWN")
        before = self.scalar("credits")
        self.tap("A")
        self.require("cancellation asks for confirmation", self.assignment() == (3, 0)
                     and self.station()["confirm"] == 1)
        self.tap("A")
        self.require("confirmed cancellation pays nothing", self.assignment() == (0, 0)
                     and self.scalar("credits") == before and self.receipts() == 3)
        self.hangar()

        self.board()
        self.take(3)
        self.bail()
        self.recall()
        self.require("boarding before beacon visits cannot complete relay", self.assignment() == (3, 0)
                     and self.scalar("credits") == before)
        self.bail()
        self.beacon(1, (3, 1))
        self.beacon(2, (3, 2))
        self.require("both relay beacons still require safe return", self.scalar("credits") == before
                     and self.receipts() == 3)
        self.shot("relay-awaiting-return")
        self.recall()
        self.require("safe reboarding pays relay once", self.assignment() == (0, 0)
                     and self.scalar("credits") == before + 500 and self.receipts() == 7)
        self.redock()
        self.board()
        self.check_markers()
        self.shot("all-walks-cleared")
        self.hangar()
        self.save_now()
        return {"credits": self.scalar("credits"), "receipts": self.receipts(), "pack": self.scalar("sw_pack")}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("rom", type=Path)
    parser.add_argument("--elf", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--inspect-save", type=Path,
                        help="cold-boot a native save earned by a previous full EVA run and inspect its board")
    args = parser.parse_args()
    if args.out.exists() and any(args.out.iterdir()):
        parser.error("--out must be new or empty")
    args.out.mkdir(parents=True, exist_ok=True)
    report = {"schema_version": 1, "rom_sha256": hashlib.sha256(args.rom.read_bytes()).hexdigest(),
              "elf_sha256": hashlib.sha256(args.elf.read_bytes()).hexdigest(),
              "method": __doc__, "full_campaign_playthrough": False}
    save = args.out / "native.srm"
    if args.inspect_save:
        shutil.copyfile(args.inspect_save, save)
        report["method"] = "Cold boot a previously earned native EVA save, use real station controls, inspect saved rewards and visible first-clear stars. Docking approach is positioned."
        report["source_save_sha256"] = hashlib.sha256(save.read_bytes()).hexdigest()
    with Emu("gba", args.rom, save_path=save) as emu:
        emu.save_state = emu.load_state = forbid_savestates
        game = Eva(emu, symbols(args.elf), args.out)
        try:
            report["final"] = game.inspect_save() if args.inspect_save else game.run_jobs()
        except Exception as exc:
            game.check("assignment run completes", False, error=str(exc))
            game.shot("failure")
        report["setup"], report["checks"] = game.setup, game.checks
        report["video_frames"] = emu.frames
    if "final" in report and not args.inspect_save:
        reload_dir = args.out / "reload"
        reload_dir.mkdir()
        reload_save = reload_dir / "native.srm"
        shutil.copy2(save, reload_save)
        result = reload_dir / "report.json"
        command = [sys.executable, str(Path(__file__).with_name("campaign_save.py")),
                   str(args.rom.resolve()), "--elf", str(args.elf.resolve()),
                   "--worker", "read", "--save", str(reload_save.resolve()), "--result", str(result.resolve())]
        run = subprocess.run(command, check=False)
        data = json.loads(result.read_text()) if result.exists() else {}
        raw = bytes.fromhex(data.get("final", {}).get("progress", {}).get("raw_hex", ""))
        live = data.get("final", {}).get("live", {})
        passed = (run.returncode == 0 and len(raw) == 260 and raw[249] == report["final"]["receipts"]
                  and live.get("credits") == report["final"]["credits"] and live.get("sw_pack") == 1)
        report["checks"].append({"name": "earned receipts, rewards and pack survive native cold boot", "passed": passed})
        report["native_reload"] = {"returncode": run.returncode, "passed": passed}
        print(f"{'PASS' if passed else 'FAIL'}  earned receipts, rewards and pack survive native cold boot", flush=True)
    report["passed"] = bool(report["checks"]) and all(item["passed"] for item in report["checks"])
    (args.out / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
