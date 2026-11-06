from pathlib import Path
R = Path("app/src/main/java/org/audiveris/omr")
def sub(f, anchor, new, before=False):
    p = R / f; s = p.read_bytes().decode()
    assert s.count(anchor) >= 1, (f, anchor)
    i = s.index(anchor)
    s = s[:i] + new + s[i:] if before else s[:i + len(anchor)] + new + s[i + len(anchor):]
    p.write_bytes(s.encode())
H = "org.audiveris.omr.sig.HeadTrace"
sub("sheet/symbol/SymbolsBuilder.java", '        if (System.getenv("HEADTRACE") != null) {\n            final org.audiveris.omr.classifier.Evaluation[] raw', """        if (System.getenv("CLEFPROBE") != null) {
            final String[] pr = System.getenv("CLEFPROBE").split(",");
            final java.awt.Rectangle probe = new java.awt.Rectangle(Integer.parseInt(pr[0]), Integer.parseInt(pr[1]), Integer.parseInt(pr[2]), Integer.parseInt(pr[3]));
            if (probe.intersects(glyph.getBounds())) {
                """ + H + """.log("CLEFP " + closestStaff.getId() + " " + """ + H + """.box(glyph.getBounds()) + " " + glyph.getWeight() + """ + H + """.evals(classifier.evaluate(glyph, system, 5, 0.0, null)));
            }
        }
""", before=True)
sub("sig/inter/ClefInter.java", "    public static double drawnGrade (Shape shape,", """    public static boolean fitsBassDrawing (Glyph glyph,
                                           Staff staff)
    {
        return bassDrawing().fits(glyph, staff);
    }

    private static boolean oversizedBass (Glyph glyph,
                                          Staff staff)
    {
        final double il = staff.getSpecificInterline();
        return System.getenv("CLEFBIG") != null
                && (glyph.getBounds().height / il > 1.25 * constants.bassClefHeight.getValue());
    }

""", before=True)
sub("sig/inter/ClefInter.java", "            case F_CLEF, F_CLEF_SMALL -> {\r\n", """                if (oversizedBass(glyph, staff)) {
                    yield null;
                }
""")
sub("sheet/clef/ClefBuilder.java", "            logger.debug(\"ClefAdapter evaluateGlyph on {}\", glyph);", """            if (System.getenv("CLEFHDR") != null && ClefInter.fitsBassDrawing(glyph, staff)
                    && (bassFit == null || glyph.getWeight() > bassFit.getWeight())) {
                bassFit = glyph;
            }

""", before=True)
sub("sheet/clef/ClefBuilder.java", "        // Register the remaining clef candidates", """        if (bestMap.isEmpty() && bassFit != null) {
            bestMap.put(ClefKind.BASS, ClefInter.createValid(bassFit, F_CLEF, 0.5 * Grades.intrinsicRatio, staff));
        }

""", before=True)
sub("sheet/clef/ClefBuilder.java", "    /** Dedicated staff to analyze. */", """    private Glyph bassFit;

""", before=True)
