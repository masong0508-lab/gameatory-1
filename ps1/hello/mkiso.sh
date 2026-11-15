#!/bin/sh
# hello.iso: ISO9660 with SYSTEM.CNF + PSX.EXE (what emulators boot; HLE BIOS or real BIOS)
cd "$(dirname "$0")"; rm -rf iso; mkdir iso; cp hello.exe iso/PSX.EXE
printf 'BOOT = cdrom:\\PSX.EXE;1\r\nTCB = 4\r\nEVENT = 10\r\nSTACK = 801FFF00\r\n' > iso/SYSTEM.CNF
genisoimage -quiet -V STARFLYBACK -sysid PLAYSTATION -o hello.iso iso
