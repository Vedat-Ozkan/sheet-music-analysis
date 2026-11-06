#!/bin/bash
S=/tmp/claude-1000/-home-kema-projects/e7eb6523-6727-4e40-ab68-cd8b0116ddd2/scratchpad
while read set stem; do for s in 0 1; do echo "$S/aud-pitch51 $set $stem $s $S/mlr/tb"; done; done < $S/mlr/sample.txt | xargs -P 6 -L 1 $S/mlr/tb_run.sh
echo done
