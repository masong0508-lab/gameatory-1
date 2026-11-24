# B3 measured ROM residency candidate

B2's stock runs were seek-bound (15–21 physical page misses per tick over
roughly 96 active pages with a 69-frame pool). B3 native-code work is intended
to remove many instruction/table reads; the remaining map pages need actual
measurements, not guessed address lists.

Build a private B3 TEST candidate with `-DPGPROF`. The 4096-byte saturating
`pg_prof` array now increments only on actual requested ROM CD fetches
(including a paired physical read as one request), after the CLOCK soft-remap
path. Bulk pause-block reads are separate diagnostics. Capture short,
independent scene windows (walk, drive, climb/flight, station, map loads)
at stock with known frames and input, excluding boot from level samples.
Reject any interval where a counter saturated. Do not reuse old B2 profiles:
they counted RAM remaps as if they were misses. Use a fresh private process
or reset only the TEST diagnostic counters between windows.

Create numeric JSON with the schema documented in `residency.py`: page keys
are hexadecimal 4 KiB page IDs, not guest byte addresses or ROM contents.
Then:

```sh
python3 ps1/msb/residency.py --profile /private/b3-stock-profile.json \
  --original-boot-list ps1/stage19/t/resident62.txt \
  --out /private/resident_b3.txt --keep-boot 16
```

The ranking normalizes each scene's physical misses to equal weight and
reserves the chosen number of remapped boot pages. It emits 61 unique pages
by default, preserving the current pool memory geometry. The output can be
passed as `RPG=/private/resident_b3.txt` to the merged build. It does not
modify the published source or the original-game resident list. The relocation
also retains the unchanged tail of the original last table page, including
the data following the relocated table.

Compare baseline and candidate using the same private ROM, exact controller
tour, stock and recommended core settings, and guest-tick denominator.
Report actual CD fetches/tick, pictures/s, boot/loading time, save/quit and
pause latency. A ranked list is not a measured performance improvement.
No ROM bytes, screenshots, logs, private addresses of translated code or
generated game data are committed. The B3 target remains <1 physical miss
per tick; it is not claimed achieved by this tool.
