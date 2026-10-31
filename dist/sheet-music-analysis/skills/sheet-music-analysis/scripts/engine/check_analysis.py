from __future__ import annotations

import io
import re
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import asdict, replace
from fractions import Fraction

from music21 import key as m21key

from engine.comparison import Label, from_annotations, from_draft, matches, sounding
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
SCRIPT_DIGITS = str.maketrans('⁰¹²³⁴⁵⁶⁷⁸⁹₀₁₂₃₄₅₆₇₈₉', 'o1234567890123456789')


class ClarificationNeeded(ValueError):
    def __init__(self, message: str, question: str):
        self.question = question
        super().__init__(f'{message}. {question}')


def _key(text: str) -> str:
    parts = text.strip().replace('♯', '#').replace('♭', 'b').replace('-', 'b').split()
    name = parts[0]
    if len(parts) > 1:
        name = name.lower() if parts[1].lower().startswith('min') else name[0].upper() + name[1:]
    if sounding(name, 'I') is None:
        raise ValueError(f"Cannot read key {text!r}")
    return name


def _figure(text: str, key: str) -> str:
    groups = text.split('/\0')
    text = text.replace('\0', '')
    figure = text.translate(SCRIPT_DIGITS)
    figure = re.sub(r'(?<=\d)/(?=\d)', '', figure)
    figure = figure.replace('°', 'o').replace('♯', '#').replace('♭', 'b').replace('/o', 'ø')
    figure = {'It+6': 'It6', 'Ger+6': 'Ger6', 'Fr+6': 'Fr6'}.get(figure, figure)
    if re.fullmatch(r'[Vv]64[-–—]53', figure):
        raise ClarificationNeeded(f'Unplaced resolution {text!r}', 'At which beats do the cadential 6/4 and its 5/3 resolution occur?')
    for part in figure.split('/'):
        numeral = re.match(r'[#b-]*([ivIV]+)', part)
        if numeral and not (numeral[1].isupper() or numeral[1].islower()):
            raise ClarificationNeeded(f'Mixed-case numeral {text!r}', f'Should {numeral[1]!r} be uppercase or lowercase?')
    match = re.fullmatch(r"([#b-]*[ivIV]+[oø+]?)(7?)([abcd])(/.*)?", figure)
    if match:
        head, seventh, letter, target = match.groups()
        figures = ('7', '65', '43', '42') if seventh else ('', '6', '64')
        inversion = 'abcd'.index(letter)
        if inversion >= len(figures):
            raise ClarificationNeeded(f"Invalid triad inversion in {text!r}", 'Which inversion do you mean (a, b or c for a triad)?')
        figure = head + figures[inversion] + (target or '')
    parts = figure.split('/')
    valid = all(ROMAN.fullmatch(part) for part in parts)
    if not valid and figure not in ('N', 'N6', 'Cad64', 'It6', 'Ger6', 'Ger65', 'Fr6', 'Fr43'):
        raise ClarificationNeeded(f"Cannot read Roman numeral {text!r} in {key}", f'Which Roman numeral did you mean by {text!r}?')
    if len(parts) > 1:
        head = re.match(r'[#b-]*([ivIV]+)', parts[0])[1].lower()
        if len(parts) > 2 or head == 'i' or not re.fullmatch(r'[#b-]*(?:ii|iii|iv|v|vi|VII)', parts[1], re.IGNORECASE) or parts[1] == 'vii':
            raise ClarificationNeeded(
                f'Implausible applied chord {text!r}',
                f"Separate chords with spaces or commas; use / only for 'of', as in V/V. Did you mean {figure} as one chord, or {' then '.join(groups if len(groups) > 1 else parts)} as separate chords?")
    if sounding(key, figure) is None:
        raise ClarificationNeeded(f"Cannot read Roman numeral {text!r} in {key}", f'Which Roman numeral did you mean by {text!r}?')
    return figure


def _finish(labels: list[Label], index: ScoreIndex | None) -> list[Label]:
    found = {}
    for label in labels:
        if index:
            measure = index.measure(label.measure)
            label = replace(label, beat=measure.beat_of(measure.offset_of(label.beat)))
        position = (label.measure, label.beat)
        if position in found and found[position] != label:
            raise ClarificationNeeded(f"Conflicting labels at bar {label.measure} beat {round(label.beat, 2):g}", f'Which label belongs at bar {label.measure} beat {round(label.beat, 2):g}: {found[position].figure} or {label.figure}?')
        found[position] = label
    if not found:
        raise ValueError('No Roman numeral labels found')
    return sorted(found.values(), key=lambda label: (label.measure, label.beat))


def from_text(text: str, default_key: str = 'C', index: ScoreIndex | None = None) -> list[Label]:
    text = text.translate(SCRIPT_DIGITS)
    text = re.sub(r'(?:\s+/\s*|\s*/\s+)(?=[#b-]*[ivIV])', '/\0', text)
    text = re.sub(r'\s*/\s*', '/', text)
    text = re.sub(r'\bCad\s*6\s*[-–—]\s*4', 'Cad64', text, flags=re.IGNORECASE)
    text = re.sub(r'(?<=\S)\s+[-–—]\s+(?=\S)', ' ', text)
    tokens = list(TOKEN.finditer(text))
    key = _key(default_key)
    initial_keys = set()
    kinds = [t.lastgroup for t in tokens]
    unaddressed = [i for i, k in enumerate(kinds) if k in ('key', 'shortkey') and not (i > 0 and kinds[i - 1] in ('bar', 'beat'))]
    for position in unaddressed:
        name = _key(re.sub(r'^(?:key\s*:?|in)\s*', '', tokens[position].group(), flags=re.I).rstrip(':'))
        stop = next((i for i in range(position + 1, len(kinds)) if kinds[i] in ('key', 'shortkey')), len(kinds))
        if 'label' not in kinds[:position] or ('label' not in kinds[position + 1:stop] and len(unaddressed) == 1):
            initial_keys.add(name)
        elif 'label' not in kinds[position + 1:stop]:
            raise ClarificationNeeded(f'Key {name} has no chord after it', f'Put the key just before the first chord in the new key, e.g. m3 {name}: I. Where does the change to {name} occur?')
    if len(initial_keys) > 1:
        raise ClarificationNeeded('Multiple unaddressed keys', 'Where does the key change occur (bar and beat)?')
    if initial_keys:
        key = next(iter(initial_keys))
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
            value = value.strip('()[]\"\'.!')
            if re.fullmatch(r'\d[-–—]\d', value) and labels and labels[-1].measure == measure and position > 0 and tokens[position - 1].lastgroup == 'label':
                continue
            if re.fullmatch(r'\d+(?:/\S+)?', value) and labels and labels[-1].measure == measure and position > 0 and tokens[position - 1].lastgroup == 'label' and text[tokens[position - 1].end():token.start()].isspace():
                previous = labels.pop()
                labels.append(Label(previous.measure, previous.beat, previous.key, _figure(previous.figure + value, previous.key)))
                continue
            if measure is None:
                raise ClarificationNeeded(f"Give a bar number before {value!r}", 'Which bar and beat does each numeral belong to?')
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
        local_key = m21key.Key(m21key.convertKeyStringToMusic21KeyString(key))
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
    root = ET.fromstring(data)
    for element in root.iter():
        element.tag = element.tag.rsplit('}', 1)[-1]
    if root.tag != 'score-partwise':
        raise ValueError('Expected an uncompressed score-partwise MusicXML document')
    parts = root.findall('part')
    labels = []
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
                elif element.tag == 'harmony' and element.findtext('kind') == 'none' and element.find('root/root-step') is not None and element.find('root/root-step').get('text') == '':
                    offset = cursor + Fraction(element.findtext('offset', '0')) / divisions
                    pending.append((offset, 'analysis', element.find('kind').get('text', '')))
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
            for offset, kind, value in sorted(pending, key=lambda item: item[0]):
                if kind == 'harmony':
                    key, figure = _numeral(value, key)
                    labels.append(Label(number, beat_at(offset), key, figure))
                else:
                    try:
                        key = read_label(value, number, beat_at(offset), key)
                    except ValueError:
                        if kind not in ('direction', 'analysis'):
                            raise
    return _finish(labels, index)


def compare(student: list[Label], reviewed: dict, index: ScoreIndex) -> list[dict]:
    return compare_labels(student, from_annotations(reviewed), index)


def compare_labels(student: list[Label], reference: list[Label], index: ScoreIndex) -> list[dict]:
    student = _finish(student, index)
    numbers = {measure.number for measure in index.measures}
    reference = [item for item in reference if item.measure in numbers]
    reference = _finish(reference, index) if reference else []
    results = []
    for label in student:
        position = (label.measure, label.beat)
        expected = next((item for item in reversed(reference) if (item.measure, item.beat) <= position), None)
        if expected is None:
            results.append({'at': {'measure': label.measure, 'beat': label.beat}, 'student': asdict(label), 'reviewed': None,
                            'classification': 'unchecked', 'is_error': False})
            continue
        r, s = sounding(expected.key, expected.figure), sounding(label.key, label.figure)
        if r is None or s is None:
            raise ValueError(f"Unreadable harmony at bar {label.measure} beat {label.beat:g}")
        agreement = matches(r, s)
        if not agreement['chord']:
            classification = 'different_chord'
        elif (r.tonic, r.minor) != (s.tonic, s.minor):
            classification = 'different_key'
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


def from_score(score: bytes, index: ScoreIndex) -> list[Label]:
    if score[:2] == b'PK':
        with zipfile.ZipFile(io.BytesIO(score)) as archive:
            container = ET.fromstring(archive.read('META-INF/container.xml'))
            score = archive.read(next(e.get('full-path') for e in container.iter() if e.tag.endswith('rootfile')))
    return from_musicxml(score, index=index)


def student_labels(text: str, score: bytes | None, index: ScoreIndex) -> list[Label]:
    if text.strip().lower() == 'score':
        if score is None:
            raise ValueError('Numerals inside the score can only be read from the score file; type the labels instead.')
        return from_score(score, index)
    return from_text(text, index=index)


def as_typed(labels: list[Label]) -> str:
    return '; '.join(f"m{label.measure} b{label.beat:g} {label.key}: {label.figure}" for label in labels)


def as_text(student: list[Label], draft, index: ScoreIndex) -> str:
    chords = {(chord.measure, chord.beat): chord for chord in draft.chords}
    lines = [
        "STUDENT CHECK (the user gave their own Roman numerals and wants a second reader, not an answer key). "
        "Each line is one of their labels beside the draft's chord at that beat. Start with what they got right. "
        "Explain every difference in terms of the notes (the bass, which pitch classes are present), say plainly "
        "when both readings are defensible, and count 'same chord different spelling' as agreement. The draft is "
        "right only about half the time: where its confidence is low or it lists a runner-up, or on the weak spots "
        "named in the method, say the reading is a close call instead of claiming the student is wrong.",
        "",
        "measure beat | student | draft (confidence) | draft bass | draft pitch classes | how they compare",
    ]
    for item in compare_labels(student, from_draft(draft), index):
        label, expected = item['student'], item['reviewed']
        chord = chords.get((expected['measure'], expected['beat'])) if expected else None
        confidence = f" ({chord.confidence:.2f}" + (f", runner-up {chord.alternative} {chord.alternative_confidence:.2f}" if chord.alternative else '') + ')' if chord else ''
        lines.append(
            f"m{label['measure']} b{label['beat']:g} | {label['key']}: {label['figure']} | "
            f"{expected['key'] + ': ' + expected['figure'] + confidence if expected else 'none'} | "
            f"{chord.bass if chord else ''} | {' '.join(chord.pitches) if chord else ''} | "
            + item['classification'].replace('_', ' ')
        )
    return '\n'.join(lines)
