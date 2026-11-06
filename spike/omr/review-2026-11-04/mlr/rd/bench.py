import json, sys
sys.path.insert(0, "/home/kema/projects/sheet-music-plugin/spike/omr/speed")
sys.argv, name, install = [sys.argv[0]] + sys.argv[3:], sys.argv[1], sys.argv[2]
import variants
variants.VARIANTS[name] = ([], "", variants.PATCHED + install + "/bin/Audiveris")
variants.main()
