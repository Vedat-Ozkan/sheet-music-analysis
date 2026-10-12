"""Six fresh CC0 songs, selected by truth triplets before any OMR evaluation.

Usage: .venv/bin/python spike/omr/bench-heldout2/build.py --lieder DIR
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
 ('h2-bantock-ghost-road', 'Bantock,_Granville/5_Songs_from_the_Chinese_Poets,_1st_Series/2_The_Ghost_Road'),
 ('h2-beach-years-at-spring', 'Beach,_Amy/3_Browning_Songs,_Op.44/1_The_Year’s_at_the_Spring'),
 ('h2-berg-nacht', 'Berg,_Alban/7_frühe_Lieder/1_Nacht'),
 ('h2-bizet-adieux', 'Bizet,_Georges/Feuilles_d’album/2_Adieux_à_Suzon'),
 ('h2-boulanger-poete', 'Boulanger,_Lili/Clairières_dans_le_ciel/04_Un_poète_disait'),
 ('h2-brahms-liebestreu', 'Brahms,_Johannes/6_Songs,_Op.3/1_Liebestreu'),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--lieder', required=True)
    args = ap.parse_args()
    old = [json.loads((HERE.parent / d / 'manifest.json').read_text()) for d in ('bench', 'bench-heldout')]
    manifest = {'pieces': {}, 'pdfs': [], 'not_built': []}
    for pid, sub in PIECES:
        url = 'https://github.com/OpenScore/Lieder/tree/main/scores/' + sub + '/'
        assert all(url.rstrip('/') != p['source_url'].rstrip('/') for m in old for p in m['pieces'].values())
        src = next(Path(args.lieder, 'scores', sub).glob('*.mxl'))
        truth = HERE / 'truth' / f'{pid}.musicxml'
        truth.write_bytes(B.excerpt(src.read_bytes(), 24))
        counts = totals(truth.read_bytes())
        manifest['pieces'][pid] = dict(kind='song', truth=str(truth.relative_to(HERE)), source_url=url,
                                      licence='CC0 1.0 (OpenScore)', excerpt_first_bars=24, truth_counts=counts)
        pdf = HERE / 'pdfs' / f'{pid}--ms.pdf'
        B.musescore(truth, pdf)
        manifest['pdfs'].append(dict(pdf=str(pdf.relative_to(HERE)), piece=pid, engraver='ms', pages=B.pages(pdf)))
        print(pid, flush=True)
    (HERE / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
