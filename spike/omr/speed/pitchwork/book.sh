#!/bin/bash
# usage: book.sh INSTALL PDF OUTDIR [small]
S=${READERS:-/tmp/claude-1000/-home-kema-projects/e7eb6523-6727-4e40-ab68-cd8b0116ddd2/scratchpad}
mkdir -p $3 && cp "$2" $3/score.pdf && cd $3
OPTS=(-option org.audiveris.omr.sig.inter.RestInter.minInterChordDx=0.0 -option "org.audiveris.omr.sig.inter.AbstractTimeInter.optionalTimes=6/4, 7/8, 8/8")
[ -n "$EXTRA" ] && OPTS+=($EXTRA)
case "$2" in *--ms.pdf) OPTS+=(-option org.audiveris.omr.ui.symbol.MusicFont.defaultMusicFamily=Leland);; esac
[ "$4" = small ] && OPTS+=(-option org.audiveris.omr.sheet.ProcessingSwitches.smallHeads=true -option org.audiveris.omr.sheet.ProcessingSwitches.smallBeams=true -option org.audiveris.omr.sheet.ProcessingSwitches.implicitTuplets=true)
TESSDATA_PREFIX=$S/$1/tessdata HOME=$3 _JAVA_OPTIONS="-Xmx1g -Djava.awt.headless=true -Dsun.java2d.uiScale=1 $DIAG" timeout 900 $S/$1/bin/Audiveris -batch "${OPTS[@]}" -export -output $3 score.pdf > run.txt 2>&1
rm -rf book && unzip -o -q score.omr -d book
