#!/bin/bash
# usage: live_stats.sh log : stats over the "SF3 frame" lines (host = renderer hblank lines)
grep "SF3 frame" "$1" | awk '{for(i=1;i<=NF;i++){ if($i=="host")h=$(i+1); if($i=="lod")l=$(i+1); if($i=="gat")g=$(i+1)} print h,l,g}' | sort -n | awk '{a[NR]=$1;s+=$1;g+=$3;if($1>456)o++;c[$2]++} END{printf "n %d mean %.1f median %d min %d max %d over456 %d (%.0f%%) gather mean %.1f lods",NR,s/NR,a[int((NR+1)/2)],a[1],a[NR],o,100*o/NR,g/NR; for(k in c) printf " lod%s:%d",k,c[k]; print ""}'
