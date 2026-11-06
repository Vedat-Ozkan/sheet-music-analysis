from pathlib import Path
p = Path("app/src/main/java/org/audiveris/omr/sheet/clef/ClefBuilder.java"); s = p.read_bytes().decode()
a = "Glyphs.buildLinks(parts, params.maxPartGap);"
assert a in s
s = s.replace(a, "Glyphs.buildLinks(parts, retryGap > 0 ? retryGap : params.maxPartGap);", 1)
a = "    /** Dedicated staff to analyze. */"
s = s.replace(a, "    private double retryGap;\n\n" + a, 1)
a = "        // Register the remaining clef candidates"
assert a in s
s = s.replace(a, """        if (bestMap.isEmpty()) {
            retryGap = 1.5 * staff.getSpecificInterline();
            bestMap = getBestMap(true);
            retryGap = 0;
        }

""" + a, 1)
p.write_bytes(s.encode())
