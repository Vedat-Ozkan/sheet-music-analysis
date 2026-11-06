from pathlib import Path
R = Path("app/src/main/java/org/audiveris/omr")
p = R / "sig/HeadTrace.java"; s = p.read_bytes().decode()
a = "    public static synchronized void log (String line)"
s = s.replace(a, """    public static void dump (org.audiveris.omr.glyph.Glyph g, String tag)
    {
        final String dir = System.getenv("CLEFDUMP");
        if (dir == null) {
            return;
        }
        try {
            final java.awt.Rectangle b = g.getBounds();
            final String name = tag + "-" + b.x + "-" + b.y + "-" + b.width + "x" + b.height + "-" + g.getWeight() + ".png";
            javax.imageio.ImageIO.write(g.getRunTable().getBufferedImage(), "png", new java.io.File(dir, name));
        } catch (Exception ex) {
            log("DUMPFAIL " + ex);
        }
    }

""" + a, 1)
p.write_bytes(s.encode())
p = R / "sheet/clef/ClefBuilder.java"; s = p.read_bytes().decode()
a = '            logger.debug("ClefAdapter evaluateGlyph on {}", glyph);'
s = s.replace(a, '            org.audiveris.omr.sig.HeadTrace.dump(glyph, "h" + staff.getId());\n' + a, 1)
p.write_bytes(s.encode())
p = R / "sheet/symbol/SymbolsBuilder.java"; s = p.read_bytes().decode()
a = "            if (probe.intersects(glyph.getBounds())) {"
s = s.replace(a, a + '\n                org.audiveris.omr.sig.HeadTrace.dump(glyph, "s");', 1)
p.write_bytes(s.encode())
