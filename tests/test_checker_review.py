import json
import re
from itertools import combinations
from pathlib import Path

import pytest
from music21 import chord, corpus, interval, key, note, roman
from music21.musicxml.m21ToXml import GeneralObjectExporter

from engine import check_analysis, part_writing
from engine.comparison import Label, matches, sounding
from engine.draft import Chord
from engine.reduce import midi
from engine.render import load_toolkit
from engine.score import ScoreIndex

DATA = Path(__file__).parent / 'data'
ENTRIES = json.loads((DATA / 'reference/part_writing_audit.json').read_text())['entries']
NAMES = sorted({e['chorale'] for e in ENTRIES if not e['chorale'].startswith('fixture:')})


@pytest.fixture(scope='module')
def real_corpus():
    paths = {p.stem: p for p in corpus.getComposer('bach')}
    sources = [(name, GeneralObjectExporter(corpus.parse(paths[name])).parse()) for name in NAMES]
    sources += [(str(p.relative_to(DATA)), p.read_bytes()) for p in sorted(DATA.glob('part_writing*.musicxml'))]
    sources += [(str(p.relative_to(DATA)), p.read_bytes()) for p in sorted((DATA / 'part_writing_ap').glob('*.musicxml'))]
    found = {}
    for name, data in sources:
        index = ScoreIndex(load_toolkit(data).getMEI())
        voices, notes, rows = part_writing._table(index, beat_grid=True)
        found[name] = index, voices, notes, dict(rows), part_writing.check(index)
    return found


def ornaments(index, notes):
    found = set()
    for line in notes.values():
        for (_, end, a), (start, stop, b), (following, _, c) in zip(line, line[1:], line[2:]):
            m = index.measure(b.measure)
            if end != start or stop != following or a.tied or b.tied:
                continue
            if b.duration >= m.beat_length or (b.onset / m.beat_length).denominator == 1:
                continue
            ab, bc = (interval.Interval(note.Note(x.pitch.replace('b', '-')), note.Note(y.pitch.replace('b', '-')))
                      for x, y in ((a, b), (b, c)))
            if all(i.isStep and 0 < abs(i.semitones) <= 2 for i in (ab, bc)) and (a.pitch == c.pitch or ab.semitones * bc.semitones > 0):
                found.add(b.id)
    return found


def test_corpus_parallel_motion_and_exam_policy(real_corpus):
    wrong = []
    for name, (_, _, _, rows, hits) in real_corpus.items():
        for h in hits:
            if h.rule not in ('parallel_fifths', 'parallel_octaves'):
                continue
            a, b = (rows[p] for p in zip(h.bars, h.beats))
            au, al, bu, bl = [midi(r[v][0].pitch) for r in (a, b) for v in h.voices]
            same = (bu - au) * (bl - al) > 0
            valid = au >= al and bu >= bl and au % 12 != bu % 12 and al % 12 != bl % 12 and (au, al) != (bl, bu)
            policy = h.why.startswith('Serious:' if same else 'Moderate:') and (same or 'strict exam rule (AP 2025)' in h.why)
            if not valid or not policy:
                wrong.append((name, h.bars, h.beats, (au, al, bu, bl), h.why))
    assert not wrong, wrong


def test_corpus_unequal_fifths_exclude_ornaments_and_are_moderate(real_corpus):
    wrong = []
    for name, (index, _, notes, rows, hits) in real_corpus.items():
        decorated = ornaments(index, notes)
        positions = list(rows)
        structural = set()
        for previous, pos in zip(positions, positions[1:]):
            a, b = rows[previous], rows[pos]
            if len(a) != 4 or len(b) != 4 or any(len(es) != 1 for es in list(a.values()) + list(b.values())):
                continue
            c = chord.Chord([es[0].pitch.replace('b', '-') for es in b.values()])
            if (c.isTriad() or c.isSeventh()) and all(midi(a[v][0].pitch) != midi(b[v][0].pitch) for v in a):
                structural.update(es[0].id for es in b.values())
        decorated -= structural
        for before, after in zip(positions, positions[1:]):
            a, b = rows[before], rows[after]
            if len(a) != 4 or len(b) != 4 or any(len(es) != 1 for es in list(a.values()) + list(b.values())):
                continue
            arrival = chord.Chord([es[0].pitch.replace('b', '-') for es in b.values()])
            if not arrival.isTriad() or arrival.inversion() != 0:
                continue
            for upper, lower in combinations(a, 2):
                events = [r[v][0] for r in (a, b) for v in (upper, lower)]
                if any(e.id in decorated for e in events):
                    continue
                au, al, bu, bl = [midi(e.pitch) for e in events]
                fifths = [interval.Interval(note.Note(r[lower][0].pitch.replace('b', '-')),
                                           note.Note(r[upper][0].pitch.replace('b', '-'))).simpleName for r in (a, b)]
                if (au >= al and bu >= bl and (bu - au) * (bl - al) > 0 and fifths == ['d5', 'P5']
                        and (lower == list(a)[-1] or bu > au)):
                    if not any(h.rule == 'unequal_fifths' and h.voices == (upper, lower)
                               and [rows[p][v][0].id for p in zip(h.bars, h.beats) for v in h.voices]
                               == [e.id for e in events] for h in hits):
                        wrong.append((name, before, after, 'missing forbidden motion'))
        for h in hits:
            if h.rule == 'unequal_fifths':
                events = [rows[p][v][0] for p in zip(h.bars, h.beats) for v in h.voices]
                if any(e.id in decorated for e in events) or not h.why.startswith('Moderate:'):
                    wrong.append((name, h.bars, h.beats))
    assert not wrong, wrong


def test_corpus_six_four_doubling_and_resolving_duplicate(real_corpus):
    wrong = []
    for name, (index, voices, notes, rows, hits) in real_corpus.items():
        if len(voices) != 4 or not part_writing.applies(index):
            continue
        decorated = ornaments(index, notes)
        for pos, row in rows.items():
            if len(row) != 4 or any(len(es) != 1 or es[0].id in decorated for es in row.values()):
                continue
            c = chord.Chord([es[0].pitch.replace('b', '-') for es in row.values()])
            if (c.isMajorTriad() or c.isMinorTriad()) and c.inversion() == 2:
                bass = midi(row[voices[-1]][0].pitch) % 12
                if c.bass().pitchClass != bass:
                    continue
                doubled = sum(midi(es[0].pitch) % 12 == bass for es in row.values()) >= 2
                reported = any(h.rule == 'six_four_doubling' and (h.bars[0], h.beats[0]) == pos for h in hits)
                if not doubled and not reported:
                    wrong.append((name, pos, 'undoubled bass'))
        for h in hits:
            if h.rule == 'six_four_doubling':
                c = chord.Chord([es[0].pitch.replace('b', '-') for es in rows[(h.bars[0], h.beats[0])].values()])
                if not ((c.isMajorTriad() or c.isMinorTriad()) and c.inversion() == 2):
                    wrong.append((name, h.bars, h.beats, 'not a major or minor six-four'))
            if h.rule != 'unresolved_cadential_tone':
                continue
            a, b = (rows[p] for p in zip(h.bars, h.beats))
            pc = midi(a[h.voices[0]][0].pitch) % 12
            source = chord.Chord([es[0].pitch.replace('b', '-') for es in a.values()])
            if source.third is None or pc != source.third.pitchClass:
                continue
            copies = [v for v in a if midi(a[v][0].pitch) % 12 == pc and v in b]
            if any(midi(a[v][0].pitch) - midi(b[v][0].pitch) in (1, 2)
                   and midi(b[v][0].pitch) % 12 == (source.fifth.pitchClass + 7) % 12 for v in copies):
                wrong.append((name, h.bars, h.beats, 'resolved duplicate sixth'))
    assert not wrong, wrong


def test_corpus_case_leniency_preserves_chord(real_corpus):
    wrong = []
    inputs = json.loads((DATA / 'check_analysis/typed_inputs.json').read_text())
    figures = {(key, fig) for case in inputs for _, _, key, fig in case.get('expected', [])}
    figures |= {(key, fig) for key in ('C', 'a') for fig in ('VII', 'viio', 'iv', 'IV', 'II', 'ii', 'VIo', 'vio', 'V/bIII', 'V/III')}
    for name, (index, *_rest) in real_corpus.items():
        bar = index.measures[0].number
        for key, fig in figures:
            variant = re.sub(r'[ivIV]+', lambda m: m[0].swapcase(), fig)
            actual, expected = sounding(key, variant), sounding(key, fig)
            if actual is None or expected is None:
                continue
            result = check_analysis.compare_labels([Label(bar, 1, key, variant)], [Label(bar, 1, key, fig)], index)[0]
            if result['is_error'] == matches(expected, actual)['chord_and_bass']:
                wrong.append((name, key, variant, fig, result['classification']))
            if result['notes'] and not matches(expected, actual)['chord']:
                wrong.append((name, key, variant, fig, 'false mild note'))
        assert sounding('a', 'V/bIII') == sounding('a', 'V/III')
    assert not wrong, wrong[:30]


def test_review_real_passages(real_corpus):
    for name, bars in [('bwv255', (7, 8)), ('bwv121.6', (12, 12))]:
        assert not any(h.rule == 'parallel_fifths' and h.bars == bars and h.voices == ((2, 1), (3, 1)) for h in real_corpus[name][-1])
    for name, bars in [('part_writing_bwv85.6.musicxml', (4, 10)), ('bwv269', (8,))]:
        assert not any(h.rule == 'unequal_fifths' and h.bars[0] in bars for h in real_corpus[name][-1])
    for name, bars in [('bwv311', (13, 13)), ('bwv65.7', (6, 7))]:
        assert any(h.rule == 'unequal_fifths' and h.bars == bars for h in real_corpus[name][-1])
    assert not any(h.rule == 'unresolved_cadential_tone' and h.bars == (2, 2) and h.voices == ((2, 1),) for h in real_corpus['bwv416'][-1])


def test_corpus_passing_idiom_through_predominant(real_corpus):
    checked = 0
    for name, (index, voices, _, rows, _) in real_corpus.items():
        positions = list(rows)
        for i, pos in enumerate(positions[:-1]):
            a, b = rows[pos], rows[positions[i + 1]]
            if len(a) != 4 or len(b) != 4 or any(len(es) != 1 for es in list(a.values()) + list(b.values())):
                continue
            ca, cb = [chord.Chord([es[0].pitch.replace('b', '-') for es in r.values()]) for r in (a, b)]
            if not ca.isDominantSeventh() or ca.inversion() != 2 or not cb.isTriad() or cb.inversion() != 1 or ca.root().pitchClass != (cb.root().pitchClass + 7) % 12:
                continue
            earlier = [p for p in positions[:i] if p[0] >= pos[0] - 2]
            tonic = next((p for p in reversed(earlier) if len(rows[p]) == 4 and all(len(es) == 1 for es in rows[p].values()) and {midi(es[0].pitch) % 12 for es in rows[p].values()} == set(cb.pitchClasses) and midi(rows[p][voices[-1]][0].pitch) % 12 == cb.root().pitchClass), None)
            if tonic is None or i < 2 or not midi(rows[tonic][voices[-1]][0].pitch) < midi(a[voices[-1]][0].pitch) < midi(b[voices[-1]][0].pitch):
                continue
            key_name = cb.root().name.replace('-', 'b')
            if cb.isMinorTriad():
                key_name = key_name.lower()
            local = key.Key(key_name)
            scale = {p.pitchClass for p in local.pitches}
            predominant = []
            for p in positions:
                if not tonic < p < pos or len(rows[p]) != 4 or any(len(es) != 1 for es in rows[p].values()):
                    continue
                c = chord.Chord([es[0].pitch.replace('b', '-') for es in rows[p].values()])
                if c.isTriad() and c.root().pitchClass in ((cb.root().pitchClass + 2) % 12, (cb.root().pitchClass + 5) % 12) and set(c.pitchClasses) <= scale:
                    predominant.append((p, roman.romanNumeralFromChord(c, local).figure))
            if not predominant:
                continue
            mid, figure = predominant[0]
            labels = [(tonic, 'I' if cb.isMajorTriad() else 'i'), (mid, figure), (pos, 'V43'), (positions[i + 1], 'I6' if cb.isMajorTriad() else 'i6')]
            spans = [Chord(p[0], p[1], key_name, figure, p[0], 1, None) for p, figure in labels]
            hits = part_writing.check(index, spans)
            assert not any(h.rule == 'unresolved_seventh' and (h.bars[0], h.beats[0]) == pos and midi(a[h.voices[0]][0].pitch) < midi(b[h.voices[0]][0].pitch) for h in hits), (name, pos)
            checked += 1
    assert checked > 0


def test_review_bwv269_rising_seventh_through_predominant():
    data = GeneralObjectExporter(corpus.parse('bach/bwv269')).parse()
    index = ScoreIndex(load_toolkit(data).getMEI())
    spans = [Chord(8, beat, 'G', figure, 8, 4, None)
             for beat, figure in [(1, 'I'), (2, 'ii'), (2.5, 'V43'), (3, 'I6')]]
    assert not any(h.rule == 'unresolved_seventh' and h.bars == (8, 8)
                   and h.beats == (2.5, 3.0) and h.voices == ((1, 1),) for h in part_writing.check(index, spans))


@pytest.fixture(scope='module')
def draft_corpus():
    found = {}
    for name, labels in json.loads((DATA / 'reference/part_writing_draft_chords.json').read_text())['chords'].items():
        index = ScoreIndex(load_toolkit((DATA / name).read_bytes()).getMEI())
        chords = [Chord(measure, beat, key_name, label, 1.0, 1.0, None) for measure, beat, key_name, label in labels]
        voices, notes, rows = part_writing._table(index)
        found[name] = index, notes, dict(rows), part_writing.check(index, chords)
    return found


def test_draft_chords_doubled_seventh_skips_ornaments(draft_corpus):
    wrong = []
    for name, (index, notes, rows, hits) in draft_corpus.items():
        decorated = ornaments(index, notes)
        for h in hits:
            if h.rule == 'doubled_seventh' and any(rows[(h.bars[0], h.beats[0])][v][0].id in decorated for v in h.voices):
                wrong.append((name, h.bars, h.beats, 'ornament counted as the seventh'))
    assert not wrong, wrong
