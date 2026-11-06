#!/bin/bash
out=$1; pdf=$2; shift 2
aud=${AUD:-/tmp/claude-1000/-home-kema-projects/e7eb6523-6727-4e40-ab68-cd8b0116ddd2/scratchpad/heads/aud}
mkdir -p "$out"
opts=(-option org.audiveris.omr.sig.inter.RestInter.minInterChordDx=0.0 -option "org.audiveris.omr.sig.inter.AbstractTimeInter.optionalTimes=6/4, 7/8, 8/8" "$@")
export HOME=$out _JAVA_OPTIONS="-Xmx2g -Djava.awt.headless=true -Dsun.java2d.uiScale=1" TESSDATA_PREFIX=$aud/tessdata
HEADTRACE=$out/trace.txt timeout 900 $aud/bin/Audiveris -batch "${opts[@]}" -export -output "$out" "$pdf" > "$out/log.txt" 2>&1
if ! ls "$out"/*.mxl >/dev/null 2>&1 && ls "$out"/*.omr >/dev/null 2>&1; then
  HEADTRACE=$out/trace2.txt timeout 900 $aud/bin/Audiveris -batch "${opts[@]}" -export -output "$out" "$out"/*.omr > "$out/log2.txt" 2>&1
  cat "$out/trace2.txt" >> "$out/trace.txt"
fi
