"""The "check my analysis" page: the student's labels in one row, the tool's reading under it only where it differs."""

from engine import notation, text
from engine.annotations import AnnotationList, Position
from engine.overlay import INK, NUMERAL_SIZE, SMALL_SIZE, Box, NotOnPage

TOOL_COLOR = '#4477AA'
AGREE_COLOR = '#228833'
GAP = 110  # clear space between neighbouring labels, as in the normal page's numeral row

NOTES = {
    'different_chord': 'the tool reads a different chord here. Compare the notes of the chord with each label.',
    'different_key': 'the tool reads the key differently here. Check which key the chord belongs to.',
}


def reserve(results):
    """Hidden numerals the size of the real ones, so bars widen as they do on a normal page."""
    def widest(item):
        return max((item['student']['figure'], item['reviewed']['figure']),
                   key=lambda figure: notation.numeral(figure, None, 'current', NUMERAL_SIZE)[1])
    return AnnotationList.model_validate({'version': 1, 'annotations': [
        {'type': 'harmony', 'at': item['at'], 'label': widest(item)} for item in results]})


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


def draw(layout, results):
    groups = {}
    for item in results:
        try:
            system, x = layout.x_of(Position(**item['at']))
        except NotOnPage:
            continue
        groups.setdefault(system.index, []).append((x, item))
    number = 0
    shown_key = None  # the student's key as last written, carried from one line to the next
    bottom = 0
    for system_index, items in groups.items():
        system = layout.systems[system_index]
        first = system.bottom() + 170 + NUMERAL_SIZE * 0.75
        second = first + 600
        cursor = system.left
        notes = []
        tool_key = None
        key_note = None  # consecutive key differences share one note, but each line carries its own
        for position, (x, item) in enumerate(items):
            student, tool, cls = item['student'], item['reviewed'], item['classification']
            x = max(x - 30, cursor)
            row, below = [], []
            if student['key'] != shown_key:
                row.append(_key(layout, x, first, student['key']))
                shown_key = student['key']
            figure_x = row[-1].right + 90 if row else x
            row.append(_numeral(layout, figure_x, first, student['figure'], student['key']))
            if cls in ('agrees', 'same_chord_different_spelling'):
                row.append(_tick(layout, row[-1].right + 90, first))
            else:
                if cls == 'different_inversion':
                    row.append(layout._text(row[-1].right + 70, first, '?', NUMERAL_SIZE, bold=True))
                else:
                    if cls == 'different_chord' or key_note != tool['key']:
                        number += 1
                        notes.append(f'[{number}] Bar {item["at"]["measure"]}, beat {item["at"]["beat"]:g}: {NOTES[cls]}')
                    key_note = tool['key'] if cls == 'different_key' else None
                    row.append(layout._text(row[-1].right + 70, first, f'[{number}]', SMALL_SIZE))
                if tool['key'] != student['key'] and tool['key'] != tool_key:
                    below.append(_key(layout, figure_x, second, tool['key'], TOOL_COLOR))
                    tool_key = tool['key']
                elif tool['key'] == student['key']:
                    tool_key = None
                at = below[-1].right + 90 if below else figure_x
                below.append(_numeral(layout, at, second, tool['figure'], tool['key'], TOOL_COLOR))
            cursor = max(box.right for box in row + below) + 2 * GAP
        y = second + 800
        bottom = y
        for note in notes:
            layout._text(system.left, y, note, SMALL_SIZE)
            y += 430
            bottom = y
    _legend(layout, bottom + 120 if bottom else None)


def _legend(layout, y):
    if y is None:
        return
    x = layout.systems[-1].left
    _tick(layout, x, y + 40, register=False)
    pieces = [(INK, 'agrees with the tool'), (INK, '·'), (TOOL_COLOR, 'blue: the tool\'s reading where it differs'), (INK, '·'),
              (INK, '? check the bass (which note is lowest)'), (INK, '·'), (INK, '[1] see note below')]
    x += 330
    for color, string in pieces:
        x = layout._text(x, y, string, SMALL_SIZE, fill=color).right + 130
