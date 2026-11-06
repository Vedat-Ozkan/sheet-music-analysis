#!/bin/bash
for st in faisst-op18-2-lied-der-nacht--scan kinkel-op8-5-trennung--scan beethoven-op48-5-gottes-macht--scan; do
  f=$(/home/kema/projects/sheet-music-plugin/.venv/bin/python -c "import json;m=json.load(open('../../bench/manifest.json'));print([e['pdf'] for e in m['pdfs'] if '$st' in e['pdf']][0])")
  taskset -c 8-11 /home/kema/projects/sheet-music-plugin/.venv/bin/python pipeline.py ../../bench/$f --out /tmp/claude-1000/-home-kema-projects/e7eb6523-6727-4e40-ab68-cd8b0116ddd2/scratchpad/prescan/runs/sim-$st --threads 4 --homr after --reuse-current ../../speed/cache/runs/marks1/bench--$st.musicxml --render > /tmp/claude-1000/-home-kema-projects/e7eb6523-6727-4e40-ab68-cd8b0116ddd2/scratchpad/prescan/runs/sim-$st.log 2>&1
done
