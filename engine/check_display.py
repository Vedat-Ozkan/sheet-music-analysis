"""Optional comparison pages for owner review."""

from engine import text
from engine.annotations import AnnotationList, Position
from engine.overlay import NUMERAL_SIZE, SMALL_SIZE, Box, NotOnPage

STATUS = {
    'agrees': 'Agrees',
    'same_chord_different_spelling': 'Same notes',
    'different_inversion': 'Check bass',
    'different_chord': 'Check chord',
    'different_key': 'Check key',
}


def reading(item):
    return text.pretty_key(item['key']) + ': ' + item['figure']


def reserve(results):
    # Space for the wider reading and its mark before Verovio chooses line breaks.
    return AnnotationList.model_validate({'version': 1, 'annotations': [
        {'type': 'harmony', 'at': item['at'], 'label': max(
            (reading(item['student']), reading(item['reviewed']), STATUS[item['classification']]),
            key=lambda label: text.width(label, NUMERAL_SIZE),
        ) + '   9999'} for item in results
    ]})


def draw(layout, results, variant):
    groups = {}
    for item in results:
        try:
            system, x = layout.x_of(Position(**item['at']))
        except NotOnPage:
            continue
        groups.setdefault(system.index, []).append((x, item))
    number = 0
    for system_index, items in groups.items():
        system = layout.systems[system_index]
        top = system.bottom() + 430
        layout._text(system.left, top, 'Your reading (top) / tool reading (below) — discuss differences', SMALL_SIZE)
        baseline = top + 620
        cursor = system.left
        notes = []
        key_warning = None
        for x, item in items:
            cls = item['classification']
            error = item['is_error']
            significant = cls in ('different_chord', 'different_key')
            mark = STATUS[cls] if variant == 'guided' else ('check bass' if cls == 'different_inversion' else '')
            if significant and (cls != 'different_key' or key_warning != item['reviewed']['key']):
                number += 1
                key_warning = item['reviewed']['key'] if cls == 'different_key' else None
                advice = 'Check the local key before naming the chord.' if cls == 'different_key' else 'Compare the chord notes, including any accidentals.'
                notes.append(f'[{number}] Bar {item["at"]["measure"]}, beat {item["at"]["beat"]:g}: {advice}')
            if significant:
                mark += f' [{number}]'
            x = max(x - 30, cursor)
            student = layout._text(x, baseline, reading(item['student']), NUMERAL_SIZE)
            status = layout._text(student.right + 90, baseline, mark, SMALL_SIZE) if variant == 'compact' and mark else None
            boxes = [student] + ([status] if status else [])
            if variant == 'compact' and not error:
                # A vector tick avoids depending on a font's symbol coverage.
                left, y = student.right + 90, baseline - 200
                layout._add('path', d=f'M{left:g},{y:g} l70,90 l150,-210',
                            fill='none', stroke='#228833', stroke_width=30,
                            **{'class': 'agreement-mark'})
                tick = Box(left, y - 120, 220, 210)
                layout.harmony_labels.append(('agreement mark', tick))
                boxes.append(tick)
            if variant == 'guided' or cls != 'agrees':
                boxes.append(layout._text(x, baseline + 600, reading(item['reviewed']), NUMERAL_SIZE, fill='#4477AA'))
            if variant == 'guided':
                boxes.append(layout._text(x, baseline + 1100, mark, SMALL_SIZE, fill='#555555'))
            cursor = max(box.right for box in boxes) + 180
        y = baseline + (1750 if variant == 'guided' else 1250)
        for note in notes:
            layout._text(system.left, y, note, SMALL_SIZE)
            y += 430
