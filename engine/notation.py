"""Label conversions and typesetting for notation presets.

Pass the stored Harmony.label and the active key (carried forward by the caller).
Quality/inversion live inside the RomanText label, not separate schema fields.

Conventions: ABRSM's 2020 grades 6–8 syllabus, p. 1, establishes the
harmonic vocabulary, but does not prescribe these exact text spellings:
https://www.mozartacademyofmusic.com/static/assets/doc/theory-syllabus-sheet-g6-8.pdf
Assumed exam notation: omit root-position 'a'; b/c/d denote inversions,
retain case and °/ø, write the Neapolitan as ♭IIb, and augmented sixths as
It+6/Fr+6/Ger+6 (their 6 is an interval, not an inversion letter).
These spellings need owner confirmation, not a claim of ABRSM certification.

Pitch spelling uses music21's RomanText interpretation:
https://music21.org/music21docs/moduleReference/moduleRoman.html
Figured-bass accidentals are literal written ♭/♯/♮/♭♭/♯♯ prefixes, not relative
semitone changes or slashed figures. All implied intervals altered from the
active key signature are made explicit, including 3 and 5. Root-position
5/3 is otherwise omitted. Accidentals on the bass belong on its note, and
are returned separately. Note suffixes (e.g. 4–3) are preserved separately;
they are free text, not enough information to reconstruct suspension pitches.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from engine import text

INVERSIONS = {"": "", "6": "b", "64": "c", "7": "7", "65": "7b", "43": "7c", "42": "7d", "2": "7d"}
SPECIAL = {"N": "♭IIb", "N6": "♭IIb", "Cad64": "Ic", "It6": "It+6", "Fr6": "Fr+6", "Fr43": "Fr+6", "Ger6": "Ger+6", "Ger65": "Ger+6"}
# Bundled fonts lack the single-codepoint double accidentals.
ACCIDENTALS = {-2: "♭♭", -1: "♭", 0: "♮", 1: "♯", 2: "♯♯"}


def current(label: str, key: str | None = None, *, size: float = 400, bold: bool = False) -> tuple[list[text.Chunk], float]:
    """Return exactly the existing renderer's chunks and width; key is separate."""
    return text.numeral(label, size, bold)


def numeral(label: str, key: str | None, style: str, size: float) -> tuple[list[text.Chunk], float]:
    """Keep default typesetting intact; separate bass figures from the Roman root."""
    if style == 'current':
        return current(label, key, size=size)
    if style == 'abrsm':
        return text.numeral(abrsm(label, key), size, inversion_letters=True)
    parts, note = _parts(label)
    # Chord symbols and unsupported extensions retain their original spelling.
    if not all(_supported(part) for part in parts):
        return current(label, key, size=size)
    figures = figured_bass(label, key)
    roots = []
    for part in parts:
        match = text.NUMERAL.fullmatch(part)
        roots.append(match['accidental'].translate(text.SYMBOLS) + match['root']
                     + text.QUALITIES.get(match['quality'], ''))
    # Piston style: the figure stack hangs on the first numeral (V⁶₅/V), as in the other styles.
    return text.numeral('/'.join(roots) + (' ' + note if note else ''), size, first_rows=figures.lines)


def _parts(label: str) -> tuple[list[str], str]:
    main, _, note = label.partition(" ")
    main = re.sub(r"(\d)/(\d)", r"\1\2", main)
    return text._split_secondary(main), note


def _supported(part: str) -> bool:
    match = text.NUMERAL.fullmatch(part)
    return part in SPECIAL or bool(match and match['root'].lower() in ('i', 'ii', 'iii', 'iv', 'v', 'vi', 'vii')
                                   and match['figures'] in INVERSIONS)


def abrsm(label: str, key: str | None = None) -> str:
    """Return letters for supported RomanText forms; other labels stay verbatim.

    Secondary functions retain their slash and target. Free-text suffixes stay
    verbatim. Case carries chord quality, as in the stored analysis.
    """
    parts, note = _parts(label)
    converted = []
    for part in parts:
        if part in SPECIAL:
            converted.append(SPECIAL[part])
            continue
        match = text.NUMERAL.fullmatch(part)
        if not match or match['root'].lower() not in ('i', 'ii', 'iii', 'iv', 'v', 'vi', 'vii') or match['figures'] not in INVERSIONS:
            return label
        converted.append(match['accidental'].translate(text.SYMBOLS) + match['root']
                         + text.QUALITIES.get(match['quality'], '') + INVERSIONS[match['figures']])
    return '/'.join(converted) + (' ' + note if note else '')


@dataclass
class FiguredBass:
    """Lines from top to bottom; text joins them with '/', ready for plain text.

    bass is a spelled pitch name, without octave. bass_accidental is the sign
    needed on that note relative to the key signature, never a figure line.
    note is the untouched explanatory suffix, separate from the figure stack.
    """

    lines: list[str]
    bass: str
    bass_accidental: str
    note: str = ''

    @property
    def text(self) -> str:
        return '/'.join(self.lines)


def figured_bass(label: str, key: str) -> FiguredBass:
    """Derive conventional shortened figures from spelled chord tones.

    Requires an explicit active key; unsupported forms raise ValueError rather
    than silently supplying figures for an invented or truncated chord.
    """
    from music21 import exceptions21, key as keys, roman

    parts, note = _parts(label)
    for part in parts:
        if not _supported(part):
            raise ValueError(f'Unsupported figured-bass label: {label!r}')
    if not key or not re.fullmatch(r'[A-Ga-g][b#♭♯-]*', key):
        raise ValueError(f'Invalid active key: {key!r}')
    try:
        active = keys.Key(key[:1] + key[1:].translate(str.maketrans({'b': '-', '♭': '-', '♯': '#'})))
    except exceptions21.Music21Exception as error:
        raise ValueError(f'Invalid active key: {key!r}') from error
    normalized = '/'.join(parts).replace('/o', 'ø').replace('°', 'o').replace('%', 'ø').translate(text.SYMBOLS)
    normalized = normalized.translate(str.maketrans({'♭': 'b', '♯': '#'}))
    # Match the stored-label semantics used by comparison and harmony.
    named = roman.RomanNumeral(normalized, active, sixthMinor=roman.Minor67Default.CAUTIONARY,
                               seventhMinor=roman.Minor67Default.CAUTIONARY)
    bass = named.bass()

    def accidental(pitch) -> str:
        actual = pitch.accidental.alter if pitch.accidental else 0
        signature = active.accidentalByStep(pitch.step)
        expected = signature.alter if signature else 0
        if actual == expected:
            return ''
        if actual not in ACCIDENTALS:
            raise ValueError(f'Unsupported accidental in {label!r}')
        return ACCIDENTALS[actual]

    intervals = {}
    for pitch in named.pitches:
        if pitch == bass:
            continue
        figure = (pitch.diatonicNoteNum - bass.diatonicNoteNum) % 7 + 1
        if figure != 1:
            intervals[figure] = accidental(pitch)
    # Augmented sixths need their actual 6/5/3 or 6/4/3, not the
    # inversion of an enharmonically interpreted seventh chord.
    if parts[0].startswith(('It', 'Fr', 'Ger')):
        show = set(intervals)
    else:
        seventh = len(named.pitches) == 4
        show = ({0: {7}, 1: {6, 5}, 2: {4, 3}, 3: {4, 2}} if seventh else {0: set(), 1: {6}, 2: {6, 4}})[named.inversion()]
    show |= {figure for figure, sign in intervals.items() if sign}
    lines = [intervals.get(figure, '') + str(figure) for figure in sorted(show, reverse=True)]
    return FiguredBass(lines, bass.name.replace('-', 'b'), accidental(bass), note)
