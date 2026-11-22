#!/usr/bin/env python3
"""Campaign EEPROM acceptance through fresh mGBA processes, never savestates.

Menus start/save the campaign, buy equipment and change options. One documented
ship-pose fixture shortens docking. The advanced-state worker grants 900 credits
and seeds chapter/act progress through the game's debug mailbox; it then buys the
jet pack and saves through real menus. These setup operations are reported.
"""
from __future__ import annotations

import argparse
import binascii
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys

from smoke import Emu, Smoke, symbols

PROG_SIZE = 260
SLOT_BLOCKS = (72, 112)
EEP_CONFIG = 0x03000D64
EEP_64K = 0x087D92E4


def checksum(data):
    return hashlib.sha256(data).hexdigest()


def crc(data):
    return binascii.crc_hqx(data, 0xFFFF)


def progress(data):
    if len(data) != PROG_SIZE:
        raise ValueError("unexpected campaign image size")
    return {
        "sha256": checksum(data), "raw_hex": data.hex(),
        "valid": data[:4] == b"SFP2" and struct.unpack_from("<H", data, 4)[0] == 1
        and struct.unpack_from("<H", data, 6)[0] == crc(data[8:]),
        "unlocked": data[8], "chapter": data[9], "flags": data[10], "ace": data[11],
        "acts": list(data[12:24]), "credits": struct.unpack_from("<i", data, 72)[0],
        "laser": data[80], "engine": data[81], "rack": data[82], "shield": data[83],
        "missiles": data[84], "paint": data[85], "jobs": data[86], "controls": data[87],
        "extension": data[88:104].hex(), "eva_receipts": data[249],
    }


def native_slots(data):
    # mGBA's native EEPROM byte order reverses each eight-byte serial block.
    logical = b"".join(data[i:i + 8][::-1] for i in range(0, len(data), 8))
    result = []
    for slot, block in enumerate(SLOT_BLOCKS):
        header = logical[block * 8:(block + 1) * 8]
        item = {"slot": slot, "valid": False}
        if len(header) == 8:
            header_check = 0x5A
            for value in header[:7]:
                header_check ^= value
            count = header[1]
            payload = logical[(block + 1) * 8:(block + 1 + count) * 8]
            item["sequence"] = int.from_bytes(header[2:4], "little")
            item["valid"] = (header[0] == 0xA7 and count == 33
                             and header[7] == header_check and len(payload) == 264
                             and crc(payload) == int.from_bytes(header[4:6], "little"))
            if item["valid"]:
                item["progress"] = progress(payload[:PROG_SIZE])
                item["valid"] = item["progress"]["valid"]
        result.append(item)
    return result


def legacy_image(data):
    """A documented compatibility fixture: clear only the optional extension.

    Both game-level and slot-level checksums are recalculated. The resulting
    native EEPROM uses the original zero-spare SgProgress representation.
    """
    logical = bytearray(b"".join(data[i:i + 8][::-1] for i in range(0, len(data), 8)))
    for item in native_slots(data):
        if not item["valid"]:
            continue
        offset = SLOT_BLOCKS[item["slot"]] * 8
        payload = bytearray(logical[offset + 8:offset + 8 + 264])
        payload[88:104] = bytes(16)
        struct.pack_into("<H", payload, 6, crc(payload[8:PROG_SIZE]))
        logical[offset + 8:offset + 8 + 264] = payload
        struct.pack_into("<H", logical, offset + 4, crc(payload))
        check = 0x5A
        for value in logical[offset:offset + 7]:
            check ^= value
        logical[offset + 7] = check
    return b"".join(logical[i:i + 8][::-1] for i in range(0, len(logical), 8))


def forbid_savestates(*_args, **_kwargs):
    raise RuntimeError("campaign save acceptance prohibits emulator savestates")


class Campaign(Smoke):
    def __init__(self, emu, syms, out):
        super().__init__(emu, syms, out)
        self.setup = []

    def require(self, name, passed, **detail):
        self.check(name, passed, **detail)
        if not passed:
            raise AssertionError(name)

    def live(self):
        names = ("credits", "laser_lv", "engine_lv", "rack_lv", "shield_lv", "missiles",
                 "paint", "jobs_done", "paints_got", "sw_pack", "sg_invert", "sg_autoaim",
                 "rag_on", "rag_fall", "rag_wacky", "rag_unlock")
        result = {name: self.scalar(name) for name in names}
        result["options"] = list(self.e.read(self.address("pos", 31), 31))
        result["applied_options"] = {name: self.scalar(name) for name in (
            "car_vmax_k", "car_accel_k", "ship_speed_k", "sg_shield_k", "cam_dflt",
            "opt_tex", "opt_planet", "car_boost_inf", "sg_inf_missiles", "sw_pack_k")}
        result["radio"] = self.e.read(self.address("radio", 20) + 17, 1)[0] & 0x7F
        return result

    def prog(self):
        return progress(self.e.read(self.address("cp_prog", PROG_SIZE), PROG_SIZE))

    def pick(self):
        sequence, slot, valid = struct.unpack("<HBB", self.e.read(self.address("spick", 4), 4))
        return {"sequence": sequence, "slot": slot, "valid": valid}

    def pending(self):
        data = self.e.read(self.address("sw", 8), 8)
        return {"sequence": int.from_bytes(data[:2], "little"), "slot": data[4],
                "block": data[5], "blocks": data[6], "busy": bool(data[7])}

    def snapshot(self, name):
        result = {"live": self.live(), "progress": self.prog(), "pick": self.pick(),
                  "pending": self.pending(), "frame": self.frame(),
                  "native_bytes": len(self.e.mem(0)), "native_sha256": checksum(self.e.mem(0))}
        self.shot(name)
        return result

    def boot(self):
        self.e.run(400)
        self.tap("A", 1500)
        self.tap("A", 100)
        for _ in range(11):
            self.tap("A", 80)
        self.e.run(400)
        frame = self.frame()
        self.require("cold boot reaches story gameplay", frame["map"] == 0 and frame["story"] == 1
                     and frame["mode"] == 0 and frame["clock"] > 0, state=frame)

    def dock(self):
        self.e.run(300, ["SELECT"])
        self.e.run(300)
        self.require("real Select input boards the Arwing", self.frame()["mode"] == 2)
        ship = self.address("ship")
        sx, sy, sz = self.vector("station_pos")
        pose = [(sx + 3000) * 256, (sy - 140) * 256, (sz + 9000) * 256,
                0, 0, -90 * 256, -16384, 0, 0, 0, 16384, 0, 0, 0, -16384]
        self.setup.append({"type": "ship docking pose", "address": hex(ship), "words": pose,
                           "purpose": "Shorten travel only; docking, shop, campaign and save use game input."})
        for i, value in enumerate(pose):
            self.e.write32(ship + 4 * i, value & 0xFFFFFFFF)
        self.e.run(20, ["A"])
        self.e.run(40, ["SELECT"])
        for _ in range(40):
            self.e.run(30)
            if self.scalar("sg_state") == 2:
                break
        self.e.run(60)
        self.require("game docking reaches the hangar", self.scalar("sg_state") == 2
                     and self.frame()["docked"] == 1)

    def wait_save(self, previous=None):
        for _ in range(600):
            pick = self.pick()
            if (pick["valid"] and not self.pending()["busy"]
                    and (previous is None or pick["sequence"] != previous)):
                slots = native_slots(self.e.mem(0))
                selected = slots[pick["slot"]]
                self.require("game commits a valid native campaign slot", selected["valid"]
                             and selected["sequence"] == pick["sequence"]
                             and selected["progress"]["raw_hex"] == self.prog()["raw_hex"], pick=pick)
                return
            self.e.run(1)
        raise AssertionError("campaign save did not commit within 600 video frames")

    def save_now(self):
        self.tap("L")
        self.tap("DOWN")
        self.tap("DOWN")
        before = self.pick()["sequence"]
        self.e.press("A", hold=12, after=0)
        self.wait_save(before)
        self.e.run(30)
        self.shot("save-now")
        self.tap("B")

    def mailbox(self, command, argument, purpose):
        address = self.address("s2_dbg", 16)
        before = self.e.u32(address + 12)
        self.setup.append({"type": "documented game debug mailbox", "command": command,
                           "argument": argument, "purpose": purpose})
        self.e.write16(address + 4, command)
        self.e.write16(address + 6, argument)
        self.e.write32(address, 0x42443253)
        for _ in range(80):
            self.e.run(1)
            if self.e.u32(address + 12) != before:
                return self.e.r32(address + 8)
        raise AssertionError("game did not consume the setup mailbox command")

    def settings_page(self):
        # From a freshly docked main menu, with JOB BOARD selected.
        for _ in range(3):
            self.tap("DOWN", 30)
        self.tap("A")
        for _ in range(5):
            self.tap("DOWN", 30)
        self.tap("A")

    def write(self):
        before = self.e.mem(0)
        self.require("no campaign writes before campaign start", not (self.prog()["flags"] & 1)
                     and all(value == 0xFF for value in before[512:]))
        (self.out / "payback-profile-512.srm").write_bytes(before[:512])
        self.dock()
        self.tap("L")
        self.e.press("A", hold=12, after=0)
        self.wait_save()
        self.require("Start Campaign proves the 8 KiB chip", self.prog()["flags"] & 1
                     and self.e.u32(EEP_CONFIG) == EEP_64K and len(self.e.mem(0)) == 8192)
        self.require("chip proof preserves Payback's first 512 bytes", self.e.mem(0)[:512] == before[:512])
        self.shot("campaign-started")
        # The game's own initial 300 credits pay for the larger rack.
        self.tap("DOWN")
        self.tap("A")
        for _ in range(4):
            self.tap("DOWN", 30)
        self.tap("A")
        self.tap("A")
        self.require("real shop purchase spends 300 credits and upgrades rack",
                     self.scalar("credits") == 0 and self.scalar("rack_lv") == 1
                     and self.scalar("missiles") == 6)
        self.shot("rack-purchased")
        self.tap("B")
        self.tap("DOWN")
        self.tap("A")
        self.tap("DOWN")
        self.tap("A")
        self.require("paint choice changes through the shop", self.scalar("paint") == 1)
        self.tap("DOWN")
        self.tap("A")
        self.tap("A")  # invert
        self.tap("DOWN")
        self.tap("A")  # autoaim
        for key in ("L", "L", "R", "R", "L", "R") * 2:
            self.tap(key, 30)
        self.tap("DOWN")
        self.tap("DOWN")
        self.tap("A")  # fall damage
        self.tap("DOWN")
        self.tap("A")  # radio
        self.tap("DOWN")
        self.tap("A")  # game settings
        initial = self.live()["options"]
        for i in range(31):
            self.tap("RIGHT" if initial[i] == 0 else "LEFT", 24)
            if i < 30:
                self.tap("DOWN", 24)
        changed = self.live()["options"]
        self.shot("settings-changed")
        self.require("all 31 setting choices change through real input",
                     all(a != b for a, b in zip(initial, changed)), before=initial, after=changed)
        self.tap("B")
        self.tap("B")
        self.save_now()
        self.require("campaign saves preserve original profile bytes", self.e.mem(0)[:512] == before[:512])

    def advance(self):
        self.dock()
        self.require("fixture grants only the jet-pack purchase budget",
                     self.mailbox(28, 900, "Fund a real jet-pack shop purchase; credits are test setup.") == 900)
        self.mailbox(24, 3, "Seed a later chapter unlock for persistence, not a claim of earned campaign completion.")
        self.mailbox(18, 3, "Seed two completed acts of chapter zero for persistence.")
        receipt = self.address("cp_prog", PROG_SIZE) + 249
        self.setup.append({"type": "campaign receipt fixture", "address": hex(receipt), "value": 3,
                           "purpose": "Seed two EVA reward receipts for persistence; not player-earned completion."})
        self.e.write8(receipt, 3)
        self.tap("DOWN")
        self.tap("A")
        for _ in range(5):
            self.tap("DOWN", 30)
        self.tap("A")
        self.tap("A")
        self.require("real jet-pack purchase spends its 900-credit budget",
                     self.scalar("sw_pack") == 1 and self.scalar("credits") == 0)
        self.shot("jet-pack-purchased")
        self.tap("B")
        self.save_now()

    def interrupt(self):
        self.dock()
        self.settings_page()
        before = self.live()["options"]
        self.e.press("RIGHT", hold=12, after=0)
        self.require("real setting change makes the next save different", self.live()["options"] != before)
        for _ in range(600):
            pending = self.pending()
            if pending["busy"] and 14 <= pending["block"] < pending["blocks"]:
                slots = native_slots(self.e.mem(0))
                self.require("power cut captures a partial slot with a good older slot",
                             sum(item["valid"] for item in slots) == 1, pending=pending)
                return
            self.e.run(1)
        raise AssertionError("did not capture an actual in-progress EEPROM write")

    def stop(self):
        self.dock()
        self.tap("L")
        for _ in range(5):
            self.tap("DOWN", 30)
        before = self.pick()["sequence"]
        self.e.press("A", hold=12, after=0)
        self.wait_save(before)
        self.require("Stop Campaign commits an inactive campaign", not (self.prog()["flags"] & 1))
        self.shot("campaign-stopped")

    def resume(self):
        self.require("cold boot leaves a stopped campaign inactive", not (self.prog()["flags"] & 1))
        self.dock()
        self.tap("L")
        self.shot("continue-campaign")
        before = self.pick()["sequence"]
        self.e.press("A", hold=12, after=0)
        self.wait_save(before)
        self.require("Continue Campaign reactivates the stored campaign", self.prog()["flags"] & 1)


def worker(args):
    args.result.parent.mkdir(parents=True, exist_ok=True)
    disk_before = args.save.read_bytes() if args.save.exists() else None
    result = {"pid": os.getpid(), "action": args.worker,
              "rom_sha256": checksum(args.rom.read_bytes()), "setup": []}
    with Emu("gba", args.rom, save_path=args.save) as emu:
        emu.save_state = emu.load_state = forbid_savestates
        game = Campaign(emu, symbols(args.elf), args.result.parent)
        try:
            game.boot()
            result["boot"] = game.snapshot("cold-boot")
            if args.worker != "read":
                getattr(game, args.worker)()
            result["final"] = game.snapshot("final")
            result["slots"] = native_slots(emu.mem(0))
            result["setup"] = game.setup
        except Exception as exc:
            game.check("worker completes", False, error=str(exc))
            result["error"] = str(exc)
        result["checks"] = game.checks
        result["video_frames"] = emu.frames
        result["loaded_native_bytes"] = emu.loaded_save_bytes
        result["passed"] = bool(game.checks) and all(c["passed"] for c in game.checks)
    disk_after = args.save.read_bytes() if args.save.exists() else None
    result["disk_bytes"] = len(disk_after) if disk_after is not None else 0
    result["disk_sha256"] = checksum(disk_after) if disk_after is not None else None
    result["disk_unchanged"] = disk_before == disk_after
    args.result.write_text(json.dumps(result, indent=2) + "\n")
    return 0 if result["passed"] else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("rom", type=Path)
    parser.add_argument("--elf", required=True, type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--worker", choices=("write", "read", "advance", "interrupt", "stop", "resume"), help=argparse.SUPPRESS)
    parser.add_argument("--save", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--result", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.worker:
        return worker(args)
    if args.out is None:
        parser.error("--out is required")
    if args.out.exists() and any(args.out.iterdir()):
        parser.error("--out must be new or empty; existing native saves are never overwritten")
    args.out.mkdir(parents=True, exist_ok=True)
    report = {
        "schema_version": 1, "rom_sha256": checksum(args.rom.read_bytes()),
        "elf_sha256": checksum(args.elf.read_bytes()),
        "method": "Native mGBA EEPROM memory kind 0; separate OS process per stage; no savestates.",
        "scope": "Merged Stunt Fox 8 KiB campaign EEPROM, equipment and game settings. Does not certify a physical 512-byte chip or full campaign playthrough.",
        "setup": "Ship pose shortens travel to the station. Only the advanced stage uses debug grants for 900 credits, chapter unlock 3 and act bits 3. Legacy format is a documented checksum-correct fixture.",
        "checks": [], "workers": {},
    }

    def check(name, passed, **detail):
        report["checks"].append({"name": name, "passed": bool(passed), **detail})
        print(f"{'PASS' if passed else 'FAIL'}  {name}", flush=True)

    def run(name, action, source=None):
        folder = args.out / name
        folder.mkdir()
        save = folder / "native.srm"
        if source is not None:
            shutil.copyfile(source, save)
        result = folder / "worker.json"
        command = [sys.executable, str(Path(__file__).resolve()), str(args.rom.resolve()),
                   "--elf", str(args.elf.resolve()), "--worker", action,
                   "--save", str(save.resolve()), "--result", str(result.resolve())]
        process = subprocess.run(command, capture_output=True, text=True, timeout=180)
        (folder / "worker.log").write_text(process.stdout + process.stderr)
        if result.exists():
            value = json.loads(result.read_text())
            report["workers"][name] = value
            for item in value["checks"]:
                report["checks"].append({**item, "name": name + ": " + item["name"]})
        if process.returncode or not result.exists():
            raise RuntimeError(f"{name} exited {process.returncode}; see {folder / 'worker.log'}")
        return value, save

    def cold_equal(name, expected, source):
        read, _ = run(name, "read", source)
        check(name + ": live equipment and every option survive cold boot",
              read["boot"]["live"] == expected["final"]["live"])
        check(name + ": campaign image survives cold boot",
              read["boot"]["progress"]["raw_hex"] == expected["final"]["progress"]["raw_hex"])
        check(name + ": cold reader preserves EEPROM bytes", read["disk_unchanged"])
        return read

    try:
        first, first_save = run("menu-write", "write")
        check("game writes exactly 8 KiB of native EEPROM", first["disk_bytes"] == 8192)
        cold_equal("menu-coldboot", first, first_save)
        advanced, advanced_save = run("advanced-write", "advance", first_save)
        check("advanced setup is saved through normal menus",
              advanced["final"]["progress"]["unlocked"] == 3
              and advanced["final"]["progress"]["acts"][0] == 3
              and advanced["final"]["progress"]["eva_receipts"] == 3
              and advanced["final"]["live"]["sw_pack"] == 1)
        cold_equal("advanced-coldboot", advanced, advanced_save)
        stopped, stopped_save = run("stopped-write", "stop", advanced_save)
        check("stopping retains the live purchases and options",
              stopped["final"]["live"] == advanced["final"]["live"])
        resumed, _ = run("stopped-coldboot-continue", "resume", stopped_save)
        check("stopped campaign is read before Continue without being restarted",
              resumed["boot"]["progress"]["raw_hex"] == stopped["final"]["progress"]["raw_hex"]
              and not resumed["boot"]["progress"]["flags"] & 1)
        check("Stop then cold Continue preserves purchases and every option",
              resumed["final"]["live"] == advanced["final"]["live"])
        check("Stop then cold Continue preserves the complete campaign image",
              resumed["final"]["progress"]["raw_hex"] == advanced["final"]["progress"]["raw_hex"])
        interrupted, partial_save = run("interrupted-write", "interrupt", advanced_save)
        recovered = cold_equal("interrupted-coldboot", advanced, partial_save)
        check("actual partial write falls back to the previous committed slot",
              recovered["boot"]["pick"] == advanced["final"]["pick"])
        legacy_path = args.out / "legacy-zero-extension.srm"
        legacy_path.write_bytes(legacy_image(advanced_save.read_bytes()))
        legacy, _ = run("legacy-coldboot", "read", legacy_path)
        legacy_prog = legacy["boot"]["progress"]
        check("legacy zero-spare campaign restores chapter and paid equipment",
              legacy_prog["unlocked"] == 3 and legacy_prog["acts"][0] == 3
              and legacy["boot"]["live"]["rack_lv"] == 1 and legacy["boot"]["live"]["paint"] == 1
              and legacy_prog["extension"] == bytes(16).hex())
        check("legacy zero-spare campaign leaves extras at cold defaults",
              legacy["boot"]["live"]["sw_pack"] == 0
              and legacy["boot"]["live"]["options"] == first["boot"]["live"]["options"])
        migrated, migrated_save = run("profile-512-migration", "write",
                                     args.out / "menu-write/payback-profile-512.srm")
        check("existing 512-byte Payback profile is loaded before campaign expansion",
              migrated["loaded_native_bytes"] == 512 and migrated["disk_bytes"] == 8192)
        cold_equal("migration-coldboot", migrated, migrated_save)
        pids = [value["pid"] for value in report["workers"].values()]
        check("every stage ran in a separate process", len(pids) == len(set(pids)))
    except Exception as exc:
        check("acceptance matrix completes", False, error=str(exc))
    report["passed"] = bool(report["checks"]) and all(c["passed"] for c in report["checks"])
    (args.out / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
