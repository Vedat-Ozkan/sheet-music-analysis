"""Run local MuseScore conversions and compare their MSCX against reviewed positions.

Run from the repository root with the project Python:
  PYTHONPATH=. python spike/export/check_corpus.py --musescore /path/to/squashfs-root/AppRun --out /path/to/evidence
The engraving corpus must already exist in out/engraving/scores (no downloads).
"""
from collections import Counter
from copy import deepcopy
from fractions import Fraction
import argparse
import json
import os
from pathlib import Path
import subprocess
import xml.etree.ElementTree as ET

from engine.draft import as_annotations, build
from engine.export import _document, export_musicxml
from engine.render import load_toolkit
from engine.score import ScoreIndex

ROOT = Path(__file__).resolve().parents[2]
DURATIONS = {name: Fraction(4, denominator) for name, denominator in
             [('long', 1), ('breve', 1), ('whole', 1), ('half', 2), ('quarter', 4),
              ('eighth', 8), ('16th', 16), ('32nd', 32), ('64th', 64), ('128th', 128), ('256th', 256)]}
DURATIONS.update(long=Fraction(16), breve=Fraction(8))
DIGITS = str.maketrans('⁰¹²³⁴⁵⁶⁷⁸⁹', '0123456789')


def expected_labels(original, analysis, index):
    root = ET.fromstring(_document(original))
    staff_count = sum(int(p.findtext('measure/attributes/staves', '1')) for p in root.findall('part'))
    key, expected = None, []
    for a in sorted((a for a in analysis['annotations'] if a['type'] == 'harmony'),
                    key=lambda a: (a['at']['measure'], a['at'].get('beat', 1))):
        text = a['label'].translate(DIGITS)
        if a.get('key') and a['key'] != key:
            key = a['key']
            text = f'{key}: {text}'
        bar = index.measure(a['at']['measure'])
        expected.append((bar.number, bar.offset_of(a['at'].get('beat', 1)), staff_count, text))
    return expected


def converted_labels(path, index, texts):
    root = ET.parse(path).getroot()
    segments = {s.index: (m, s) for m in index.measures for s in m.segments}
    actual = []
    for staff in root.findall('./Score/Staff'):
        measures = staff.findall('Measure')
        assert len(measures) == len(segments), (path.name, staff.get('id'), len(measures), len(segments))
        for position, measure in enumerate(measures, 1):
            bar, segment = segments[position]
            for voice in measure.findall('voice'):
                cursor, tuplets = Fraction(0), []
                for element in voice:
                    if element.tag == 'location':
                        assert element.find('measures') is None, ET.tostring(element)
                        cursor += 4 * Fraction(element.findtext('fractions', '0'))
                    elif element.tag == 'Tuplet':
                        tuplets.append(Fraction(int(element.findtext('normalNotes')), int(element.findtext('actualNotes'))))
                    elif element.tag == 'endTuplet':
                        tuplets.pop()
                    elif element.tag == 'StaffText':
                        text = ''.join(element.find('text').itertext())
                        if text in texts and element.findtext('placement') == 'below':
                            actual.append((bar.number, segment.start + cursor, int(staff.get('id')), text))
                    elif element.tag in ('Chord', 'Rest'):
                        grace = any(child.tag == 'appoggiatura' or child.tag.startswith('grace')
                                    for child in element)
                        for lyric in element.findall('Lyrics'):
                            if ''.join(lyric.find('text').itertext()) in texts:
                                assert lyric.findtext('placement', 'below') == 'below'
                                actual.append((bar.number, segment.start + cursor, int(staff.get('id')) + int(element.findtext('staffMove', '0')),
                                               ''.join(lyric.find('text').itertext())))
                        if not grace:
                            kind = element.findtext('durationType')
                            duration = (4 * Fraction(element.findtext('duration')) if kind == 'measure'
                                        else DURATIONS[kind] * (2 - Fraction(1, 2 ** int(element.findtext('dots', '0')))))
                            for ratio in tuplets:
                                duration *= ratio
                            cursor += duration
                assert not tuplets, (path.name, position)
    return actual


def records(labels, index):
    return [dict(measure=m, beat=str(Fraction(1) + offset / index.measure(m).beat_length),
                 staff=staff, text=text) for m, offset, staff, text in labels]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--musescore', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--check-only', action='store_true')
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    work = ROOT / 'out/export-check'
    work.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, QT_QPA_PLATFORM='offscreen', QT_QPA_PLATFORMTHEME='none',
               QT_STYLE_OVERRIDE='Fusion', XDG_CURRENT_DESKTOP='', XDG_DATA_HOME=str(work / 'data'),
               XDG_CONFIG_HOME=str(work / 'config'), XDG_CACHE_HOME=str(work / 'cache'))
    for key in ('DISPLAY', 'WAYLAND_DISPLAY'):
        env.pop(key, None)
    pairs = [(next((ROOT / 'out/engraving/scores').glob(a.stem + '.*')), a)
             for a in sorted((ROOT / 'examples/engraving').glob('*.json'))]
    pairs.append((ROOT / 'tests/data/chopin_nocturne_op9_no2.mxl', ROOT / 'examples/chopin_op9_no2_m1-8.json'))
    pairs = [(source, a.stem, json.loads(a.read_text())) for source, a in pairs]
    cadential = ROOT / 'tests/data/cadential_64.musicxml'
    cadential_index = ScoreIndex(load_toolkit(cadential.read_bytes()).getMEI())
    cadential_analysis = as_annotations(build(json.loads((ROOT / 'tests/data/cadential_64_raw.json').read_text()),
                                             cadential_index)).model_dump()
    pairs.append((cadential, 'cadential-64', cadential_analysis))
    probes = {'annotations': [dict(type='harmony', at=dict(measure=m, beat=b), label=label)
                              for m, b, label in [(1, 1, 'V⁶⁵'), (1, 2, 'viio7/V'), (1, 3, 'Ger65'),
                                                  (1, 4, 'bII6'), (2, 1, 'Cad64'), (2, 2, 'viiø65/ii')]]}
    pairs.append((ROOT / 'tests/data/chopin_nocturne_op9_no2.mxl', 'figure-probes', probes))
    staff_probe = {'annotations': [dict(type='harmony', at=dict(measure=2, beat=2),
                                       key='Db', label='viiø42/vi')]}
    pairs.append((ROOT / 'tests/data/export-debussy-clair.musicxml', 'bass-sustain-probe', staff_probe))
    results = {}
    for source, name, analysis in pairs:
        original = source.read_bytes()
        index = ScoreIndex(load_toolkit(original).getMEI())
        expected = expected_labels(original, analysis, index)
        before = ET.fromstring(_document(original))
        original_texts = {x.text for x in before.findall('.//lyric/text')
                          + before.findall('.//direction/direction-type/words')}
        assert not original_texts & {x[3] for x in expected}, name
        if not args.check_only:
            (args.out / (name + '-annotations.json')).write_text(json.dumps(analysis, indent=2) + '\n')
            xml = args.out / (name + '.musicxml')
            xml.write_bytes(export_musicxml(original, analysis))
            native = work / (name + '.mscx')
            command = [str(args.musescore), str(xml), '-platform', 'offscreen',
                       '-platformtheme', 'none', '-style', 'Fusion', '-o', str(native)]
            proc = subprocess.run(command, env=env, capture_output=True, timeout=180, cwd=ROOT)
            (args.out / (name + '-mscx.log')).write_bytes(proc.stdout + proc.stderr)
            if proc.returncode:
                results[name] = dict(expected=len(expected), status='NOT RUN', reason=f'Conversion exited {proc.returncode}')
                print(name, results[name], flush=True)
                continue
            (args.out / native.name).write_bytes(native.read_bytes())
        after = ET.parse(args.out / (name + '.musicxml')).getroot()
        before_notes, after_notes = before.findall('.//note'), after.findall('.//note')
        assert len(before_notes) == len(after_notes), name
        for original_note, exported_note in zip(before_notes, after_notes):
            clean = deepcopy(exported_note)
            existing = {ET.tostring(x) for x in original_note.findall('lyric')}
            for lyric in clean.findall('lyric'):
                if ET.tostring(lyric) not in existing:
                    clean.remove(lyric)
            assert ET.tostring(original_note) == ET.tostring(clean), name
        actual = converted_labels(args.out / (name + '.mscx'), index, {x[3] for x in expected})
        wanted, got = Counter(expected), Counter(actual)
        for label in list(wanted):
            m, offset, staff, text = label
            match = next((x for x in got if x[0] == m and x[2:] == (staff, text)
                          and abs(x[1] - offset) <= Fraction(1, 96) and got[x]), None)
            if match is not None and match != label:
                got[match] -= 1
                got[label] += 1
        survived = sum((wanted & got).values())
        results[name] = dict(source=str(source.relative_to(ROOT)), transport_probe=name in ('figure-probes', 'bass-sustain-probe'),
                             musicxml_notes_unchanged=len(before_notes), expected=len(expected), actual=len(actual),
                             exact_text_bar_beat_bass=survived,
                             missing=records(list((wanted - got).elements()), index),
                             unexpected=records(list((got - wanted).elements()), index),
                             expected_labels=records(expected, index), actual_labels=records(actual, index))
        print(name, f'{survived}/{len(expected)}', results[name]['missing'], flush=True)
    (args.out / 'corpus-results.json').write_text(json.dumps(results, indent=2) + '\n')
    return int(any(r.get('exact_text_bar_beat_bass') != r['expected'] or r.get('unexpected') for r in results.values()))


if __name__ == '__main__':
    raise SystemExit(main())
