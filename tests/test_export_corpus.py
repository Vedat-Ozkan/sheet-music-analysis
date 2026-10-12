"""Check the verification timeline against a real editor round-trip."""
from collections import Counter
from copy import deepcopy
from fractions import Fraction
import os
from pathlib import Path
import subprocess
import xml.etree.ElementTree as ET

import pytest

from engine.check_analysis import from_musicxml
from engine.export import export_musicxml
from engine.render import load_toolkit
from engine.score import ScoreIndex
from spike.export.check_corpus import converted_labels, expected_labels

ROOT = Path(__file__).resolve().parents[1]
MUSESCORE = Path('/home/kema/projects/sheet-music-plugin/spike/omr/tools/musescore/squashfs-root/AppRun')


@pytest.mark.skipif(not MUSESCORE.is_file(), reason='Local MuseScore AppImage extraction absent')
def test_mscx_appoggiatura_does_not_advance_lyric_beat(tmp_path):
    root = ET.parse(ROOT / 'tests/data/export_placement.musicxml').getroot()
    measure = root.findall('part')[-1].find('measure')
    first_bass = measure.findall('note')[1]
    grace = deepcopy(first_bass)
    grace.remove(grace.find('duration'))
    grace.remove(grace.find('dot'))
    grace.insert(0, ET.Element('grace'))
    grace.find('type').text = 'eighth'
    measure.insert(list(measure).index(first_bass), grace)
    original = ET.tostring(root)
    analysis = {'annotations': [dict(type='harmony', at=dict(measure=1, beat=1), label='V65')]}
    index = ScoreIndex(load_toolkit(original).getMEI())
    xml = tmp_path / 'grace.musicxml'
    native = tmp_path / 'grace.mscx'
    roundtrip = tmp_path / 'grace-roundtrip.musicxml'
    xml.write_bytes(export_musicxml(original, analysis))
    env = dict(os.environ, QT_QPA_PLATFORM='offscreen', QT_QPA_PLATFORMTHEME='none',
               QT_STYLE_OVERRIDE='Fusion', XDG_CURRENT_DESKTOP='',
               XDG_DATA_HOME=str(tmp_path / 'data'), XDG_CONFIG_HOME=str(tmp_path / 'config'),
               XDG_CACHE_HOME=str(tmp_path / 'cache'))
    for key in ('DISPLAY', 'WAYLAND_DISPLAY'):
        env.pop(key, None)
    for source, target in [(xml, native), (native, roundtrip)]:
        proc = subprocess.run([str(MUSESCORE), str(source), '-platform', 'offscreen',
                               '-platformtheme', 'none', '-style', 'Fusion', '-o', str(target)],
                              env=env, capture_output=True, timeout=180)
        assert proc.returncode == 0, proc.stdout + proc.stderr
    assert len(ET.parse(native).findall('.//Chord/appoggiatura')) == 1
    labels = from_musicxml(roundtrip.read_bytes(), default_key='G')
    assert [(label.measure, label.beat, label.figure) for label in labels] == [(1, 1, 'V65')]
    actual = Counter(converted_labels(native, index, {'V65'}))
    assert actual == Counter({(1, Fraction(0), 3, 'V65'): 1})
    # A verifier must also reject a reviewed position half a beat late.
    analysis['annotations'][0]['at']['beat'] = 1.5
    assert not actual & Counter(expected_labels(original, analysis, index))
