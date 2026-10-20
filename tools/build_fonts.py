from pathlib import Path

from fontTools.ttLib import TTFont
from fontTools.ttLib.tables import ttProgram

FONTS = Path(__file__).resolve().parent.parent / "engine" / "fonts"
FAMILY = "Score Serif"
SIGNS = (0x266D, 0x266E, 0x266F)
STYLES = {
    "Regular": ("LiberationSerif-Regular.ttf", "DejaVuSerif.ttf"),
    "Bold": ("LiberationSerif-Bold.ttf", "DejaVuSerif-Bold.ttf"),
    "Italic": ("LiberationSerif-Italic.ttf", "DejaVuSerif.ttf"),
    "BoldItalic": ("LiberationSerif-BoldItalic.ttf", "DejaVuSerif-Bold.ttf"),
}


def build(style: str, base_file: str, signs_file: str) -> None:
    font, signs = TTFont(FONTS / base_file), TTFont(FONTS / signs_file)
    assert font["head"].unitsPerEm == signs["head"].unitsPerEm
    order = font.getGlyphOrder()
    for code in SIGNS:
        if code in font.getBestCmap():
            continue
        source = signs.getBestCmap()[code]
        name = f"uni{code:04X}.dejavu"
        glyph = signs["glyf"][source]
        glyph.expand(signs["glyf"])
        glyph.program = ttProgram.Program()
        glyph.program.fromBytecode(b"")
        assert not glyph.isComposite()
        font["glyf"].glyphs[name] = glyph
        font["hmtx"].metrics[name] = signs["hmtx"].metrics[source]
        order.append(name)
        for table in font["cmap"].tables:
            if table.isUnicode():
                table.cmap[code] = name
    font.setGlyphOrder(order)
    font["glyf"].glyphOrder = order
    font["maxp"].numGlyphs = len(order)
    names = font["name"]
    for record in list(names.names):
        if record.nameID in (1, 3, 4, 6, 16, 17, 21, 22):
            names.removeNames(nameID=record.nameID)
    full = FAMILY if style == "Regular" else f"{FAMILY} {style.replace('BoldItalic', 'Bold Italic')}"
    subfamily = style.replace("BoldItalic", "Bold Italic")
    for name_id, value in ((1, FAMILY), (2, subfamily), (3, f"{FAMILY.replace(' ', '')}-{style}"), (4, full), (6, f"{FAMILY.replace(' ', '')}-{style}")):
        names.setName(value, name_id, 3, 1, 0x409)
        names.setName(value, name_id, 1, 0, 0)
    font.save(FONTS / f"ScoreSerif-{style}.ttf")


if __name__ == "__main__":
    for style, (base, signs) in STYLES.items():
        build(style, base, signs)
