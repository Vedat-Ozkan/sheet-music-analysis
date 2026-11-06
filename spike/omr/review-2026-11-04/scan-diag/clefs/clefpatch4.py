from pathlib import Path
R = Path("app/src/main/java/org/audiveris/omr")
def rw(f, fn):
    p = R / f; s = p.read_bytes().decode(); s2 = fn(s); assert s != s2, f; p.write_bytes(s2.encode())
def big(s):
    a = s.index("                if (oversizedBass(glyph, staff)) {")
    b = s.index("}", s.index("yield null;", a)) + 1
    s = s[:a] + s[b:].lstrip("\r\n")
    return s.replace("private static boolean oversizedBass", "public static boolean oversizedBass")
rw("sig/inter/ClefInter.java", big)
rw("sheet/symbol/SymbolsBuilder.java", lambda s: s.replace("                final Inter created = factory.create(eval, glyph, closestStaff);", """                if ((eval.shape == org.audiveris.omr.glyph.Shape.F_CLEF || eval.shape == org.audiveris.omr.glyph.Shape.F_CLEF_SMALL)
                        && org.audiveris.omr.sig.inter.ClefInter.oversizedBass(glyph, closestStaff)) {
                    continue;
                }

                final Inter created = factory.create(eval, glyph, closestStaff);""", 1))
rw("sheet/clef/ClefBuilder.java", lambda s: s.replace("        // Keep only interesting parts\r\n", """        for (Glyph tracePart : parts) {
            org.audiveris.omr.sig.HeadTrace.log("CLEFPART " + sheet.getStub().getNumber() + " " + staff.getId() + " " + isFirstPass + " " + org.audiveris.omr.sig.HeadTrace.box(tracePart.getBounds()) + " " + tracePart.getWeight() + " inner=" + tracePart.getBounds().intersects(innerRect));
        }

        // Keep only interesting parts\r\n""", 1))
NEW = """    private void findBassClefs (Staff staff,
                                List<HeadInter> heads)
    {
        final Classifier classifier = ShapeClassifier.getInstance();
        final ByteProcessor noStaff = sheet.getPicture().getSource(Picture.SourceKey.NO_STAFF);
        final Set<Rectangle> checked = new HashSet<>();
        final int il = scale.getInterline();

        for (HeadInter head : new ArrayList<>(heads)) {
            if (head.isRemoved() || head.getShape().isSmallHead() || !checked.add(head.getBounds())) {
                continue;
            }

            final Rectangle box = head.getBounds();
            final Rectangle win = new Rectangle(box.x - il / 2, box.y - (3 * il) / 5, (7 * il) / 2, (9 * il) / 2)
                    .intersection(new Rectangle(0, 0, noStaff.getWidth(), noStaff.getHeight()));

            if (win.isEmpty()) {
                continue;
            }

            final List<Glyph> parts = new ArrayList<>();

            for (Glyph part : GlyphFactory.buildGlyphs(new RunTableFactory(Orientation.VERTICAL).createTable(noStaff, win), new Point(win.x, win.y))) {
                final Rectangle b = part.getBounds();

                if (b.intersects(box) || ((b.x > win.x) && (b.y > win.y) && (b.x + b.width < win.x + win.width)
                        && (b.y + b.height < win.y + win.height) && (part.getWeight() >= 10))) {
                    parts.add(part);
                }
            }

            if (parts.isEmpty()) {
                continue;
            }

            final Glyph ink = (parts.size() == 1) ? parts.get(0) : GlyphFactory.buildGlyph(parts);
            final Rectangle ib = ink.getBounds();

            if ((ib.height < 2.2 * il) || (ib.height > 3.9 * il) || (ib.width < 1.8 * il) || (ib.width > 3.4 * il)
                    || sig.intersectedInters(ib).stream().anyMatch(inter -> inter instanceof ClefInter)) {
                continue;
            }

            final Evaluation[] evals = classifier.evaluate(ink, il, 1, 0.0, null);

            if ((evals.length == 0) || ((evals[0].shape != Shape.F_CLEF) && (evals[0].shape != Shape.F_CLEF_SMALL))
                    || (ClefInter.drawnGrade(evals[0].shape, evals[0].grade, ink, staff) < constants.minClefGrade.getValue())
                    || (Math.abs(staff.pitchPositionOf(ink.getCenter2D())) >= 4)) {
                continue;
            }

            final List<HeadInter> inside = new ArrayList<>();

            for (HeadInter h : heads) {
                final Rectangle hb = h.getBounds();
                final Rectangle common = hb.intersection(ib);

                if (!common.isEmpty() && ((2 * common.width * common.height) >= (hb.width * hb.height))) {
                    inside.add(h);
                }
            }

            final ClefInter clef = ClefInter.createValid(system.registerGlyph(ink, null), evals[0].shape, Grades.intrinsicRatio * evals[0].grade, staff);
            org.audiveris.omr.sig.HeadTrace.log("CLEFKNOB " + staff.getId() + " " + org.audiveris.omr.sig.HeadTrace.box(ib) + " " + evals[0].shape + " " + evals[0].grade + " heads=" + inside.size());

            for (HeadInter h : inside) {
                h.remove();
            }

            heads.removeAll(inside);
            sig.addVertex(clef);
            clef.freeze();
        }
    }

"""
def knob(s):
    a = "    private void findClefs (Staff staff,"
    i = s.index(a)
    j = s.rindex("    //-----------", 0, i)
    j = s.rindex("    //-----------", 0, j)
    s = s[:j] + NEW + s[j:]
    b = "        final Set<Rectangle> checked = new HashSet<>(); // Head candidates share locations"
    k = s.index(b)
    return s[:k] + '        if (System.getenv("CLEFKNOB") != null) {\n            findBassClefs(staff, heads);\n        }\n\n' + s[k:]
rw("sheet/note/NoteHeadsBuilder.java", knob)
