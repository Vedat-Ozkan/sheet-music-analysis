"""The "check my analysis" page: the student's labels in one row, the tool's reading under it only where it differs."""

import math
import re
from dataclasses import asdict
from xml.sax.saxutils import escape

from engine import check_analysis, notation, text
from engine.annotations import AnnotationList, Position
from engine.comparison import from_annotations
from engine.overlay import INK, NUMERAL_SIZE, Box, NotOnPage

ERROR = '#D50000'  # the teacher's red pen: everything the tool writes is a correction
AGREE_COLOR = '#228833'
# A key-only difference is not a fault in the student's chord, so it is not red; grey ink is the margin pencil beside the red pen.
NEUTRAL = '#555555'
GAP = 110  # clear space between neighbouring labels, as in the normal page's numeral row
ROW = 640  # from the student's baseline to the tool's
SIZE = 330  # smallest text that reads at chat size (about 11 px)
STROKE = 30  # the spec's stroke for rings and underlines
CORNER = 120  # ring corner radius: small enough that the corners of a stacked figure's text box stay inside
KEY_CLEAR = 40  # extra space between a key label and a ring that follows it
RING_PAD = 60  # clear space between a label and the ring round it
NOTE_LINE = 500
ROOM_LINE = 390  # what Verovio sets aside for each line of a hidden two-line direction
VEROVIO_BASE = 1250  # what the hidden numeral measures before any padding (measured; hardly varies with the figure)
NBSP = 243  # width of one non-breaking space in the hidden numerals Verovio sets (measured)

DIFFERS = ('different_chord', 'different_key', 'different_inversion')
UNLABELLED = 'unlabelled'  # the tool has a chord here and the student wrote nothing
UNCHECKED = 'unchecked'  # the student's label comes before the tool's first, so there is nothing to compare

NOTES = {
    'different_chord': 'the tool reads a different chord here. Check the notes of the chord against your label.',
    'different_chord_and_key': 'the tool reads a different chord and key here. Check the notes of the chord, then its key.',
}
FOOT = {UNLABELLED: "? = you didn't label this chord; the tool's reading is below it", UNCHECKED: 'no mark = the tool has no chord there to compare'}


def compare(student, reviewed, index):
    """The student's labels checked against the tool's, plus the tool's chords the student skipped."""
    reference = check_analysis._finish(
        [item for item in from_annotations(reviewed) if item.measure in {m.number for m in index.measures}], index)
    first = (reference[0].measure, reference[0].beat)
    student = check_analysis._finish(student, index)
    results = check_analysis.compare_labels([s for s in student if (s.measure, s.beat) >= first], reference, index)
    results += [{'at': {'measure': s.measure, 'beat': s.beat}, 'student': asdict(s), 'reviewed': None,
                 'classification': UNCHECKED, 'is_error': False} for s in student if (s.measure, s.beat) < first]
    written = {(s.measure, s.beat) for s in student}
    results += [{'at': {'measure': r.measure, 'beat': r.beat}, 'student': None, 'reviewed': asdict(r),
                 'classification': UNLABELLED, 'is_error': False} for r in reference if (r.measure, r.beat) not in written]
    style = reviewed.get('style', 'current')  # carried on each result so the page draws labels as the analysis does
    return sorted(({**item, 'style': style} for item in results), key=lambda item: (item['at']['measure'], item['at']['beat']))


def _key_width(key):
    return text.width(text.pretty_key(key) + ':', NUMERAL_SIZE, bold=True) + 90


def _numeral_width(figure, key, style):
    return notation.numeral(figure, key, style, NUMERAL_SIZE)[1]


def _mark_width(item, marks):
    cls = item['classification']
    if cls in ('agrees', 'same_chord_different_spelling'):
        return 90 + 220
    number = 40 + text.width(str(marks), SIZE, bold=True)
    if cls == 'different_chord':
        return 2 * RING_PAD + number
    if cls == 'different_key':
        return number
    if cls == 'different_inversion':
        return _slot(item)
    return 0


def _slot(item):
    """Room right of a root-position numeral for the underline that stands where its missing figure would be."""
    student = item['student']
    chunks = notation.numeral(student['figure'], student['key'], item['style'], NUMERAL_SIZE)[0]
    return 0 if _figure_indices(chunks, item['style']) else 30 + text.width('6', NUMERAL_SIZE * text.FIGURE)


def _figure_indices(chunks, style):
    """Which chunks of a numeral are its inversion figure: the raised or stacked digits, or the ABRSM letter."""
    return [i for i, c in enumerate(chunks)
            if c.size < NUMERAL_SIZE or (style == 'abrsm' and c.dx > 0 and c.text in ('b', 'c', 'd'))]


def _mark_count(results):
    return sum(item['classification'] in ('different_chord', 'different_key') for item in results)  # no note number is larger


def _row_widths(results, shown=None, marks=None, carry_key=True):
    """Per entry, the width of the student's row and of the tool's, with the keys that precede them.

    Without carry_key, every red key that differs from the student's is counted: reserve() does not
    know where lines break, and draw() prints the tool's key again at the start of each line."""
    tool_key, widths = None, []
    if marks is None:
        marks = _mark_count(results)
    for item in results:
        student, tool, style = item['student'], item['reviewed'], item['style']
        top = bottom = 0.0
        if not carry_key:
            tool_key = None
        if student:
            if student['key'] != shown:
                top += _key_width(student['key']) + KEY_CLEAR * (item['classification'] == 'different_chord')
                shown = student['key']
                tool_key = None  # a key just written in black is the one the reader now assumes
            top += _numeral_width(student['figure'], student['key'], style) + _mark_width(item, marks)
        elif tool:
            top += text.width('?', NUMERAL_SIZE, bold=True)
        if tool and (not student or item['classification'] in DIFFERS):
            if tool['key'] != (tool_key or shown):
                bottom += _key_width(tool['key'])
                tool_key = tool['key']
            bottom += _numeral_width(tool['figure'], tool['key'], style)
        widths.append((top, bottom))
    return widths


def reserve(results):
    """Hidden numerals as wide as what is drawn under them, so a bar with several labels widens as on a normal page."""
    annotations = []
    for item, (top, bottom) in zip(results, _row_widths(results, carry_key=False)):
        shown = item['student'] or item['reviewed']
        needed = max(top, bottom) + GAP
        filler = max(0, math.ceil((needed - VEROVIO_BASE) / NBSP))
        annotations.append({'type': 'harmony', 'at': item['at'], 'label': shown['figure'] + ' ' * filler})
    return AnnotationList.model_validate({'version': 1, 'annotations': annotations})


def with_room(mei, lines, bottom_staff):
    """The MEI with a hidden direction of that many lines under the first bar of each system that needs room."""
    for measure_id, count in lines.items():
        end = mei.index('</measure>', mei.index(f'xml:id="{measure_id}"'))
        room = f'<dir staff="{bottom_staff}" tstamp="1" place="below" type="analysis-room">-{"<lb/>-" * count}</dir>'
        mei = mei[:end] + room + mei[end:]
    return mei


def _numeral(layout, x, baseline, figure, key, style, color=INK, underline=False, register=True, label=None):
    chunks, total = notation.numeral(figure, key, style, NUMERAL_SIZE)
    boxes = [layout._text(x + c.dx, baseline + c.dy, c.text, c.size, bold=c.bold, fill=color) for c in chunks]
    box = Box(x, min(b.y for b in boxes), total, max(b.bottom for b in boxes) - min(b.y for b in boxes))
    if underline:
        # Only the figure is wrong. A root-position label has none, so the underline stands right of the numeral where
        # the figure would go: underlining the numeral itself would sit on the tool's numeral below and read as a fraction.
        shown = [(chunks[i], boxes[i]) for i in _figure_indices(chunks, style)]
        if shown:
            left, right = min(b.x for _, b in shown), max(b.right for _, b in shown)
            y = max(b.bottom for _, b in shown) + 50
        else:
            left = box.right + 30
            right = left + text.width('6', NUMERAL_SIZE * text.FIGURE)
            y = box.bottom + 50
            box = Box(box.x, box.y, right - box.x, box.height)
        layout._add('path', d=f'M{left:g},{y:g} H{right:g}', fill='none', stroke=ERROR, stroke_width=STROKE,
                    stroke_linecap='round', **{'class': 'inversion-underline'})
    if register:
        layout.harmony_labels.append((label or figure, box))
    return box


def _ring(layout, box):
    """A red-pen ring round a wrong label. A rounded rectangle, not an ellipse or stadium, so a stacked figure's
    corners stay inside and the ring needs no more room than its box."""
    x, y, w, h = box.x - RING_PAD, box.y - RING_PAD, box.width + 2 * RING_PAD, box.height + 2 * RING_PAD
    layout._add('rect', x=f'{x:g}', y=f'{y:g}', width=f'{w:g}', height=f'{h:g}', rx=CORNER, fill='none',
                stroke=ERROR, stroke_width=STROKE, **{'class': 'wrong-label-ring'})
    box = Box(x, y, w, h)
    layout.harmony_labels.append(('wrong-label ring', box))
    return box


def _key(layout, x, baseline, key, color=INK):
    box = layout._text(x, baseline, text.pretty_key(key) + ':', NUMERAL_SIZE, bold=True, fill=color)
    layout.harmony_labels.append((key + ':', box))
    return box


def _tick(layout, left, baseline, register=True):
    # A vector tick avoids depending on a font's symbol coverage.
    y = baseline - 200
    layout._add('path', d=f'M{left:g},{y:g} l70,90 l150,-210', fill='none', stroke=AGREE_COLOR,
                stroke_width=30, **{'class': 'agreement-mark'})
    box = Box(left, y - 120, 220, 210)
    if register:
        layout.harmony_labels.append(('agreement mark', box))
    return box


def _legend_pieces(results):
    classes = {item['classification'] for item in results}
    pieces = []
    if classes & {'agrees', 'same_chord_different_spelling'}:
        pieces.append('agrees')
    if 'different_chord' in classes:
        pieces.append('ring = a different chord (see note)')
    if 'different_inversion' in classes:
        pieces.append('underline = check the inversion')
    return pieces


def _foot_lines(results):
    classes = {item['classification'] for item in results}
    return [FOOT[c] for c in (UNLABELLED, UNCHECKED) if c in classes]


def _plain(figure):
    """A numeral typed in running text: the stacked figures as 6/5, since a note line has no raised digits."""
    return re.sub(r'(?<=[A-Za-z°øo])(65|43|42|64)(?!\d)', lambda m: f'{m[1][0]}/{m[1][1]}', figure)


def _key_name(key):
    return text.pretty_key(key[0].upper() + key[1:]) + (' major' if key[0].isupper() else ' minor')


def _key_note(pairs):
    """E.g. "the tool hears this in C major: III in A minor = I in C." for the chords of a key-only run."""
    pairs = list(dict.fromkeys(pairs))
    tool_key = pairs[0][3]
    student_keys = {s_key for _, s_key, _, _ in pairs}
    tool_short = text.pretty_key(tool_key) if tool_key[0].isupper() else _key_name(tool_key)
    if len(student_keys) == 1:
        (student_key,) = student_keys
        pairs_text = ', '.join(f'{_plain(s)} = {_plain(t)}' for s, _, t, _ in pairs)
        if len(pairs) == 1:
            pairs_text = f'{_plain(pairs[0][0])} in {_key_name(student_key)} = {_plain(pairs[0][2])} in {tool_short}'
        else:
            pairs_text += f' ({_key_name(student_key)} to {_key_name(tool_key)})'
    else:
        pairs_text = ', '.join(f'{_plain(s)} in {_key_name(k)} = {_plain(t)} in {tool_short}' for s, k, t, _ in pairs)
    return f'the tool hears this in {_key_name(tool_key)}: {pairs_text}.'


def _span(start, end):
    if start == end:
        return f'Bar {start["measure"]}, beat {start["beat"]:g}'
    if start['measure'] == end['measure']:
        return f'Bar {start["measure"]}, beats {start["beat"]:g}–{end["beat"]:g}'
    return f'Bar {start["measure"]} beat {start["beat"]:g} to bar {end["measure"]} beat {end["beat"]:g}'


def _wrap(string, width):
    lines, line = [], ''
    for word in string.split():
        if line and text.width(f'{line} {word}', SIZE) > width:
            lines.append(line)
            line = word
        else:
            line = f'{line} {word}'.strip()
    lines.append(line)
    if len(lines) > 1 and ' ' not in lines[-1]:  # never leave one word alone on the last line
        head, _, tail = lines[-2].rpartition(' ')
        lines[-2:] = [head, f'{tail} {lines[-1]}']
    return lines


def _starts(xs, widths, left, right):
    """Where each label of a system begins: under its chord, but crowded back from the right edge, because Verovio
    sets no room past a system's last note and a long final label would run over the barline."""
    placed = []
    for x, (top, bottom) in zip(xs, widths):
        placed.append(max(x - 30, placed[-1] + max(widths[len(placed) - 1]) + 2 * GAP if placed else left))
    limit = right
    for i in reversed(range(len(placed))):
        placed[i] = max(left, min(placed[i], limit - max(widths[i])))
        limit = placed[i] - 2 * GAP
    return placed


def draw(layout, results, last_page=True):
    """Draw the page; returns, for the first bar of each system, how many more lines of room it needs."""
    groups = {}
    for item in results:
        try:
            system, x = layout.x_of(Position(**item['at']))
        except NotOnPage:
            continue
        groups.setdefault(system.index, []).append((x, item))
    results = [item for items in groups.values() for _, item in items]  # what this page shows
    number = 0
    shown_key = None  # the student's key as last written, carried from one line to the next
    deficits = {}
    bottom = 0
    for system_index, items in groups.items():
        system = layout.systems[system_index]
        first = system.bottom() + 170 + NUMERAL_SIZE * 0.75
        second = first + ROW
        cursor = system.left
        widths = _row_widths([item for _, item in items], shown_key, _mark_count(results))
        starts = _starts([x for x, _ in items], widths, cursor, system.right)
        notes = []  # [number, start, end, text or key-run pairs, colour]
        tool_shown = None  # the last key printed in the tool's row on this line; before one, the student's key is what the reader assumes
        run = None  # the open note of the key-only run just before this entry
        has_below = any(bottom for _, bottom in widths)
        for (x, item), start in zip(items, starts):
            student, tool, cls, style = item['student'], item['reviewed'], item['classification'], item['style']
            x = max(start, cursor)
            row, below = [], []
            if student:
                at = x
                ringed = cls == 'different_chord'
                if student['key'] != shown_key:
                    row.append(_key(layout, at, first, student['key']))
                    shown_key = student['key']
                    tool_shown = None
                    at = row[-1].right + 90 + KEY_CLEAR * ringed
                at += RING_PAD * ringed
                row.append(_numeral(layout, at, first, student['figure'], student['key'], style,
                                    underline=cls == 'different_inversion', register=not ringed))
                if cls != 'different_key':
                    run = None
                if cls in ('agrees', 'same_chord_different_spelling'):
                    row.append(_tick(layout, row[-1].right + 90, first))
                elif ringed:
                    row[-1] = _ring(layout, row[-1])
                    number += 1
                    kind = 'different_chord_and_key' if tool['key'] != student['key'] else cls
                    notes.append([number, item['at'], item['at'], NOTES[kind], ERROR])
                    # Raised like a footnote number, clear of the ring.
                    row.append(layout._text(row[-1].right + 40, first - 120, str(number), SIZE, bold=True, fill=ERROR))
                elif cls == 'different_key':
                    # The student's chord is right, so: no ring, no tick, and one neutral note for the whole run.
                    pair = (student['figure'], student['key'], tool['figure'], tool['key'])
                    if run and run[3][0][3] == tool['key']:
                        run[2] = item['at']
                        run[3].append(pair)
                    else:
                        number += 1
                        run = [number, item['at'], item['at'], [pair], NEUTRAL]
                        notes.append(run)
                        row.append(layout._text(row[-1].right + 40, first - 120, str(number), SIZE, bold=True, fill=NEUTRAL))
            else:
                row.append(layout._text(x, first, '?', NUMERAL_SIZE, bold=True, fill=ERROR))
            if tool and (not student or cls in DIFFERS):
                color = NEUTRAL if cls == 'different_key' else ERROR
                at = x
                if tool['key'] != (tool_shown or shown_key):
                    below.append(_key(layout, at, second, tool['key'], color))
                    tool_shown = tool['key']
                    at = below[-1].right + 90
                below.append(_numeral(layout, at, second, tool['figure'], tool['key'], style, color, label='tool ' + tool['figure']))
            cursor = max(box.right for box in row + below) + 2 * GAP
        y = (second if has_below else first) + 700
        for number_, start, end, note, color in notes:
            if not isinstance(note, str):
                note = _key_note(note)
            at = layout._text(system.left, y, str(number_), SIZE, bold=True, fill=color).right + 110
            for line in _wrap(f'{_span(start, end)}: {note}', system.right - at):
                layout._text(at, y, line, SIZE)
                bottom = y + 140
                y += NOTE_LINE
        bottom = max(bottom, (second if has_below else first) + 250)
        deficits[system_index] = bottom
    last = max(groups) if groups else None
    if last_page and last is not None:
        bottom = deficits[last] + NOTE_LINE
        for line in _foot_lines(results):
            for part in _wrap(line, layout.systems[-1].right - layout.systems[-1].left):
                layout._text(layout.systems[-1].left, bottom, part, SIZE)
                bottom += NOTE_LINE
        bottom = _legend(layout, bottom, _legend_pieces(results))
        deficits[last] = bottom
    needs = {}
    for system_index, bottom in deficits.items():
        if system_index + 1 < len(layout.systems):
            gap = bottom + 250 - layout.systems[system_index + 1].top()
        else:
            gap = bottom + 300 - _page_room(layout)
        if gap > 0:
            needs[layout.systems[system_index].measures[0].id] = math.ceil(gap / ROOM_LINE)
    return needs


def _page_room(layout):
    """The page's height in the coordinates the overlay draws in, less the margin it keeps clear at the foot."""
    height = float(next(e for e in layout.root.iter() if e.get('class') == 'definition-scale').get('viewBox').split()[3])
    top = float(re.search(r'translate\([-\d.]+,\s*([-\d.]+)', layout.canvas.get('transform')).group(1))
    return height - top - 1000


def _legend(layout, y, pieces):
    if not pieces:
        return y
    system = layout.systems[-1]
    x, start = system.left, system.left
    for position, string in enumerate(pieces):
        lead = 330 if string == 'agrees' else 0
        dot = text.width('·', SIZE) + 260 if position else 0
        if x + dot + lead + text.width(string, SIZE) > system.right and x > start:
            x, y, dot = start, y + NOTE_LINE, 0
        if dot:
            x = layout._text(x + 130, y, '·', SIZE).right
        if lead:
            _tick(layout, x, y + 40, register=False)
        x = layout._text(x + lead + (130 if dot else 0), y, string, SIZE).right
    return y + 140
