"""Score cached readings with official engine counters; never invokes Audiveris.

Usage: .venv/bin/python .../evaluate.py BENCHDIR RESULTS.json OUTPUT.json
Gains/losses use original pitch-aligned bar pairs, even if the new alignment changes.
"""
import collections
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path[:0] = [str(ROOT), str(ROOT / 'spike/omr'), str(ROOT / 'spike/omr/bench')]
from engine.triplets import infer_triplets


def worker(truth, cached):
    from engine_check import load
    from compare import align
    data = Path(cached).read_bytes()
    fixed = infer_triplets(data)
    with tempfile.TemporaryDirectory() as tmp:
        after = Path(tmp) / 'after.musicxml'
        after.write_bytes(fixed)
        scores = []
        for path in (cached, after):
            run = subprocess.run([sys.executable, str(ROOT / 'spike/omr/bench/score_one.py'), truth, str(path)],
                                 capture_output=True, text=True, check=True)
            scores.append(json.loads(run.stdout.strip().splitlines()[-1]))
    t = load(Path(truth).read_bytes())[0]
    before, after = load(data)[0], load(fixed)[0]
    pairs = align([(b,) for b in t], [(b,) for b in before])[0]
    gained = lost = 0
    for i, j in pairs:
        a, b = t[i] & before[j], t[i] & after[j]
        gained += sum((b - a).values())
        lost += sum((a - b).values())
    return dict(before=scores[0], after=scores[1], recovered=gained, wrongly_changed=lost, changed=fixed != data)


def main():
    if sys.argv[1] == '--worker':
        print(json.dumps(worker(*sys.argv[2:4])))
        return
    bd, results, output = map(Path, sys.argv[1:4])
    manifest, saved = json.loads((bd / 'manifest.json').read_text()), json.loads(results.read_text())
    rows = []
    totals = collections.Counter()
    for p in manifest['pdfs']:
        key = hashlib.sha256((bd / p['pdf']).read_bytes() + saved['audiveris_install'].encode()).hexdigest()[:32]
        cached = bd / 'cache' / f'{key}.musicxml'
        truth = bd / manifest['pieces'][p['piece']]['truth']
        run = subprocess.run([sys.executable, __file__, '--worker', str(truth), str(cached)],
                             capture_output=True, text=True, check=True)
        row = dict(pdf=p['pdf'], cache=str(cached), **json.loads(run.stdout.strip().splitlines()[-1]))
        # Assert the baseline is the production run, rather than a different cache/settings selection.
        original = next(r for r in saved['pdfs'] if r['pdf'] == p['pdf'])['score']
        for k in ('truth_notes', 'shared_pitch', 'shared_pitch_onset'):
            assert row['before'][k] == original[k], (p['pdf'], k)
        rows.append(row)
        totals.update(recovered=row['recovered'], wrongly_changed=row['wrongly_changed'], truth=row['before']['truth_notes'])
        for when in ('before', 'after'):
            for k in ('shared_pitch', 'shared_pitch_onset'):
                totals[f'{when}_{k}'] += row[when][k]
        if row['changed']:
            print(p['pdf'], row['recovered'], row['wrongly_changed'], flush=True)
    result = dict(totals=dict(totals), pdfs=rows,
                  worse=[r['pdf'] for r in rows if r['after']['shared_pitch_onset'] < r['before']['shared_pitch_onset']],
                  any_regression=[r['pdf'] for r in rows if r['wrongly_changed']])
    output.write_text(json.dumps(result, indent=1))
    print(json.dumps(result['totals']), flush=True)


if __name__ == '__main__':
    main()
