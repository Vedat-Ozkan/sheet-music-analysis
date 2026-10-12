"""Read six fresh PDFs sequentially with production read_pdf, retaining pre-fix bytes.

No changes to orchestration: the wrapper captures the input to the final post-fix.
Usage: .venv/bin/python spike/omr/bench-heldout3/read.py --audiveris PATH
"""
import argparse
import hashlib
import importlib
import json
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path[:0] = [str(ROOT), str(HERE.parent / 'bench')]
from run import install_signature
reader = importlib.import_module('engine.read_pdf')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--audiveris', required=True)
    ap.add_argument('--shard', default='0/1', help='i/n: read every n-th PDF so up to 4 can run at once; results go to results-prod2.shardI.json, merge by hand')
    args = ap.parse_args()
    manifest = json.loads((HERE / 'manifest.json').read_text())
    sig = install_signature(Path(args.audiveris)) + 'prod2-prefixed'
    rows = []
    original = reader.infer_triplets
    captured = []

    def capture(data):
        captured.append(data)
        return original(data)

    reader.infer_triplets = capture
    si, sn = map(int, args.shard.split('/'))
    for p in manifest['pdfs'][si::sn]:
        data = (HERE / p['pdf']).read_bytes()
        key = hashlib.sha256(data + sig.encode()).hexdigest()[:32]
        cache = HERE / 'cache' / f'{key}.musicxml'
        meta = cache.with_suffix('.json')
        if not meta.exists():
            captured.clear()
            started = time.monotonic()
            reading = reader.read_pdf(data, args.audiveris)
            assert len(captured) == 1
            cache.write_bytes(captured[0])
            cache.with_suffix('.after.musicxml').write_bytes(reading.musicxml)
            meta.write_text(json.dumps(dict(ok=True, pages=reading.pages, scan=reading.scan,
                                            skipped=reading.skipped, seconds=round(time.monotonic() - started, 1))))
        r = json.loads(meta.read_text())
        truth = HERE / manifest['pieces'][p['piece']]['truth']
        scored = subprocess.run([sys.executable, str(HERE.parent / 'bench/score_one.py'), str(truth), str(cache)],
                                capture_output=True, text=True, check=True)
        rows.append({**p, 'score': json.loads(scored.stdout.strip().splitlines()[-1]), **r})
        (HERE / ('results-prod2.json' if sn == 1 else f'results-prod2.shard{si}.json')).write_text(json.dumps(dict(audiveris_install=sig, pdfs=rows), indent=1))
        print(p['pdf'], r['seconds'], flush=True)


if __name__ == '__main__':
    main()
