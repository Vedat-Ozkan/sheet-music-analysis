"""Read student Roman numerals and compare them with a reviewed annotation list."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import asdict
from fractions import Fraction

from music21 import key as m21key

from engine.comparison import Label, from_annotations, matches, sounding
from engine.score import ScoreIndex, beat_length

KEY_NAME = r"[A-Ga-g][#b♯♭-]*(?:\s+(?:major|minor|maj|min))?"
ROMAN = re.compile(r"[#b-]*(?:VII|III|VI|IV|II|V|I|vii|iii|vi|iv|ii|v|i)(?:o|ø|\+)?M?(?:753|53|65|64|43|42|13|11|9|7|6|2)?")
TOKEN = re.compile(
    rf"(?P<bar>\b(?:bar|measure|m\.?)\s*(\d+)(?:\.(\d+(?:\.\d+)?))?)"
    rf"|(?P<beat>\b(?:beat|b\.?)\s*(\d+(?:\.\d+)?))"
    rf"|(?P<key>\b(?:key\s*:?|in)\s*({KEY_NAME})\s*:?)"
    rf"|(?P<shortkey>{KEY_NAME}\s*:)"
    r"|(?P<label>[^\s,;:]+)", re.IGNORECASE,
)


def _key(text: str) -> str:
    parts = text.strip().replace('♯', '#').replace('♭', 'b').replace('-', 'b').split()
    name = parts[0]
    if len(parts) > 1:
        name = name.lower() if parts[1].lower().startswith('min') else name[0].upper() + name[1:]
    if sounding(name, 'I') is None:
        raise ValueError(f"Cannot read key {text!r}")
    return name


def _figure(text: str, key: str) -> str:
    figure = text.replace('°', 'o').replace('♯', '#').replace('♭', 'b')
    match = re.fullmatch(r"([#b-]*[ivIV]+[oø+]?)(7?)([abcd])(/.*)?", figure)
    if match:
        head, seventh, letter, target = match.groups()
        figures = ('7', '65', '43', '42') if seventh else ('', '6', '64')
        inversion = 'abcd'.index(letter)
        if inversion >= len(figures):
            raise ValueError(f"Invalid triad inversion in {text!r}")
        figure = head + figures[inversion] + (target or '')
    parts = figure.replace('/o', 'ø').split('/')
    valid = all(ROMAN.fullmatch(part) for part in parts)
    if not valid and figure not in ('N', 'N6', 'Cad64', 'It6', 'Ger6', 'Ger65', 'Fr6', 'Fr43'):
        raise ValueError(f"Cannot read Roman numeral {text!r} in {key}")
    if sounding(key, figure) is None:
        raise ValueError(f"Cannot read Roman numeral {text!r} in {key}")
    return figure


def _finish(labels: list[Label], index: ScoreIndex | None) -> list[Label]:
    found = {}
    for label in labels:
        if index:
            index.measure(label.measure).offset_of(label.beat)
        position = (label.measure, label.beat)
        if position in found and found[position] != label:
            raise ValueError(f"Conflicting labels at bar {label.measure} beat {label.beat:g}")
        found[position] = label
    if not found:
        raise ValueError('No Roman numeral labels found')
    return sorted(found.values(), key=lambda label: (label.measure, label.beat))


def from_text(text: str, default_key: str = 'C', index: ScoreIndex | None = None) -> list[Label]:
    """Unmarked successive labels occupy beats 1, 2, ...; an unaddressed key is the initial key."""
    tokens = list(TOKEN.finditer(text))
    key = _key(default_key)
    # A standalone "key: G major" often follows the student's answer rather than preceding it.
    for position, token in enumerate(tokens):
        addressed = position > 0 and tokens[position - 1].lastgroup in ('bar', 'beat')
        if token.lastgroup == 'key' and token.group().lower().startswith('key') and not addressed:
            key = _key(re.sub(r'^key\s*:?\s*', '', token.group(), flags=re.I).rstrip(':'))
            break
    labels, measure, beat = [], None, 1.0
    for position, token in enumerate(tokens):
        kind, value = token.lastgroup, token.group()
        if kind == 'bar':
            address = re.search(r'(\d+)(?:\.(\d+(?:\.\d+)?))?$', value)
            measure, beat = int(address[1]), float(address[2] or 1)
        elif kind == 'beat':
            beat = float(re.search(r'\d+(?:\.\d+)?$', value)[0])
        elif kind in ('key', 'shortkey'):
            key = _key(re.sub(r'^(?:key\s*:?|in)\s*', '', value, flags=re.I).rstrip(':'))
        else:
            if value in ('6', '64', '7', '65', '43', '42') and labels and labels[-1].measure == measure and position > 0 and tokens[position - 1].lastgroup == 'label':
                previous = labels.pop()
                labels.append(Label(previous.measure, previous.beat, previous.key, _figure(previous.figure + value, previous.key)))
                continue
            if measure is None:
                raise ValueError(f"Give a bar number before {value!r}")
            if beat < 1:
                raise ValueError(f"Beat must be at least 1 in bar {measure}")
            labels.append(Label(measure, beat, key, _figure(value, key)))
            beat += 1
    return _finish(labels, index)


def _xml_key(element: ET.Element) -> str:
    mode = element.findtext('mode') or element.findtext('numeral-mode') or 'major'
    if mode not in ('major', 'minor'):
        raise ValueError(f"Unsupported MusicXML key mode {mode!r}")
    fifths = element.findtext('fifths') or element.findtext('numeral-fifths')
    if fifths is None:
        raise ValueError('MusicXML key needs fifths and a major/minor mode')
    local = m21key.KeySignature(int(fifths)).asKey(mode)
    return local.tonic.name.replace('-', 'b').lower() if mode == 'minor' else local.tonic.name.replace('-', 'b')


def _numeral(harmony: ET.Element, key: str) -> tuple[str, str]:
    numeral = harmony.find('numeral')
    root = numeral.find('numeral-root')
    if root is None:
        raise ValueError('MusicXML numeral is missing numeral-root')
    local = numeral.find('numeral-key')
    if local is not None:
        key = _xml_key(local)
    degree = int(root.text or 0)
    if not 1 <= degree <= 7:
        raise ValueError(f"Invalid MusicXML numeral-root {degree}")
    kind = harmony.findtext('kind', 'major')
    kinds = {
        'major': ('', False, False), 'minor': ('', True, False),
        'augmented': ('+', False, False), 'diminished': ('o', True, False),
        'dominant': ('', False, True), 'major-seventh': ('M', False, True),
        'minor-seventh': ('', True, True), 'diminished-seventh': ('o', True, True),
        'half-diminished': ('ø', True, True), 'augmented-seventh': ('+', False, True),
    }
    if kind not in kinds or harmony.find('degree') is not None:
        raise ValueError(f"Unsupported MusicXML numeral kind/modification {kind!r}")
    quality, minor, seventh = kinds[kind]
    name = ('I', 'II', 'III', 'IV', 'V', 'VI', 'VII')[degree - 1]
    name = name.lower() if minor else name
    alteration = int(numeral.findtext('numeral-alter', '0'))
    accidental = '#' * alteration if alteration > 0 else 'b' * -alteration
    if key[0].islower():
        # XML alterations count from natural minor; RomanText has quality-dependent
        # raised vi/vii and flats that count from the major scale instead.
        local_key = m21key.Key(key.replace('b', '-'))
        desired = (local_key.pitchFromDegree(degree).pitchClass + alteration) % 12
        for shift in [0] + [n for size in range(1, abs(alteration) + 3) for n in (-size, size)]:
            prefix = '#' * shift if shift > 0 else 'b' * -shift
            candidate = sounding(key, prefix + name + quality)
            if candidate and candidate.root == desired:
                accidental = prefix
                break
        else:
            raise ValueError('Unsupported MusicXML numeral alteration')
    inversion = int(harmony.findtext('inversion', '0'))
    figures = ('7', '65', '43', '42') if seventh else ('', '6', '64')
    if not 0 <= inversion < len(figures):
        raise ValueError(f"Invalid MusicXML inversion {inversion} for {kind}")
    return key, _figure(accidental + name + quality + figures[inversion], key)


def from_musicxml(data: str | bytes, default_key: str = 'C', index: ScoreIndex | None = None) -> list[Label]:
    """Read partwise XML; ordinary song lyrics outside the bottom staff are ignored."""
    root = ET.fromstring(data)
    for element in root.iter():
        element.tag = element.tag.rsplit('}', 1)[-1]
    if root.tag != 'score-partwise':
        raise ValueError('Expected an uncompressed score-partwise MusicXML document')
    parts = root.findall('part')
    labels = []
    # Verovio supplies the same logical-bar/segment mapping used by export.
    # Plain numeric XML (including small student snippets) needs no toolkit.
    timing = index
    if timing is None and any(not m.get('number', '').lstrip('-').isdigit() for p in parts for m in p.findall('measure')):
        from engine.render import load_toolkit
        timing = ScoreIndex(load_toolkit(data).getMEI())
    segments = {s.index: (m, s) for m in timing.measures for s in m.segments} if timing else {}

    def read_label(text, number, beat, key):
        prefix = re.fullmatch(rf'\s*({KEY_NAME})\s*:\s*(\S+)\s*', text)
        if prefix:
            key, text = _key(prefix[1]), prefix[2]
        labels.append(Label(number, beat, key, _figure(text, key)))
        return key

    for part in parts:
        key, divisions, unit, staves = _key(default_key), 1, Fraction(1), 1
        for position, measure in enumerate(part.findall('measure'), 1):
            number = measure.get('number', '')
            bar, segment = segments.get(position, (None, None))
            if bar is not None:
                number = bar.number
            elif number.lstrip('-').isdigit():
                number = int(number)
            else:
                raise ValueError(f"Non-numeric MusicXML measure {number!r}; provide a numbered score")

            def beat_at(offset):
                return bar.beat_of(segment.start + offset) if bar else float(offset / unit + 1)
            cursor = previous = Fraction(0)
            pending = []
            for element in measure:
                if element.tag == 'attributes':
                    divisions = int(element.findtext('divisions', str(divisions)))
                    staves = int(element.findtext('staves', str(staves)))
                    time = element.find('time')
                    if time is not None:
                        unit = beat_length(int(time.findtext('beats')), int(time.findtext('beat-type')))
                    local = element.find('key')
                    if local is not None:
                        key = _xml_key(local)
                elif element.tag in ('backup', 'forward'):
                    shift = Fraction(int(element.findtext('duration', '0')), divisions)
                    cursor += -shift if element.tag == 'backup' else shift
                elif element.tag == 'harmony' and element.find('numeral') is not None:
                    offset = cursor + Fraction(element.findtext('offset', '0')) / divisions
                    pending.append((offset, 'harmony', element))
                elif element.tag == 'direction' and part is parts[-1] and element.get('placement') == 'below' and int(element.findtext('staff', '1')) == staves:
                    offset = cursor + Fraction(element.findtext('offset', '0')) / divisions
                    for words in element.findall('direction-type/words'):
                        text = (words.text or '').strip()
                        pending.append((offset, 'direction', text))
                elif element.tag == 'note':
                    chord = element.find('chord') is not None
                    onset = previous if chord else cursor
                    if part is parts[-1] and int(element.findtext('staff', '1')) == staves:
                        for lyric in element.findall('lyric'):
                            text = ''.join(t.text or '' for t in lyric.findall('text')).strip()
                            if not text:
                                continue
                            pending.append((onset, 'lyric', text))
                    if not chord:
                        previous = cursor
                        if element.find('grace') is None:
                            cursor += Fraction(int(element.findtext('duration', '0')), divisions)
            # Export inserts offset directions before the notes. Process labels in
            # musical order so a later key prefix carries into the following bar.
            for offset, kind, value in sorted(pending, key=lambda item: item[0]):
                if kind == 'harmony':
                    key, figure = _numeral(value, key)
                    labels.append(Label(number, beat_at(offset), key, figure))
                else:
                    try:
                        key = read_label(value, number, beat_at(offset), key)
                    except ValueError:
                        if kind != 'direction':
                            raise
    return _finish(labels, index)


def compare(student: list[Label], reviewed: dict, index: ScoreIndex) -> list[dict]:
    """Classify each student onset against the reviewed chord still active there.

    Keys take precedence over chord differences. Gaps before the first reviewed
    label and unreadable reference labels are errors, never fabricated agreement.
    """
    student = _finish(student, index)
    reference = from_annotations(reviewed)
    numbers = {measure.number for measure in index.measures}
    reference = _finish([item for item in reference if item.measure in numbers], index)
    results = []
    for label in student:
        position = (label.measure, label.beat)
        expected = next((item for item in reversed(reference) if (item.measure, item.beat) <= position), None)
        if expected is None:
            raise ValueError(f"No reviewed harmony at bar {label.measure} beat {label.beat:g}")
        r, s = sounding(expected.key, expected.figure), sounding(label.key, label.figure)
        if r is None or s is None:
            raise ValueError(f"Unreadable harmony at bar {label.measure} beat {label.beat:g}")
        agreement = matches(r, s)
        if not agreement['key']:
            classification = 'different_key'
        elif not agreement['chord']:
            classification = 'different_chord'
        elif not agreement['chord_and_bass']:
            classification = 'different_inversion'
        elif expected.figure == label.figure:
            classification = 'agrees'
        else:
            classification = 'same_chord_different_spelling'
        results.append({
            'at': {'measure': label.measure, 'beat': label.beat},
            'student': asdict(label), 'reviewed': asdict(expected),
            'classification': classification,
            'is_error': classification in ('different_key', 'different_chord', 'different_inversion'),
            'matches': agreement,
        })
    return results
