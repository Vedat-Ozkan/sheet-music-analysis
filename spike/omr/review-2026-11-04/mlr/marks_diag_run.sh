#!/bin/bash
S=/tmp/claude-1000/-home-kema-projects/e7eb6523-6727-4e40-ab68-cd8b0116ddd2/scratchpad
O=/home/kema/projects/sheet-music-plugin/spike/omr
INST=${INST:-$S/aud-marksdiag}
OUT=${OUT:-$S/mlr/marksdiag}
one() {
  set_=$1; stem=$2; d=$OUT/$stem; mkdir -p $d
  [ -f $d/done ] && exit 0
  HOME=$d TESSDATA_PREFIX=$INST/tessdata _JAVA_OPTIONS="-Xmx1g -Djava.awt.headless=true -Dsun.java2d.uiScale=1" timeout 900 $INST/bin/Audiveris -batch -option org.audiveris.omr.sig.inter.RestInter.minInterChordDx=0.0 -option "org.audiveris.omr.sig.inter.AbstractTimeInter.optionalTimes=6/4, 7/8, 8/8" -export -output $d $O/$set_/pdfs/$stem.pdf > $d/out.txt 2>&1
  touch $d/done
  echo $stem
}
export -f one
export S O INST OUT
python3 -c "import json;[print(p[0],p[1]) for p in json.load(open('$S/mlr/marks_sample.json'))]" | xargs -P 6 -L 1 bash -c 'one "$0" "$1"'
