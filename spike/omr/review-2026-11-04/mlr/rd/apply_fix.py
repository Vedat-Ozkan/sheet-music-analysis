import sys
p = sys.argv[1] + "/app/src/main/java/org/audiveris/omr/sheet/symbol/SymbolsBuilder.java"
s = open(p, newline="").read()
nl = "\r\n" if "\r\n" in s else "\n"
a = "        final List<Evaluation> evals = withClefSizesMerged(classifier.evaluate("
assert s.count(a) == 1
s = s.replace(a, "        glyph = withRestTipsRestored(glyph);" + nl + nl + a)
a = "    //---------------------//" + nl + "    // withClefSizesMerged //"
assert s.count(a) == 1
m = '''    private Glyph withRestTipsRestored (Glyph glyph)
    {
        final List<Point> tips = new ArrayList<>(tipThroughLine(glyph, 1));
        tips.addAll(tipThroughLine(glyph, -1));

        if (tips.isEmpty()) {
            return glyph;
        }

        final Rectangle box = glyph.getBounds();

        for (Point tip : tips) {
            box.add(tip);
        }

        box.setSize(
                Math.max(box.width, tips.stream().mapToInt(t -> t.x - box.x + 1).max().getAsInt()),
                Math.max(box.height, tips.stream().mapToInt(t -> t.y - box.y + 1).max().getAsInt()));

        final ByteProcessor buffer = new ByteProcessor(box.width, box.height);
        buffer.invert();
        glyph.getRunTable().write(buffer, glyph.getLeft() - box.x, glyph.getTop() - box.y);

        for (Point tip : tips) {
            buffer.set(tip.x - box.x, tip.y - box.y, 0);
        }

        final Glyph restored = new Glyph(
                box.x,
                box.y,
                new RunTableFactory(Orientation.VERTICAL).createTable(buffer));
        final Evaluation[] natural = classifier.evaluate(
                glyph,
                system,
                1,
                0,
                EnumSet.of(Classifier.Condition.CHECKED));
        final Evaluation[] better = classifier.evaluate(
                restored,
                system,
                1,
                0,
                EnumSet.of(Classifier.Condition.CHECKED));

        if ((better.length == 0) || !ShapeSet.Rests.contains(better[0].shape)
                || ((natural.length > 0) && (natural[0].grade >= better[0].grade))) {
            return glyph;
        }

        return sheet.getGlyphIndex().registerOriginal(restored);
    }

    private List<Point> tipThroughLine (Glyph glyph,
                                        int dir)
    {
        final ByteProcessor binary = sheet.getPicture().getSource(Picture.SourceKey.BINARY);
        final Rectangle box = glyph.getBounds();
        final int maxTipWidth = constants.maxTipWidth.getValue();
        final int maxRows = 2 * sheet.getScale().getMaxFore();
        int y = (dir > 0) ? (box.y + box.height - 1) : box.y;
        Set<Integer> columns = new LinkedHashSet<>();

        for (int x = box.x; x < (box.x + box.width); x++) {
            if (glyph.contains(new Point(x, y))) {
                columns.add(x);
            }
        }

        final List<Point> tip = new ArrayList<>();
        boolean crossedLine = false;

        for (int row = 0; row < maxRows; row++) {
            y += dir;

            if ((y < 0) || (y >= binary.getHeight())) {
                break;
            }

            final int yy = y;
            final Set<Integer> reached = new LinkedHashSet<>();

            for (int column : columns) {
                for (int x = Math.max(0, column - 1); x <= Math.min(binary.getWidth() - 1, column + 1); x++) {
                    if (binary.get(x, yy) == 0) {
                        reached.add(x);
                    }
                }
            }

            if (reached.size() > maxTipWidth) {
                crossedLine = true;
                reached.retainAll(columns);
            }

            if (reached.isEmpty() || (reached.size() > maxTipWidth)) {
                break;
            }

            for (int x : reached) {
                tip.add(new Point(x, yy));
            }

            columns = reached;
        }

        return crossedLine ? tip : Collections.emptyList();
    }

'''.replace("\n", nl)
s = s.replace(a, m + a)
a = '        private final Constant.Integer maxPartCount = new Constant.Integer('
assert s.count(a) == 1
s = s.replace(a, '        private final Constant.Integer maxTipWidth = new Constant.Integer(' + nl + '                "Pixels",' + nl + '                3,' + nl + '                "Maximum width of a symbol end followed through a staff line");' + nl + nl + a)
for imp, after in [("import org.audiveris.omr.glyph.ShapeSet;", "import org.audiveris.omr.glyph.Shape;"),
                   ("import org.audiveris.omr.run.Orientation;" + nl + "import org.audiveris.omr.run.RunTableFactory;" + nl + "import org.audiveris.omr.sheet.Picture;", None),
                   ("import ij.process.ByteProcessor;", None), ("import java.awt.Point;", None)]:
    if imp.split(nl)[0] in s:
        continue
    if after:
        s = s.replace(after + nl, after + nl + imp + nl, 1)
    else:
        i = s.index("import org.audiveris.omr.classifier.Evaluation;")
        s = s[:i] + imp + nl + s[i:]
open(p, "w", newline="").write(s)
