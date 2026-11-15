#!/bin/bash
# live-feedback coverage loop (emulator-only): run the snapshot-resume disc in pcsxr, collect RT_MISS guest addresses, add them to tools7/extra_touch.txt, rebuild, repeat
cd "$(dirname "$0")/.."; export ROM="${ROM:?}"
for it in 1 2 3 4 5 6; do
  RTOPT=-Os bash t/disc7.sh cl "-DPRINT_EVERY_SF3=15" 1 > out/cl_build.log 2>&1
  bash run/run7.sh out/cl.iso run/cl$it ${T:-170} run/empty.txt 0
  last=$(grep "SF3 frame" run/cl$it.log | tail -1 | sed 's/.*SF3 frame \([0-9]*\).*/\1/')
  m=$(grep -o "RT_MISS guest code not in cold set: [0-9a-f]*" run/cl$it.log | head -1 | awk '{print $NF}')
  echo "iter $it last frame $last miss ${m:-none}"
  [ -z "$m" ] && break
  echo "$m" >> tools7/extra_touch.txt
  bash t/final.sh > out/final_cl$it.log 2>&1
done
