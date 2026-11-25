#!/usr/bin/env python3
"""Compute the candidate flight/station slot and permanent cold-code ceiling.

Read the actual private B2 ELF section extents. The report is a feasibility
check for the shared slot, NOT a claim that the complete B3 native modules
or GPU backend fit. Cold groups crossing the slot must be interpreted from
boot, never dynamically linked or restored there.
"""
import argparse
import json
import struct
from pathlib import Path
from gpu_layout import elf_ranges, interval

GROUP=16384
SECTOR=2048
CAP=0x22000
WORLD=0x800cd800


def plan(live, native_lo, world=WORLD, capacity=CAP):
    byname={name:(a,b) for name,a,b in live if name in ('.blob','.bootimg')}
    if set(byname)!={'.blob','.bootimg'}:
        raise ValueError('need the translated blob and boot image')
    host=byname['.blob'][1]
    boot_end=byname['.bootimg'][1]
    lo=world-capacity
    if not 0<capacity<=CAP or capacity%SECTOR or world%SECTOR or not 0x80010000<=lo<world<=0x80108000:
        raise ValueError('invalid shared slot')
    if not host<boot_end<=lo or native_lo<=host or (native_lo-host)%GROUP:
        raise ValueError('invalid translation/native boundary')
    ceiling=host+((min(lo,native_lo)-host)//GROUP)*GROUP
    # cold_all copies only whole groups. During boot the original image
    # is still needed, and all resident allocated sections must stay out.
    conflicts=[]
    for name,a,b in live:
        if a<world and b>lo:
            conflicts.append(dict(owner=name,bytes=min(b,world)-max(a,lo)))
    first=(lo-host)//GROUP
    last=(world-1-host)//GROUP
    return dict(slot_start=lo,slot_end=world,slot_bytes=capacity,
                cold_host=host,boot_image_end=boot_end,cold_ceiling=ceiling,
                old_cold_groups=(native_lo-host)//GROUP,
                new_cold_groups=(ceiling-host)//GROUP,
                groups_intersecting_slot=list(range(first,last+1)),
                conflicting_sections=conflicts,
                slot_fit=not conflicts,full_gpu_layout_verified=False)


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--elf',type=Path,required=True)
    ap.add_argument('--native-lo',type=lambda x:int(x,0),required=True)
    ap.add_argument('--world',type=lambda x:int(x,0),default=WORLD)
    ap.add_argument('--capacity',type=lambda x:int(x,0),default=CAP)
    a=ap.parse_args()
    try: result=plan(elf_ranges(a.elf.read_bytes()),a.native_lo,a.world,a.capacity)
    except (OSError,ValueError,struct.error) as e: ap.error(str(e))
    print(json.dumps(result,indent=2))
    return 0 if result['slot_fit'] else 1


if __name__=='__main__': raise SystemExit(main())
