#!/bin/bash
name=$1; shift
S=/tmp/claude-1000/-home-kema-projects/e7eb6523-6727-4e40-ab68-cd8b0116ddd2/scratchpad
mkdir -p $S/heads/w/$name/bin
ln -sfn $S/aud-marks1/tessdata $S/heads/w/$name/tessdata
{ echo '#!/bin/bash'; printf 'exec %s/aud-marks1/bin/Audiveris' $S; for o in "$@"; do printf ' -option %q' "$o"; done; echo ' "$@"'; } > $S/heads/w/$name/bin/Audiveris
chmod +x $S/heads/w/$name/bin/Audiveris
