import argparse, json, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "bench"))
import build as B  # noqa: E402
from features import totals  # noqa: E402

LIED = "https://github.com/OpenScore/Lieder/tree/main/scores/"
CC0 = "CC0 1.0 (OpenScore)"
H = [
    ("h-schubert-aufenthalt", "Schubert,_Franz/Schwanengesang,_D.957/05_Aufenthalt", 40, ["ms", "ly"]),
    ("h-holmes-barque-des-amours", "Holmès,_Augusta_Mary_Anne/20_Mélodies/03_La_barque_des_amours", 40, ["ms", "ly"]),
    ("h-schubert-erlkonig", "Schubert,_Franz/_/Der_Erlkönig,_D.328", 40, ["ms", "ly"]),
    ("h-bizet-absence", "Bizet,_Georges/20_Mélodies,_Op.21/13_Absence", 40, ["ms", "ly"]),
    ("h-clara-schumann-liebeszauber", "Schumann,_Clara/6_Lieder,_Op.13/3_Liebeszauber", 40, ["ms"]),
    ("h-haydn-o-tuneful-voice", "Haydn,_Joseph/10_Canzonets/08_O_tuneful_Voice,_Hob.XXVIa42", 40, ["ms"]),
    ("h-brahms-fruhlingstrost", "Brahms,_Johannes/9_Lieder_und_Gesänge,_Op.63/1_Frühlingstrost", 40, ["ms"]),
    ("h-lang-traumbild", "Lang,_Josephine/2_Lieder,_Op.28/1_Traumbild", 40, ["ms"]),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lieder", required=True)
    ap.add_argument("--lilypond-bin", required=True)
    a = ap.parse_args()
    manifest = {"pieces": {}, "pdfs": [], "not_built": []}
    for pid, sub, bars, engravers in H:
        src = next(Path(a.lieder, "scores", sub).glob("*.mxl"))
        truth = HERE / "truth" / f"{pid}.musicxml"
        truth.write_bytes(B.excerpt(src.read_bytes(), bars) if bars else src.read_bytes())
        manifest["pieces"][pid] = {"kind": "song", "truth": str(truth.relative_to(HERE)), "source_url": LIED + sub + "/",
                                   "licence": CC0, "excerpt_first_bars": bars, "truth_counts": totals(truth.read_bytes())}
        for eng in engravers:
            out = HERE / "pdfs" / f"{pid}--{eng}.pdf"
            try:
                B.musescore(truth, out) if eng == "ms" else B.lilypond(truth, out, Path(a.lilypond_bin))
                n = B.pages(out)
                manifest["pdfs"].append({"pdf": f"pdfs/{out.name}", "piece": pid, "engraver": eng, "pages": n})
            except Exception as e:  # noqa: BLE001
                err = getattr(e, "stderr", b"")
                manifest["not_built"].append({"piece": pid, "engraver": eng, "reason": f"{type(e).__name__}: {str(err)[-200:] if err else e}"})
    (HERE / "manifest.json").write_text(json.dumps(manifest, indent=1, ensure_ascii=False))
    print(len(manifest["pieces"]), "pieces,", len(manifest["pdfs"]), "pdfs; not built:", manifest["not_built"])


if __name__ == "__main__":
    main()
