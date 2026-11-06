import re
from pathlib import Path
R = Path("app/src/main/java/org/audiveris/omr")
def sub(f, anchor, new, before=False):
    p = R / f; s = p.read_bytes().decode()
    assert s.count(anchor) >= 1, (f, anchor)
    i = s.index(anchor)
    if before:
        s = s[:i] + new + s[i:]
    else:
        s = s[:i + len(anchor)] + new + s[i + len(anchor):]
    p.write_bytes(s.encode())
H = "org.audiveris.omr.sig.HeadTrace"
sub("sig/HeadTrace.java", "    public static synchronized void log (String line)", """    public static String evals (org.audiveris.omr.classifier.Evaluation[] evals)
    {
        final StringBuilder sb = new StringBuilder();
        for (org.audiveris.omr.classifier.Evaluation e : evals) {
            sb.append(' ').append(e.shape).append('=').append(String.format("%.3f", e.grade));
        }
        return sb.toString();
    }

    public static void clefInter (String tag, org.audiveris.omr.sig.inter.ClefInter c, String extra)
    {
        if (out == null) {
            return;
        }
        final org.audiveris.omr.sig.SIGraph g = c.getSig();
        final int sheet = g == null ? 0 : g.getSystem().getSheet().getStub().getNumber();
        final int staff = c.getStaff() == null ? 0 : c.getStaff().getId();
        final Double ctx = c.getContextualGrade();
        log(tag + " " + sheet + " " + staff + " " + c.getShape() + " " + c.getKind() + " " + String.format("%.3f", c.getGrade())
                + " " + (ctx == null ? "-" : String.format("%.3f", ctx)) + " " + box(c.getBounds()) + " g=" + (c.getGlyph() == null ? "-" : box(c.getGlyph().getBounds()) + " " + c.getGlyph().getWeight()) + " " + extra);
    }

""", before=True)
sub("sheet/clef/ClefBuilder.java", 'logger.debug("ClefAdapter evaluateGlyph on {}", glyph);', """
            """ + H + """.log("CLEFH " + sheet.getStub().getNumber() + " " + staff.getId() + " " + """ + H + """.box(glyph.getBounds()) + " " + glyph.getWeight() + " il=" + staff.getSpecificInterline() + " pp=" + String.format("%.2f", staff.pitchPositionOf(glyph.getCenter2D()))
                    + """ + H + """.evals(classifier.evaluate(glyph, staff.getSpecificInterline(), 8, 0.0, null)));""")
sub("sheet/clef/ClefBuilder.java", "        // Register the remaining clef candidates", """        """ + H + """.log("CLEFHRECT " + sheet.getStub().getNumber() + " " + staff.getId() + " " + """ + H + """.box(outerRect) + " best=" + bestMap);
""", before=True)
sub("sheet/clef/ClefBuilder.java", "            staff.getHeader().clef = bestClef;", """
            """ + H + """.clefInter("CLEFHPICK", bestClef, "of=" + clefs.size());""")
sub("sheet/symbol/SymbolsBuilder.java", "        // Create one interpretation for each acceptable evaluation", """        if (System.getenv("HEADTRACE") != null) {
            final org.audiveris.omr.classifier.Evaluation[] raw = classifier.evaluate(glyph, system, 8, 0.0, null);
            boolean clefLike = false;
            for (org.audiveris.omr.classifier.Evaluation e : raw) {
                clefLike |= e.grade >= 0.02 && (e.shape == org.audiveris.omr.glyph.Shape.F_CLEF || e.shape == org.audiveris.omr.glyph.Shape.F_CLEF_SMALL || e.shape == org.audiveris.omr.glyph.Shape.G_CLEF || e.shape == org.audiveris.omr.glyph.Shape.G_CLEF_SMALL || e.shape == org.audiveris.omr.glyph.Shape.C_CLEF);
            }
            if (clefLike) {
                """ + H + """.log("CLEFS " + system.getSheet().getStub().getNumber() + " " + closestStaff.getId() + " " + """ + H + """.box(glyph.getBounds()) + " " + glyph.getWeight() + " pp=" + String.format("%.2f", closestStaff.pitchPositionOf(center)) + " kept=" + evals.size() + """ + H + """.evals(raw));
            }
        }

""", before=True)
p = R / "sig/inter/AbstractInter.java"; s = p.read_bytes().decode()
a = "if (this instanceof HeadInter traceHead) {"
assert a in s
s = s.replace(a, "if (this instanceof org.audiveris.omr.sig.inter.ClefInter traceClef) {\n                " + H + ".clefInter(\"CLEFREM\", traceClef, " + H + ".where());\n            } else " + a, 1)
p.write_bytes(s.encode())
sub("score/PartwiseBuilder.java", "            for (ClefInter clef : measure.getClefs()) {", """
                """ + H + """.clefInter("CLEFEXP", clef, "m=" + measure.getStack().getPageId());""")
sub("score/PartwiseBuilder.java", "            Map<Staff, List<ClefInter>> map = new HashMap<>();", """
            for (Staff traceStaff : measure.getPart().getStaves()) {
                """ + H + """.log("MEASX " + traceStaff.getSystem().getSheet().getStub().getNumber() + " " + traceStaff.getId() + " " + measure.getStack().getPageId() + " " + measure.getAbscissa(org.audiveris.omr.util.HorizontalSide.LEFT, traceStaff) + " " + measure.getAbscissa(org.audiveris.omr.util.HorizontalSide.RIGHT, traceStaff) + " " + traceStaff.getFirstLine().yAt(measure.getAbscissa(org.audiveris.omr.util.HorizontalSide.LEFT, traceStaff)) + " " + traceStaff.getSpecificInterline());
            }""")
