"""Six fresh CC0 songs chosen from selection-ranking.txt (truth triplets printed without a number), before any OMR.
# Brahms Op.6/6 (rank 4) was replaced by Faisst Op.18/3 (rank 12): MuseScore crashed engraving it (exit 40), before any OMR.

Usage: .venv/bin/python spike/omr/bench-heldout3/build.py --lieder DIR
Uses the same MuseScore 4 export and first-bars excerpt as the original benchmark.
"""
import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / 'bench'))
import build as B
from features import totals

# Fixed before reading: six composers, contrasting densities, first 24 bars each.
PIECES = [
 ('h3-schumann-fruehlingsnacht', 'Schumann,_Robert/Liederkreis,_Op.39/12_Frühlingsnacht'),
 ('h3-franz-lotosblume', 'Franz,_Robert/6_Lieder,_Op.25/1_Die_Lotosblume'),
 ('h3-faisst-sehnsucht', 'Faisst,_Clara_Mathilda/4_Lieder,_Op.18/3_Sehnsucht'),
 ('h3-schubert-kraehe', 'Schubert,_Franz/Winterreise,_D.911/15_Die_Kraehe'),
 ('h3-lang-auf-der-reise', 'Lang,_Josephine/_/Auf_der_Reise,_Op.22'),
 ('h3-hensel-mayenlied', 'Hensel,_Fanny/6_Lieder,_Op.1/4_Mayenlied'),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--lieder', required=True)
    args = ap.parse_args()
    old = [json.loads((HERE.parent / d / 'manifest.json').read_text()) for d in ('bench', 'bench-heldout', 'bench-heldout2')]
    manifest = {'pieces': {}, 'pdfs': [], 'not_built': []}
    for pid, sub in PIECES:
        url = 'https://github.com/OpenScore/Lieder/tree/main/scores/' + sub + '/'
        assert all(url.rstrip('/') != p['source_url'].rstrip('/') for m in old for p in m['pieces'].values())
        src = next(Path(args.lieder, 'scores', sub).glob('*.mxl'))
        truth = HERE / 'truth' / f'{pid}.musicxml'
        truth.write_bytes(B.excerpt(src.read_bytes(), 32))
        counts = totals(truth.read_bytes())
        manifest['pieces'][pid] = dict(kind='song', truth=str(truth.relative_to(HERE)), source_url=url,
                                      licence='CC0 1.0 (OpenScore)', excerpt_first_bars=32, truth_counts=counts)
        pdf = HERE / 'pdfs' / f'{pid}--ms.pdf'
        B.musescore(truth, pdf)
        manifest['pdfs'].append(dict(pdf=str(pdf.relative_to(HERE)), piece=pid, engraver='ms', pages=B.pages(pdf)))
        print(pid, flush=True)
    (HERE / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
