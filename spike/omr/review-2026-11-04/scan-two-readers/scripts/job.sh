#!/bin/bash
echo "cpus $(nproc) mem $(awk '/MemTotal/{print $2}' /proc/meminfo) KB"
for t in 4 2; do for p in /pages/*.png; do
  ORT_THREADS=$t OMP_NUM_THREADS=$t /usr/bin/time -f "RESULT threads=$t $(basename $p) wall %e cpu %U+%S peakKB %M exit %x" python /safe.py $p 2>&1 | grep -E "^RESULT|Traceback"
done; done
echo RESULT done
