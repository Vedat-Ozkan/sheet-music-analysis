#!/bin/bash
install=$1; set=$2; stem=$3; setting=$4; root=$5
d=$root/$stem/s$setting; mkdir -p $d
base=(-option org.audiveris.omr.sig.inter.RestInter.minInterChordDx=0.0 -option "org.audiveris.omr.sig.inter.AbstractTimeInter.optionalTimes=6/4, 7/8, 8/8")
small=(-option org.audiveris.omr.sheet.ProcessingSwitches.smallHeads=true -option org.audiveris.omr.sheet.ProcessingSwitches.smallBeams=true -option org.audiveris.omr.sheet.ProcessingSwitches.implicitTuplets=true)
opts=("${base[@]}"); [ "$setting" = 1 ] && opts+=("${small[@]}")
cp /home/kema/projects/sheet-music-plugin/spike/omr/$set/pdfs/$stem.pdf $d/$stem.pdf
HOME=$d TESSDATA_PREFIX=$install/tessdata _JAVA_OPTIONS="-Xmx1g -Djava.awt.headless=true -Dsun.java2d.uiScale=1" $install/bin/Audiveris -batch "${opts[@]}" -transcribe -save -export -output $d $d/$stem.pdf > $d/log.txt 2>&1
