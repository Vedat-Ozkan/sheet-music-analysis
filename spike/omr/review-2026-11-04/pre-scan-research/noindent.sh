#!/bin/bash
export PYTHONDONTWRITEBYTECODE=1
taskset -c 0-3 /home/kema/projects/sheet-music-plugin/.venv/bin/python noindent.py rehearsal/parratt-with-wisdom--scan.pdf /tmp/claude-1000/-home-kema-projects/e7eb6523-6727-4e40-ab68-cd8b0116ddd2/scratchpad/prescan/runs/noindent/01
for k in 05 06 08; do taskset -c 0-3 /home/kema/projects/sheet-music-plugin/.venv/bin/python noindent.py /tmp/claude-1000/-home-kema-projects/e7eb6523-6727-4e40-ab68-cd8b0116ddd2/scratchpad/prescan/runs/book/$k/piece.pdf /tmp/claude-1000/-home-kema-projects/e7eb6523-6727-4e40-ab68-cd8b0116ddd2/scratchpad/prescan/runs/noindent/$k; done
echo NOINDENT DONE
