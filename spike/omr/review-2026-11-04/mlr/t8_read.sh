#!/bin/bash
S=/tmp/claude-1000/-home-kema-projects/e7eb6523-6727-4e40-ab68-cd8b0116ddd2/scratchpad/mlr
A=$S/../aud-pitch39
one() {
  set_=$1; stem=$2; eng=$3
  d=$S/books/$stem; rm -rf "$d"; mkdir -p "$d"; cd "$d"
  extra=""
  [ "$eng" = "ms" ] && extra="-option org.audiveris.omr.ui.symbol.MusicFont.defaultMusicFamily=Leland"
  HOME=$d TESSDATA_PREFIX=$A/tessdata _JAVA_OPTIONS="-Xmx1g -Djava.awt.headless=true -Dsun.java2d.uiScale=1" timeout 400 $A/bin/Audiveris -batch -option org.audiveris.omr.sig.inter.RestInter.minInterChordDx=0.0 -option "org.audiveris.omr.sig.inter.AbstractTimeInter.optionalTimes=6/4, 7/8, 8/8" $extra -export -output "$d" "/home/kema/projects/sheet-music-plugin/spike/omr/$set_/pdfs/$stem.pdf" > log.txt 2>&1
  echo "$stem $?"
}
export -f one; export S A
python3 -c "import json;print('\n'.join(' '.join(r) for r in json.load(open('$S/probe_set.json'))))" | xargs -P 4 -L 1 bash -c 'one "$@"' _
