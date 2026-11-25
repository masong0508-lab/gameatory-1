#!/usr/bin/env python3
"""Private expanded-cache placement and preseed generation for merged PS1.
No ROM bytes, profiles or generated headers belong in the repository.
"""
import hashlib
import json
import re
import sys
from pathlib import Path

PAGE = 4096
ROM_BYTES = 16 * 1024 * 1024
MAX_PAGES = 52

def plan(nat_lo, cold_host, pages):
    if not isinstance(pages, int) or not 0 <= pages <= MAX_PAGES or pages % 4:
        raise ValueError("SFNAT_EXT_PAGES must be 0 or a multiple of 4 through 52")
    if nat_lo < cold_host or (nat_lo-cold_host) % 16384:
        raise ValueError("native start must be a cold-group boundary")
    lo = nat_lo - pages*PAGE
    # Preserve the boot image and cold group 27 (B2 translated cell fix).
    if pages and lo < max(0x800a8100, cold_host+28*16384):
        raise ValueError("expanded cache would reclaim boot or cell-fix code; reduce SFNAT_EXT_PAGES")
    return lo

def parse_seeds(text, pages):
    ids = []
    for line in text.splitlines():
        for token in line.split("#", 1)[0].split():
            pg = int(token, 16)
            if not 0 <= pg < ROM_BYTES//PAGE or pg in ids:
                raise ValueError("duplicate or out-of-range merged ROM page")
            ids.append(pg)
    if len(ids) > pages:
        raise ValueError("seed count exceeds expanded cache capacity")
    return ids

def generate(natdir, pages, seed_path=None, rom_path=None):
    root = Path(natdir)
    ids = parse_seeds(Path(seed_path).read_text(), pages) if seed_path else []
    if seed_path and not pages:
        raise ValueError("seed list requires a nonzero expanded cache")
    rom = b""
    if ids:
        if not rom_path:
            raise ValueError("B3EXT_ROM must name the matching private merged ROM")
        rom = Path(rom_path).read_bytes()
        if len(rom) != ROM_BYTES:
            raise ValueError("seeds require a 16 MiB merged ROM")
    # Array remains writable; linker reserves the entire frame range.
    h = ["/* private generated page data: never commit */",
         "#define B3_EXT_SEED_COUNT %du" % len(ids)]
    if pages:
        h.append("static const u16 b3_ext_seed_ids[%d] = {%s};" %
                 (max(1, len(ids)), ",".join(str(p) for p in ids) or "0"))
        h.append('static u8 b3_ext_storage[SF_NAT_EXT_N*4096u] __attribute__((section(".sfncache.ext"),aligned(16),used)) = {')
        for pg in ids:
            block = rom[pg*PAGE:(pg+1)*PAGE]
            for i in range(0,PAGE,32):
                h.append(",".join("0x%02x"%v for v in block[i:i+32])+",")
        if not ids:
            h.append("0")
        h.append("};")
    data = ("\n".join(h)+"\n").encode("ascii")
    (root/"sfnat_ext_seed.h").write_bytes(data)
    meta = {"pages":pages,"seed_count":len(ids),"header_sha256":hashlib.sha256(data).hexdigest(),
            "rom_sha256":hashlib.sha256(rom).hexdigest() if ids else None}
    (root/"sfnat_ext_seed.json").write_text(json.dumps(meta,sort_keys=True)+"\n")
    return len(ids)

def verify(natdir, rom_path):
    root=Path(natdir)
    header=(root/"sfnat_place.h").read_text()
    m=re.search(r"^#define SF_NAT_EXT_N (\d+)u$",header,re.M)
    if not m:
        return 0  # older native placement, no extension
    pages=int(m.group(1))
    meta=json.loads((root/"sfnat_ext_seed.json").read_text())
    if meta["pages"]!=pages or not 0<=meta["seed_count"]<=pages:
        raise ValueError("expanded-cache placement/seed mismatch")
    if hashlib.sha256((root/"sfnat_ext_seed.h").read_bytes()).hexdigest()!=meta["header_sha256"]:
        raise ValueError("expanded-cache header changed after placement")
    if meta["seed_count"]:
        rom=Path(rom_path).read_bytes()
        if len(rom)!=ROM_BYTES or hashlib.sha256(rom).hexdigest()!=meta["rom_sha256"]:
            raise ValueError("expanded-cache seeds are from a different merged ROM")
    return pages

if __name__=="__main__":
    print("expanded cache: %d extra pages" % verify(sys.argv[1],sys.argv[2]))
