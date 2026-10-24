"""Conservative training provenance from published lists, without importing model code."""

from __future__ import annotations

import ast
import re
import unicodedata
from pathlib import Path


def catalogue_readings(corpus: Path) -> list[Path]:
    # Some works have only a named analyst's reading, with no primary file.
    folders = {}
    for path in sorted(corpus.rglob("analysis*.txt")):
        if "Kostka" not in str(path):
            if path.parent not in folders or path.name == "analysis.txt":
                folders[path.parent] = path
    return [folders[folder] for folder in sorted(folders)]


def assignments(path: Path) -> dict:
    found = {}
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                name = target.id if isinstance(target, ast.Name) else target.attr if isinstance(target, ast.Attribute) else None
                if name in ("annotation_score_duples", "splits", "test_pieces", "prob_pieces"):
                    try:
                        found[name] = ast.literal_eval(node.value)
                    except (ValueError, TypeError):
                        pass
    return found


def canonical(path: str) -> str:
    path = path.replace("Etudes_and_Preludes", "Keyboard_Other").replace("String_Quartets", "Quartets")
    path = unicodedata.normalize("NFKD", path)
    path = "".join(c for c in path if not unicodedata.combining(c)).lower()
    path = re.sub(r"\d+", lambda m: str(int(m[0])), path)
    return re.sub(r"[^a-z0-9/]", "", path)


class Training:
    def __init__(self, augmented: Path, dlc_source: Path, dataset: Path):
        self.augmented = {}
        for path in sorted((augmented / "AugmentedNet/data").glob("*.py")):
            data = assignments(path)
            for split, names in data.get("splits", {}).items():
                for name in names:
                    annotation, score = data["annotation_score_duples"][name]
                    entry = dict(id=name, split=split, source=str(path), annotation=annotation, score=score)
                    if "/Corpus/" in annotation:
                        folder = "Corpus/" + annotation.split("/Corpus/")[1].rsplit("/", 1)[0]
                        self.augmented.setdefault(canonical(folder), []).append(entry)
                    elif name.startswith("mps-"):
                        _, k, movement = name.split("-")
                        folder = f"Corpus/Piano_Sonatas/Mozart,_Wolfgang_Amadeus/{k}/{movement}"
                        self.augmented.setdefault(canonical(folder), []).append(entry)
        exclusions = assignments(dlc_source)
        self.test = set(exclusions["test_pieces"])
        self.problem = set(exclusions["prob_pieces"])
        self.dlc_source = str(dlc_source)
        self.dlc = {f"{p.parent.name}_{p.stem}": p for p in (dataset / "pitch_arrays/DLC").glob("*/*.tsv")}
        self.trained_scores = {
            Path(e["score"]).name: e for entries in self.augmented.values() for e in entries
            if e["split"] in ("training", "validation")
            and ("music21/corpus/" in e["score"] or "/corrections/BachChorales/" in e["score"])
        }

    def judgement(self, folder: str, remote: dict) -> dict:
        augmented = self.augmented.get(canonical(folder), [])
        score_identity = Path(remote.get("remote_score_music21", "")).name
        if score_identity in self.trained_scores:
            entry = self.trained_scores[score_identity]
            if not any(e["id"] == entry["id"] for e in augmented):
                augmented = [*augmented, dict(entry, identity_match=score_identity)]
        dlc_id = None
        for value in remote.values():
            if not isinstance(value, str):
                continue
            match = re.search(r"(?:githubusercontent.com|github.com)/DCMLab/([^/]+)/[^/]+/(?:harmonies|MS3)/([^/]+)", value)
            if match:
                stem = re.sub(r"(?:\.harmonies)?\.(?:tsv|mscx)$", "", match[2])
                dlc_id = match[1] + "_" + stem
                break
        if not dlc_id and "Piano_Sonatas/Beethoven" in folder and remote.get("sonata_number"):
            dlc_id = f"beethoven_piano_sonatas_{remote['sonata_number']:02d}-{remote['movement']}"
        if not dlc_id and "Piano_Sonatas/Mozart" in folder:
            dlc_id = "mozart_piano_sonatas_" + "-".join(folder.split("/")[-2:])
        if not dlc_id and "/Schubert,_Franz/Winterreise," in folder:
            number = int(folder.rsplit("/", 1)[1].split("_")[0])
            dlc_id = f"schubert_winterreise_n{number:02d}"
        if not dlc_id and "/Schumann,_Robert/Liederkreis,_Op.39/" in folder:
            number = int(folder.rsplit("/", 1)[1].split("_")[0])
            dlc_id = f"schumann_liederkreis_op39n{number:02d}"
        if not dlc_id and "/Mahler,_Gustav/Kindertotenlieder/" in folder:
            number = int(folder.rsplit("/", 1)[1].split("_")[0])
            dlc_id = next((n for n in self.dlc if n.startswith(f"mahler_kindertotenlieder_kindertotenlieder_{number:02d}_")), None)
        if not dlc_id and "/Schumann,_Clara/" in folder:
            match = re.search(r"/[^/]*Op\.(13|23)/(\d+)", folder)
            if match:
                dlc_id = next((n for n in self.dlc if n.startswith(f"c_schumann_lieder_op{match[1]}no{int(match[2])} ")), None)
        if dlc_id and dlc_id not in self.dlc:
            # WiR sometimes omits an opus suffix retained by the DLC filename.
            candidates = [n for n in self.dlc if n.startswith(dlc_id + "op")]
            if len(candidates) == 1:
                dlc_id = candidates[0]
        dlc_present = dlc_id in self.dlc
        excluded = "test_pieces" if dlc_id in self.test else "prob_pieces" if dlc_id in self.problem else None
        seen = any(e["split"] in ("training", "validation") for e in augmented) or (dlc_present and not excluded)
        evidence = dict(augmented=augmented or [{"source": "AugmentedNet/data/*.py", "status": "absent from all published duples"}],
                        dlc=dict(id=dlc_id, present=dlc_present, exclusion=excluded, source=self.dlc_source,
                                 dataset_file=str(self.dlc[dlc_id]) if dlc_present else None))
        certainty = "confirmed" if seen or (augmented and excluded) else "probable"
        return dict(status="trained" if seen else "unseen", certainty=certainty, evidence=evidence)
