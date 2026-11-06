#!/bin/bash
set -euo pipefail
PDF=$1; OUT=$2; shift 2
HERE=$(cd "$(dirname "$0")" && pwd)
JDK=$HERE/../tools/jdk25
APP=/tmp/audiveris-5.11.0-sma.2/opt/audiveris/lib/app
CP=$(grep '^app.classpath=' "$APP/Audiveris.cfg" | sed "s#app.classpath=\$APPDIR/#$APP/#" | paste -sd:)
EXTRA=()
for option in "$@"; do EXTRA+=(-option "$option"); done
mkdir -p "$OUT/work"
cp "$PDF" "$OUT/work/score.pdf"
HOME=$OUT/work TESSDATA_PREFIX=/tmp/audiveris-5.11.0-sma.2/opt/audiveris/tessdata \
taskset -c 0,1 "$JDK/bin/java" -Xms512m -Xmx1g -Djava.awt.headless=true -Dsun.java2d.uiScale=1 -Dfile.encoding=UTF-8 \
  --add-exports=java.desktop/sun.awt.image=ALL-UNNAMED --enable-native-access=ALL-UNNAMED \
  -XX:StartFlightRecording=filename=$OUT/read.jfr,settings=profile -cp "$CP" Audiveris \
  -batch -option org.audiveris.omr.sig.inter.RestInter.minInterChordDx=0.0 "${EXTRA[@]}" -export -output "$OUT/work" "$OUT/work/score.pdf" \
  > "$OUT/audiveris.txt" 2>&1
"$JDK/bin/jfr" view --width 200 hot-methods "$OUT/read.jfr" > "$OUT/hot-methods.txt"
"$JDK/bin/jfr" print --events jdk.ExecutionSample --stack-depth 64 "$OUT/read.jfr" > "$OUT/samples.txt"
