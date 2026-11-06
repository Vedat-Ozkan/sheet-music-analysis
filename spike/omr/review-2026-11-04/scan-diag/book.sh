#!/bin/bash
out=$1; pdf=$2; shift 2
mkdir -p "$out"
L=/home/kema/projects/sheet-music-plugin/spike/omr/speed/launchers/marks1/bin/Audiveris
HOME=$out _JAVA_OPTIONS="-Xmx2g -Djava.awt.headless=true -Dsun.java2d.uiScale=1" TESSDATA_PREFIX=$(dirname $(dirname $L))/tessdata \
  $L -batch -option org.audiveris.omr.sig.inter.RestInter.minInterChordDx=0.0 -option "org.audiveris.omr.sig.inter.AbstractTimeInter.optionalTimes=6/4, 7/8, 8/8" "$@" -transcribe -save -output "$out" "$pdf" > "$out/log.txt" 2>&1
