"""The pieces the analysis is checked on, each with a published human analysis.

Chosen on 2026-10-02 (reports/Scores with published analyses.md): the analysis was found
first, then a MusicXML file. `labels` is a chord-by-chord reading by a human analyst that a
script can compare against; `prose` is what a teacher wrote, which a person or the chat model
has to read. Scores and labels are downloaded on first use into out/eval/, which is not
committed: several of the files are non-commercial or carry no licence.
"""

from __future__ import annotations

import io
import os
import re
import zipfile
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from music21 import corpus

ROOT = Path(__file__).parent.parent
OUT = ROOT / "out" / "eval"
CORPUS = Path(os.path.dirname(corpus.__file__))

ROME = "https://raw.githubusercontent.com/MarkGotham/When-in-Rome/master/Corpus/"
ASAP = "https://raw.githubusercontent.com/fosfrancesco/asap-dataset/master/"
DCML = "https://raw.githubusercontent.com/fosfrancesco/piano_corpora_dcml/main/scores/"
TPC = "https://raw.githubusercontent.com/hectorbellmann-art/Tonal-Piano-Corpus/main/"
MUSETRAINER = "https://raw.githubusercontent.com/musetrainer/library/master/scores/"
TEORIA = "https://www.teoria.com/en/articles/"
TONIC_CHORD = "https://tonic-chord.com/"

SONATAS = ROME + "Piano_Sonatas/"
BACH_WTC = ROME + "Keyboard_Other/Bach,_Johann_Sebastian/The_Well-Tempered_Clavier_I/"
LINDENBAUM = ROME + "OpenScore-LiederCorpus/Schubert,_Franz/Winterreise,_D.911/05_Der_Lindenbaum/"
CHOPIN_20 = ROME + "Keyboard_Other/Chopin%2C_Fr%C3%A9d%C3%A9ric/Preludes%2C_Op.28/20/"
HAYDN_104 = ROME + "Orchestral/Haydn,_Franz_Joseph/Symphony_104/1/"


@dataclass(frozen=True)
class Piece:
    id: str
    title: str
    score: str  # URL, or "corpus:" + a path in the music21 corpus
    labels: str | None = None  # RomanText by a human analyst
    prose: tuple[str, ...] = ()
    fix: str | None = None  # "harmony": the analysts' chord labels are inside the file and are removed
    bar_offset: int = 0  # the score's bar number minus the analysis's, where the file counts a pickup as bar 1
    tonal: bool = True  # False where Roman numerals are not the right tool (Debussy, Ravel)
    note: str = ""


PIECES = [
    Piece(
        "bach-prelude-846",
        "Bach, Prelude in C major, BWV 846",
        BACH_WTC + "01/score.mxl",
        BACH_WTC + "01/analysis.txt",
        ("https://edition-gorz.de/WTC-01.pdf", TEORIA + "2017/BWV846/index.php"),
    ),
    Piece(
        "bach-chorale-269",
        "Bach, chorale 'Aus meines Herzens Grunde', BWV 269",
        "corpus:bach/bwv269.mxl",
        "corpus:bach/choraleAnalyses/riemenschneider001.rntxt",
        ("https://alexandermartinblog.wordpress.com/2017/07/17/1-aus-meines-herzens-grunde/",),
    ),
    Piece(
        "bach-fugue-847",
        "Bach, Fugue in C minor, BWV 847",
        "https://raw.githubusercontent.com/VincentCavez/EuterPen/main/scores/BWV_847.xml",
        prose=("https://edition-gorz.de/WTC-02.pdf", "https://musictheory.pugetsound.edu/mt21c/FugueAnalysis.html"),
    ),
    Piece(
        "mozart-k332-1",
        "Mozart, Sonata K. 332, first movement",
        SONATAS + "Mozart,_Wolfgang_Amadeus/K332/1/score.mxl",
        SONATAS + "Mozart,_Wolfgang_Amadeus/K332/1/analysis.txt",
        ("https://www.clarkross.ca/143_Mozart_k332_I_Exp.pdf",),
        note="The prose analysis is detailed for bars 1-93 only.",
    ),
    Piece(
        "mozart-k545-1",
        "Mozart, Sonata K. 545, first movement",
        SONATAS + "Mozart,_Wolfgang_Amadeus/K545/1/score.mxl",
        SONATAS + "Mozart,_Wolfgang_Amadeus/K545/1/analysis.txt",
        (
            "https://static1.squarespace.com/static/5e5b68dff2456f2d5ba27693/t/6742d8df45da2d598bcd016a/1732434144131/Richard+Bruner+Mozart+K.+545+Analysis.pdf",
            TONIC_CHORD + "mozart-piano-sonata-no-16-in-c-major-k-545-analysis/",
        ),
    ),
    Piece(
        "chopin-prelude-20",
        "Chopin, Prelude Op. 28 No. 20",
        CHOPIN_20 + "score.mxl",
        CHOPIN_20 + "analysis.txt",
        (TEORIA + "2018/chopin-preludes/20/index.php",),
    ),
    Piece(
        "chopin-prelude-4",
        "Chopin, Prelude Op. 28 No. 4",
        MUSETRAINER + "Prlude_No._4_in_E_Minor_Op._28_-_Frdric_Chopin.mxl",
        prose=(TEORIA + "chopin-prelude-04/index.php",),
    ),
    Piece(
        "beethoven-pathetique-2",
        "Beethoven, Sonata Op. 13 'Pathétique', second movement",
        ASAP + "Beethoven/Piano_Sonatas/8-2/xml_score.musicxml",
        SONATAS + "Beethoven,_Ludwig_van/Op013%28Pathetique%29/2/analysis.txt",
        (TONIC_CHORD + "beethoven-piano-sonata-no-8-in-c-minor-pathetique-analysis/", "https://musictheory.pugetsound.edu/mt21c/PeriodForm.html"),
    ),
    Piece(
        "beethoven-op2no1-1",
        "Beethoven, Sonata Op. 2 No. 1, first movement",
        ASAP + "Beethoven/Piano_Sonatas/1-1/xml_score.musicxml",
        SONATAS + "Beethoven,_Ludwig_van/Op002_No1/1/analysis.txt",
        (
            "https://www.musictheoryacademy.com/wp-content/uploads/2019/01/Beethoven-sonata-in-F-minor-sonata-form-annotated-sheet-music.pdf",
            TONIC_CHORD + "beethoven-piano-sonata-no-1-in-f-minor-analysis/",
        ),
        bar_offset=1,
    ),
    Piece(
        "haydn-104-1",
        "Haydn, Symphony No. 104, first movement",
        HAYDN_104 + "score.mxl",
        HAYDN_104 + "analysis.txt",
        ("https://resource.download.wjec.co.uk/vtc/2015-16/15-16_23/Haydn%20104%201st%20mvt_%20Music.pdf",),
        note="The score is a one-part reduction, not the orchestral parts.",
    ),
    Piece(
        "schubert-lindenbaum",
        "Schubert, 'Der Lindenbaum', Winterreise No. 5",
        LINDENBAUM + "score.mxl",
        LINDENBAUM + "analysis.txt",
    ),
    Piece(
        "schumann-kinderszenen-1",
        "Schumann, Kinderszenen Op. 15 No. 1",
        TPC + "Schumann%2C%20Robert%20%281810%20-%201856%29/xml/Childhood%20scenes%20Op15/Op15No1.xml",
        ROME + "Keyboard_Other/Schumann,_Robert/Kinderszenen,_Op.15/1/analysis.txt",
        (
            "https://qualifications.pearson.com/content/dam/pdf/A%20Level/Music/2013/Teaching%20and%20learning%20materials/UNIT_3_-_23__Schumann_-_Kinderscenen_Op__15_-_Nos__1_3_and_11_June_2017.pdf",
            "https://www.harmony.org.uk/book/schumann_analysis/schumann_formal_analysis.htm",
        ),
    ),
    Piece(
        "mendelssohn-op19-1",
        "Mendelssohn, Song Without Words Op. 19 No. 1",
        TPC + "Mendelssohn%2C%20Felix%20%281809%20-%201847%29/xml/Lieder%20ohne%20W%C3%B6rte/Op19No1.xml",
        prose=("https://rucore.libraries.rutgers.edu/rutgers-lib/65438/PDF/1/play/",),
        note="The analysis shows a repeat with two endings at bar 15; the file writes it out.",
    ),
    Piece(
        "brahms-op118-2",
        "Brahms, Intermezzo Op. 118 No. 2",
        ASAP + "Brahms/Six_Pieces_op_118/2/xml_score.musicxml",
        prose=(
            "http://www.kellydeanhansen.com/opus118.html",
            "https://napulen.github.io/reports/mcgill/muth251/",
            "https://lukedahn.wordpress.com/2011/11/26/enharmonic-spellings-in-brahms-intermezzo-in-a-op-118-no-2/",
        ),
    ),
    Piece(
        "liszt-sonetto-104",
        "Liszt, Sonetto 104 del Petrarca",
        DCML + "liszt_pelerinage/161.05_Sonetto_104_del_Petrarca.musicxml",
        fix="harmony",
        note="Expert labels exist only in DCML's own format, not yet read by eval/compare.py.",
    ),
    Piece(
        "tchaikovsky-june",
        "Tchaikovsky, 'June: Barcarolle', Op. 37a No. 6",
        DCML + "tchaikovsky_seasons/op37a06.musicxml",
        ROME + "Keyboard_Other/Tchaikovsky%2C_Pyotr/Seasons%2C_Op.37a/6/analysis.txt",
        ("https://article.bbwpublisher.com/uploads/file/files/journals/31/articles/4329/submission/proof/4329-313-12085-1-10-20220927.pdf",),
        fix="harmony",
    ),
    Piece(
        "grieg-notturno",
        "Grieg, Notturno Op. 54 No. 4",
        DCML + "grieg_lyric_pieces/op54n04.musicxml",
        ROME + "Keyboard_Other/Grieg,_Edvard/Lyric_Pieces/Op54_No4/analysis.txt",
        fix="harmony",
    ),
    Piece(
        "ravel-sonatine-1",
        "Ravel, Sonatine, first movement",
        TPC + "Ravel%2C%20Maurice%20%281875%20-%201937%29/xml/Sonatina/Sonatine1.xml",
        prose=("https://scholar.colorado.edu/downloads/xg94hp86p",),
        tonal=False,
        note="The file writes the exposition repeat out: from analysis bar 26 on, file bar = analysis bar + 25.",
    ),
    Piece(
        "ravel-jeux-deau",
        "Ravel, Jeux d'eau",
        "https://raw.githubusercontent.com/esthy13/memuk/main/melody/partitions/ATEPP-1.1/raw/Maurice_Ravel/Jeux_d%27eau%2C_M._30/musicxml_cleaned.musicxml",
        prose=("https://scholarsbank.uoregon.edu/server/api/core/bitstreams/1c78b6ba-97fe-4d56-90fb-15995c420e7b/content",),
        tonal=False,
    ),
    Piece(
        "rachmaninoff-op32-10",
        "Rachmaninoff, Prelude in B minor Op. 32 No. 10",
        ASAP + "Rachmaninoff/Preludes_op_32/10/xml_score.musicxml",
        prose=("https://digital.library.unt.edu/ark:/67531/metadc1248480/m2/1/high_res_d/BUXTON-DISSERTATION-2018.pdf",),
    ),
    Piece(
        "rachmaninoff-op23-5",
        "Rachmaninoff, Prelude in G minor Op. 23 No. 5",
        TPC + "Rachmaninov%2C%20Sergey%20%281873%20-%201943%29/xml/Preludes%20Op23/PreludeOp23No5.xml",
        prose=("https://en.wikipedia.org/wiki/Prelude_in_G_minor_%28Rachmaninoff%29",),
        note="The only analysis found is a thin outline.",
    ),
    Piece(
        "debussy-fille",
        "Debussy, 'La fille aux cheveux de lin'",
        TPC + "Debussy%2C%20Claude%20%281862%20-%201914%29/xml/Pr%C3%A9ludes%20Book1/8%20La%20fille%20aux%20cheveux%20de%20lin.xml",
        prose=(
            "https://gonzalovarela.com/assets/doc/studies/An%C3%A1lisis%20arm%C3%B3nico%20de%20%27La%20fille%20aux%20cheveux%20de%20lin%27%20%28Preludio%20Libro%201%20No.%208%29%20de%20Claude%20Debussy-EN.pdf",
            TEORIA + "debussy-fille-aux-cheveux-de-lin/index.php",
        ),
        tonal=False,
    ),
    Piece(
        "debussy-des-pas",
        "Debussy, 'Des pas sur la neige'",
        TPC + "Debussy%2C%20Claude%20%281862%20-%201914%29/xml/Pr%C3%A9ludes%20Book1/6%20Des%20pas%20sur%20la%20neige.xml",
        prose=(TEORIA + "debussy-des-pas-sur-la-neige/index.php",),
        tonal=False,
    ),
    # added 2026-10-03, to test impressionist music on more than three pieces
    Piece(
        "debussy-voiles",
        "Debussy, 'Voiles'",
        DCML + "debussy_corpus/l117-02_preludes_voiles.musicxml",
        prose=(
            TEORIA + "2020/debussy-preludes/02/index.php",
            "http://vickyjohnson.altervista.org/Analysis_Debussy_Voiles.pdf",  # 'Parting the Veils of Debussy's Voiles', Scottish Music Review
        ),
        tonal=False,
    ),
    Piece(
        "debussy-clair-de-lune",
        "Debussy, 'Clair de lune', Suite bergamasque",
        DCML + "debussy_corpus/l075-03_suite_clair.musicxml",
        "https://raw.githubusercontent.com/DCMLab/debussy_suite_bergamasque/main/harmonies/l075-03_suite_clair.harmonies.tsv",  # DCML experts' labels
        prose=("https://digital.library.txst.edu/bitstream/handle/10877/4330/FERGUSON-THESIS.pdf",),  # Ferguson, MA thesis, Texas State (2012)
        fix="harmony",  # the file carries the DCML experts' chord labels
    ),
]

BY_ID = {piece.id: piece for piece in PIECES}


def _download(source: str, cached: Path) -> bytes:
    if source.startswith("corpus:"):
        return (CORPUS / source.removeprefix("corpus:")).read_bytes()
    if not cached.exists():
        cached.parent.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(source, timeout=60) as response:
            cached.write_bytes(response.read())
    return cached.read_bytes()


def without_harmony(data: bytes) -> bytes:
    """The score with every <harmony> element removed (chord symbols, analysts' labels), compressed .mxl or plain."""
    strip = lambda xml: re.sub(rb"<harmony\b.*?</harmony>\s*", b"", xml, flags=re.DOTALL)
    if data[:2] != b"PK":
        return strip(data)
    source, out = zipfile.ZipFile(io.BytesIO(data)), io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as target:
        for name in source.namelist():
            content = source.read(name)
            target.writestr(name, strip(content) if name.endswith((".xml", ".musicxml")) and "META-INF" not in name else content)
    return out.getvalue()


def score(piece: Piece) -> bytes:
    """The score file, repaired where the manifest says it needs it."""
    data = _download(piece.score, OUT / "scores" / f"{piece.id}{Path(piece.score).suffix}")
    if piece.fix == "harmony":  # the labels would print on the page and give the answer away
        data = re.sub(rb"<harmony\b.*?</harmony>\s*", b"", data, flags=re.DOTALL)
    return data


def labels(piece: Piece) -> str | None:
    """The expert reading as RomanText; a DCML harmonies table is converted (eval/dcml.py)."""
    if piece.labels is None:
        return None
    if piece.labels.endswith(".harmonies.tsv"):
        from engine.render import load_toolkit
        from engine.score import ScoreIndex
        from eval import dcml

        table = _download(piece.labels, OUT / "labels" / f"{piece.id}.harmonies.tsv").decode("utf-8")
        return dcml.to_romantext(table, ScoreIndex(load_toolkit(score(piece)).getMEI()))
    return _download(piece.labels, OUT / "labels" / f"{piece.id}.rntxt").decode("utf-8")


def rome_tree() -> list[str]:
    """Every file path in the When in Rome repository, fetched once from GitHub and cached in out/eval/."""
    cached = OUT / "when-in-rome-tree.txt"
    if not cached.exists():
        import json as _json

        url = "https://api.github.com/repos/MarkGotham/When-in-Rome/git/trees/master?recursive=1"
        with urllib.request.urlopen(url, timeout=120) as response:
            tree = _json.loads(response.read())["tree"]
        cached.parent.mkdir(parents=True, exist_ok=True)
        cached.write_text("\n".join(item["path"] for item in tree))
    return cached.read_text().split("\n")
