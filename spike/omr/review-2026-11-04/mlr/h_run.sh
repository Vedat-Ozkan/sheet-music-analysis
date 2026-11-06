#!/bin/bash
S=/tmp/claude-1000/-home-kema-projects/e7eb6523-6727-4e40-ab68-cd8b0116ddd2/scratchpad/mlr
O=/home/kema/projects/sheet-music-plugin/spike/omr
V=$O/homr-venv/bin
export OMP_NUM_THREADS=4
export HOME_ORIG=$HOME
python3 -c "import json;print('\n'.join(' '.join(r) for r in json.load(open('$S/h_set.json'))))" | while read set_ pdf; do
  stem=$(basename "$pdf" .pdf); d=$S/homr/$stem; mkdir -p "$d"
  [ -z "$(ls "$d"/*.png 2>/dev/null)" ] && $V/python -I $O/rasterize.py "$O/$set_/$pdf" "$d" 200 2>>$S/h_err.txt
  for png in "$d"/*.png; do
    x="${png%.png}.musicxml"
    [ -f "$x" ] || timeout 180 $V/homr "$png" > "$png.log" 2>&1
  done
  echo "$stem done $(ls "$d"/*.musicxml 2>/dev/null | wc -l)"
done
