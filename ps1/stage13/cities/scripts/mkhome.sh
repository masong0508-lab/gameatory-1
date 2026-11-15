#!/bin/bash
# mkhome.sh DIR : a fresh emulator HOME with a BLANK memory card
D=$(readlink -f -m "$1"); S=$(dirname "$(readlink -f "$0")")
rm -rf "$D"; mkdir -p "$D"; cp -a $S/../s10_boot/home1/.pcsxr "$D/"; 
sed -i "s#$S/../s10_boot/home1#$D#g; s#/tmp/claude-0/-home-user/567ff2df-658a-593d-ba5b-58eb793419f5/scratchpad/v12/ps1/s10_boot/home1#$D#g" "$D/.pcsxr/pcsxr.cfg"
cp $S/../card1.orig.mcd "$D/.pcsxr/memcards/card1.mcd"; cp $S/../card1.orig.mcd "$D/.pcsxr/memcards/card2.mcd"
mkdir -p "$D/.config"; cp -a $S/../s10_boot/home1/.config/. "$D/.config/" 2>/dev/null; cp -a $S/../s10_boot/home1/.cache "$D/" 2>/dev/null; true
