"""The "check my analysis" page: the student's labels in one row, the tool's reading under it only where it differs."""

import math
import re
from dataclasses import asdict
from xml.sax.saxutils import escape

from engine import check_analysis, notation, text
from engine.annotations import AnnotationList, Position
from engine.comparison import from_annotations
from engine.overlay import INK, NUMERAL_SIZE, SMALL_SIZE, Box, NotOnPage

TOOL_COLOR = '#4477AA'
AGREE_COLOR = '#228833'
GAP = 110  # clear space between neighbouring labels, as in the normal page's numeral row
ROW = 600  # from the student's baseline to the tool's
NOTE_LINE = 430
ROOM_LINE = 390  # what Verovio sets aside for each line of a hidden two-line direction
VEROVIO_BASE = 1250  # what the hidden numeral measures before any padding (measured; hardly varies with the figure)
NBSP = 243  # width of one non-breaking space in the hidden numerals Verovio sets (measured)

DIFFERS = ('different_chord', 'different_key', 'different_inversion')
UNLABELLED = 'unlabelled'  # the tool has a chord here and the student wrote nothing
UNCHECKED = 'unchecked'  # the student's label comes before the tool's first, so there is nothing to compare

NOTES = {
    'different_chord': 'the tool reads a different chord here. Compare the notes of the chord with each label.',
    'different_chord_and_key': 'the tool reads a different chord and a different key here. Compare the notes of the chord, and check which key it belongs to.',
    'different_key': 'the tool reads the key differently here. Check which key the chord belongs to.',
}


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
    return sorted(results, key=lambda item: (item['at']['measure'], item['at']['beat']))


def _key_width(key):
    return text.width(text.pretty_key(key) + ':', NUMERAL_SIZE, bold=True) + 90


def _numeral_width(figure, key):
    return notation.numeral(figure, key, 'current', NUMERAL_SIZE)[1]


def _mark_width(item, marks):
    cls = item['classification']
    if cls in ('agrees', 'same_chord_different_spelling'):
        return 90 + 220
    if cls == 'different_inversion':
        return 70 + text.width('?', NUMERAL_SIZE, bold=True)
    if cls in ('different_chord', 'different_key'):
        return 70 + text.width(f'[{marks}]', SMALL_SIZE)
    return 0


def _mark_count(results):
    return sum(item['classification'] in ('different_chord', 'different_key') for item in results)  # no note number is larger


def _row_widths(results, shown=None, marks=None, carry_blue=True):
    """Per entry, the width of the student's row and of the tool's, with the keys that precede them.

    Without carry_blue, every blue key that differs from the student's is counted: reserve() does not
    know where lines break, and draw() prints the tool's key again at the start of each line."""
    blue, widths = None, []
    if marks is None:
        marks = _mark_count(results)
    for item in results:
        student, tool = item['student'], item['reviewed']
        top = bottom = 0.0
        if not carry_blue:
            blue = None
        if student:
            if student['key'] != shown:
                top += _key_width(student['key'])
                shown = student['key']
                blue = None  # a key just written in black is the one the reader now assumes
            top += _numeral_width(student['figure'], student['key']) + _mark_width(item, marks)
        if tool:
            if tool['key'] != (blue or shown):
                bottom += _key_width(tool['key'])
                blue = tool['key']
            if not student or item['classification'] in DIFFERS:
                bottom += _numeral_width(tool['figure'], tool['key'])
        widths.append((top, bottom))
    return widths


def reserve(results):
    """Hidden numerals as wide as what is drawn under them, so a bar with several labels widens as on a normal page."""
    annotations = []
    for item, (top, bottom) in zip(results, _row_widths(results, carry_blue=False)):
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


def _numeral(layout, x, baseline, figure, key, color=INK):
    chunks, total = notation.numeral(figure, key, 'current', NUMERAL_SIZE)
    boxes = [layout._text(x + c.dx, baseline + c.dy, c.text, c.size, bold=c.bold, fill=color) for c in chunks]
    box = Box(x, min(b.y for b in boxes), total, max(b.bottom for b in boxes) - min(b.y for b in boxes))
    layout.harmony_labels.append((figure, box))
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


def _legend_pieces(results, key_only=False):
    classes = {item['classification'] for item in results}
    pieces = []
    if classes & {'agrees', 'same_chord_different_spelling'}:
        pieces.append('agrees with the tool')
    if classes & set(DIFFERS):
        pieces.append("blue: the tool's reading where it differs")
    if key_only:
        pieces.append("blue key alone: where the tool's key changes")
    if UNLABELLED in classes:
        pieces.append("blue on its own: a chord you didn't label")
    if UNCHECKED in classes:
        pieces.append('no mark: the tool has no chord there to compare')
    if 'different_inversion' in classes:
        pieces.append('? check the bass (which note is lowest)')
    if classes & {'different_chord', 'different_key'}:
        pieces.append('[1] numbered note under the line')
    return pieces


def _span(start, end):
    if start == end:
        return f'Bar {start["measure"]}, beat {start["beat"]:g}'
    if start['measure'] == end['measure']:
        return f'Bar {start["measure"]}, beats {start["beat"]:g}–{end["beat"]:g}'
    return f'Bar {start["measure"]} beat {start["beat"]:g} to bar {end["measure"]} beat {end["beat"]:g}'


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
    key_only = False  # a blue key with no numeral: the tool's key changes under a label that agrees
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
        notes = []
        blue_key = None  # the last key printed in blue on this line; before one, the student's key is what the reader assumes
        run = None  # (tool key, note number) of the key differences just before this entry
        blue = any(bottom for _, bottom in widths)
        for (x, item), start in zip(items, starts):
            student, tool, cls = item['student'], item['reviewed'], item['classification']
            x = max(start, cursor)
            row, below = [], []
            if student:
                at = x
                if student['key'] != shown_key:
                    row.append(_key(layout, at, first, student['key']))
                    shown_key = student['key']
                    blue_key = None
                    at = row[-1].right + 90
                row.append(_numeral(layout, at, first, student['figure'], student['key']))
                if cls != 'different_key':
                    run = None
                if cls in ('agrees', 'same_chord_different_spelling'):
                    row.append(_tick(layout, row[-1].right + 90, first))
                elif cls == 'different_inversion':
                    row.append(layout._text(row[-1].right + 70, first, '?', NUMERAL_SIZE, bold=True))
                elif cls in ('different_chord', 'different_key'):
                    if cls == 'different_key' and run and run[0] == tool['key']:
                        mark = run[1]
                        notes[-1][2] = item['at']
                    else:
                        number += 1
                        mark = number
                        kind = cls
                        if cls == 'different_chord' and tool['key'] != student['key']:
                            kind = 'different_chord_and_key'
                        notes.append([number, item['at'], item['at'], NOTES[kind]])
                    run = (tool['key'], mark) if cls == 'different_key' else None
                    row.append(layout._text(row[-1].right + 70, first, f'[{mark}]', SMALL_SIZE))
            if tool:
                at = x
                if tool['key'] != (blue_key or shown_key):
                    below.append(_key(layout, at, second, tool['key'], TOOL_COLOR))
                    blue_key = tool['key']
                    at = below[-1].right + 90
                    key_only = key_only or (student and cls not in DIFFERS)
                if not student or cls in DIFFERS:
                    below.append(_numeral(layout, at, second, tool['figure'], tool['key'], TOOL_COLOR))
            cursor = max(box.right for box in row + below) + 2 * GAP
        y = (second if blue else first) + 700
        for number_, start, end, note in notes:
            layout._text(system.left, y, f'[{number_}] {_span(start, end)}: {note}', SMALL_SIZE)
            bottom = y + 120
            y += NOTE_LINE
        bottom = max(bottom, (second if blue else first) + 200)
        deficits[system_index] = bottom
    last = max(groups) if groups else None
    if last_page and last is not None:
        bottom = _legend(layout, deficits[last] + NOTE_LINE, _legend_pieces(results, key_only))
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
        lead = 330 if string == 'agrees with the tool' else 0
        dot = text.width('·', SMALL_SIZE) + 260 if position else 0
        if x + dot + lead + text.width(string, SMALL_SIZE) > system.right and x > start:
            x, y, dot = start, y + NOTE_LINE, 0
        if dot:
            x = layout._text(x + 130, y, '·', SMALL_SIZE).right
        if lead:
            _tick(layout, x, y + 40, register=False)
        color = TOOL_COLOR if string.startswith('blue') else INK
        x = layout._text(x + lead + (130 if dot else 0), y, string, SMALL_SIZE, fill=color).right
    return y + 120
