"""Measure PDF bar warnings on cached production readings; no OMR or network calls.

Run from the repository root with PYTHONPATH=. and --data-root pointing at spike/omr.
The benchmark's pitch alignment is followed by its equal-gap fill, using the bars
and pitch/onset multisets seen by the engine (including pickups and split bars).
"""

import argparse
from collections import Counter, defaultdict
from fractions import Fraction
import importlib.util
import json
from pathlib import Path
import xml.etree.ElementTree as ET

from engine.read_pdf import problem_spots
from engine.render import load_toolkit
from engine.score import ScoreIndex

SETS = ('bench', 'bench-heldout', 'bench-heldout2', 'bench-heldout3')
SIGNALS = ('clef_change', 'key_change', 'outside_piano_range', 'duration_type_mismatch',
           'short_voice', 'three_beamed_eighths', 'density_outlier', 'negative_cursor',
           'accidental_pitch_mismatch', 'instrument_range', 'short_voice_ternary')
SEMI = dict(zip('CDEFGAB', (0, 2, 4, 5, 7, 9, 11)))
TYPES = dict(zip(('whole', 'half', 'quarter', 'eighth', '16th', '32nd', '64th'),
                 (Fraction(4), Fraction(2), Fraction(1), Fraction(1, 2), Fraction(1, 4), Fraction(1, 8), Fraction(1, 16))))


def notes(measure):
    out = Counter()
    for event in measure.events:
        if event.pitch:
            p = event.pitch
            accidental = p[1:].rstrip('0123456789')
            midi = 12 * (int(p[1 + len(accidental):]) + 1) + SEMI[p[0]] + accidental.count('#') - accidental.count('b')
            out[midi, event.onset] += 1
    return out


def candidates(data, measures):
    found = defaultdict(set)
    numbers = {s.index: m.number for m in measures for s in m.segments}
    root = ET.fromstring(data)
    instruments = {p.get('id'): p.findtext('part-name', '').lower() for p in root.findall('part-list/score-part')}
    for part in root.iter('part'):
        divisions, full = 1, None
        clefs, key = {}, None
        densities = []
        for position, measure in enumerate(part.findall('measure'), 1):
            number = numbers[position]
            attributes = measure.find('attributes')
            if attributes is not None:
                divisions = int(attributes.findtext('divisions', str(divisions)))
                time = attributes.find('time')
                if time is not None and time.findtext('beats', '').isdigit():
                    full = Fraction(int(time.findtext('beats')) * 4, int(time.findtext('beat-type')))
                for clef in attributes.findall('clef'):
                    staff = clef.get('number', '1')
                    value = (clef.findtext('sign'), clef.findtext('line'), clef.findtext('clef-octave-change'))
                    if staff in clefs and value != clefs[staff]:
                        found['clef_change'].add(number)
                    clefs[staff] = value
                value = attributes.findtext('key/fifths')
                if value is not None:
                    if key is not None and value != key:
                        found['key_change'].add(number)
                    key = value
            cursor = Fraction(0)
            for element in measure:
                if element.tag in ('backup', 'forward') or (element.tag == 'note' and element.find('chord') is None and element.find('grace') is None):
                    duration = Fraction(element.findtext('duration', '0')) / divisions
                    cursor += -duration if element.tag == 'backup' else duration
                    if cursor < -Fraction(1, 96):
                        found['negative_cursor'].add(number)
            totals = Counter()
            beam_groups, group = [], []
            count = 0
            for note in measure.findall('note'):
                if note.find('grace') is not None:
                    continue
                duration = Fraction(note.findtext('duration', '0')) / divisions
                if note.find('chord') is None:
                    totals[note.findtext('voice', '1')] += duration
                    beam = note.findtext('beam')
                    if beam == 'begin':
                        group = [note]
                    elif group and beam in ('continue', 'end'):
                        group.append(note)
                        if beam == 'end':
                            beam_groups.append(group)
                            group = []
                    else:
                        group = []
                if note.find('pitch') is None:
                    continue
                count += 1
                pitch = note.find('pitch')
                midi = 12 * (int(pitch.findtext('octave')) + 1) + SEMI[pitch.findtext('step')] + int(float(pitch.findtext('alter', '0')))
                if midi < 21 or midi > 108:
                    found['outside_piano_range'].add(number)
                accidental = {'natural': 0, 'sharp': 1, 'flat': -1, 'double-sharp': 2, 'sharp-sharp': 2, 'flat-flat': -2}.get(note.findtext('accidental'))
                if accidental is not None and accidental != int(float(pitch.findtext('alter', '0'))):
                    found['accidental_pitch_mismatch'].add(number)
                instrument = instruments.get(part.get('id'), '')
                ranges = {'violin': (55, 103), 'viola': (48, 91), 'cello': (36, 84), 'violoncello': (36, 84),
                          'flute': (60, 96), 'oboe': (58, 91), 'piano': (21, 108)}
                if instrument in ranges and not ranges[instrument][0] <= midi <= ranges[instrument][1]:
                    found['instrument_range'].add(number)
                expected = TYPES.get(note.findtext('type'))
                if expected is not None and duration and note.find('time-modification') is None:
                    expected *= 2 - Fraction(1, 2 ** len(note.findall('dot')))
                    if abs(duration - expected) > Fraction(1, 96):
                        found['duration_type_mismatch'].add(number)
            if full and any(0 < total < full - Fraction(1, 96) for total in totals.values()):
                found['short_voice'].add(number)
                if any(0 < total < full - Fraction(1, 96) and (total / Fraction(1, 2)).denominator == 1 and int(total * 2) % 3 == 0 for total in totals.values()):
                    found['short_voice_ternary'].add(number)
            if any(len(group) == 3 and all(n.findtext('type') == 'eighth' and n.find('time-modification') is None for n in group) for group in beam_groups):
                found['three_beamed_eighths'].add(number)
            densities.append((number, count))
        for i in range(1, len(densities) - 1):
            number, count = densities[i]
            left, right = densities[i - 1][1], densities[i + 1][1]
            if min(left, right) >= 4 and (count > 2 * max(left, right) or count * 2 < min(left, right)):
                found['density_outlier'].add(number)
    return {name: sorted(values) for name, values in found.items()}


def metrics(records, candidate=None):
    flagged = correct_flags = wrong = missed_notes = 0
    for record in records:
        flags = set(record['baseline'])
        if candidate:
            flags.update(record['candidates'].get(candidate, []))
        for bar in record['bars']:
            wrong += bar['wrong']
            if bar['number'] in flags:
                flagged += 1
                correct_flags += bar['wrong']
            else:
                missed_notes += bar['wrong_notes']
    return dict(flagged=flagged, flagged_wrong=correct_flags, wrong_bars=wrong,
                precision=correct_flags / flagged if flagged else None,
                recall=correct_flags / wrong if wrong else None, unflagged_wrong_notes=missed_notes)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    spec = importlib.util.spec_from_file_location('benchmark_compare', args.data_root / 'compare.py')
    compare = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(compare)
    records, truth_cache = [], {}
    for name in SETS:
        folder = args.data_root / name
        manifest = json.loads((folder / 'manifest.json').read_text())
        for entry in manifest['pdfs']:
            path = folder / 'cache/runs' / ('results-final--' + Path(entry['pdf']).stem + '.musicxml')
            truth_path = folder / manifest['pieces'][entry['piece']]['truth']
            if truth_path not in truth_cache:
                truth_cache[truth_path] = [notes(m) for m in ScoreIndex(load_toolkit(truth_path.read_bytes()).getMEI()).measures]
            truth = truth_cache[truth_path]
            data = path.read_bytes()
            measures = ScoreIndex(load_toolkit(data).getMEI()).measures
            reading = [notes(m) for m in measures]
            pairs = compare.align([(b,) for b in truth], [(b,) for b in reading])[0]
            anchors = [(-1, -1)] + pairs + [(len(truth), len(reading))]
            for (i1, j1), (i2, j2) in zip(anchors, anchors[1:]):
                if i2 - i1 == j2 - j1:
                    pairs += [(i1 + k, j1 + k) for k in range(1, i2 - i1)]
            truth_at = {j: i for i, j in pairs}
            uneven, _ = problem_spots(data)
            bars = []
            for j, (measure, observed) in enumerate(zip(measures, reading)):
                expected = truth[truth_at[j]] if j in truth_at else Counter()
                missing, extra = sum((expected - observed).values()), sum((observed - expected).values())
                bars.append(dict(number=measure.number, truth_index=truth_at.get(j), wrong=expected != observed,
                                 wrong_notes=max(missing, extra), missing=missing, extra=extra))
            records.append(dict(set=name, pdf=entry['pdf'], baseline=sorted(set(uneven)),
                                bars=bars, candidates=candidates(data, measures),
                                unaligned_truth_bars=len(truth) - len(truth_at)))
            print(name, path.stem, flush=True)
    names = list(SIGNALS)
    summary = {name: {c: metrics([r for r in records if r['set'] == name], None if c == 'baseline' else c)
                      for c in ['baseline'] + names} for name in SETS}
    args.output.write_text(json.dumps(dict(summary=summary, readings=records), indent=2) + '\n')
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
