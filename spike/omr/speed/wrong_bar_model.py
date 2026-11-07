import json
import sys
from pathlib import Path

import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.inspection import permutation_importance
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

HERE = Path(__file__).resolve().parent
ROWS = Path("/home/kema/projects/sheet-music-plugin/spike/omr/speed/cache/wrong_bars/marks1.jsonl")
OUT = HERE / "results" / "wrong-bars-marks1.json"
META = {"set", "pdf", "piece", "group", "data_set", "bar", "paired", "wrong", "wrong_exact", "wrong_notes", "truth_bars", "truth_unpaired"}
DATA_SETS = ["real scan", "olimpic scan", "made scan", "engraved", "all"]
SHARES = [0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8]
TARGETS = [0.9, 0.95]
FOLDS = 5


def models():
    return {
        "logistic": lambda: make_pipeline(StandardScaler(), LogisticRegression(max_iter=2000)),
        "boosted trees": lambda: HistGradientBoostingClassifier(max_iter=200, learning_rate=0.05, max_leaf_nodes=15,
                                                                min_samples_leaf=40, random_state=0),
    }


def out_of_fold(make, x, y, groups, folds=FOLDS):
    scores = np.zeros(len(y))
    for train, test in GroupKFold(folds).split(x, y, groups):
        scores[test] = make().fit(x[train], y[train]).predict_proba(x[test])[:, 1]
    return scores


def threshold_for(scores, y, target):
    order = np.argsort(scores)
    right = np.cumsum(1 - y[order])
    precision = right / np.arange(1, len(y) + 1)
    ok = np.nonzero(precision >= target)[0]
    return scores[order][ok[-1]] if len(ok) else -1.0


def held_out_operating_points(make, x, y, groups):
    shade = {target: np.zeros(len(y), bool) for target in TARGETS}
    for train, test in GroupKFold(FOLDS).split(x, y, groups):
        inner = out_of_fold(make, x[train], y[train], groups[train], folds=4)
        model = make().fit(x[train], y[train])
        test_scores = model.predict_proba(x[test])[:, 1]
        for target in TARGETS:
            shade[target][test] = test_scores > threshold_for(inner, y[train], target)
    return shade


def summary(shade, y):
    unshaded = ~shade
    return {
        "bars": int(len(y)), "wrong": int(y.sum()),
        "shaded_share": round(float(shade.mean()), 3),
        "unshaded": int(unshaded.sum()),
        "unshaded_right": round(float(1 - y[unshaded].mean()), 3) if unshaded.any() else None,
        "wrong_unshaded": int(y[unshaded].sum()),
        "wrong_shaded_share": round(float(shade[y == 1].mean()), 3) if y.any() else None,
        "right_but_shaded": int((shade & (y == 0)).sum()),
    }


def curve(scores, y, mask):
    rows = []
    for share in SHARES:
        cut = np.quantile(scores, 1 - share)
        rows.append({"share_target": share, **summary((scores > cut)[mask], y[mask])})
    return rows


def main():
    rows = [json.loads(line) for line in ROWS.read_text().splitlines()]
    names = [key for key in rows[0] if key not in META]
    x = np.array([[row[name] for name in names] for row in rows], float)
    groups = np.array([row["group"] for row in rows])
    kinds = np.array([row["data_set"] for row in rows])
    current = x[:, names.index("shaded")].astype(bool)
    masks = {kind: (kinds == kind) if kind != "all" else np.ones(len(rows), bool) for kind in DATA_SETS}
    report = {"features": names, "pdfs": len({row["pdf"] for row in rows}), "groups": len(set(groups)),
              "truth_bars_unpaired": {kind: int(sum(r["truth_unpaired"] for r in {r["pdf"]: r for r in rows if kind == "all" or r["data_set"] == kind}.values()))
                                      for kind in DATA_SETS}}
    for label in ("wrong", "wrong_exact"):
        y = np.array([row[label] for row in rows])
        result = {"current": {kind: summary(current[mask], y[mask]) for kind, mask in masks.items()}}
        for name, make in models().items():
            scores = out_of_fold(make, x, y, groups)
            points = held_out_operating_points(make, x, y, groups)
            result[name] = {
                "auc": {kind: round(roc_auc_score(y[mask], scores[mask]), 3) for kind, mask in masks.items() if 0 < y[mask].mean() < 1},
                "auc_current": {kind: round(roc_auc_score(y[mask], current[mask]), 3) for kind, mask in masks.items() if 0 < y[mask].mean() < 1},
                "curve": {kind: curve(scores, y, mask) for kind, mask in masks.items()},
                "held_out": {f"target {target}": {kind: summary(points[target][mask] | current[mask], y[mask])
                                                  for kind, mask in masks.items()} for target in TARGETS},
            }
            if label == "wrong":
                result[name]["importance"] = importance(make, x, y, groups, names)
                result[name]["left_at_half"] = left_at_half(scores, y, rows)
        report[label] = result
    OUT.write_text(json.dumps(report, indent=1))
    show(report)


def left_at_half(scores, y, rows):
    left = (scores <= np.quantile(scores, 0.5)) & (y == 1)
    sizes = [rows[i]["wrong_notes"] for i in np.nonzero(left)[0]]
    buckets = {"unpaired": sum(n < 0 for n in sizes), "1 note": sizes.count(1), "2 notes": sizes.count(2),
               "3-5 notes": sum(3 <= n <= 5 for n in sizes), "6+ notes": sum(n >= 6 for n in sizes)}
    kinds = {}
    for i in np.nonzero(left)[0]:
        kinds[rows[i]["data_set"]] = kinds.get(rows[i]["data_set"], 0) + 1
    return {"bars": int(left.sum()), "notes_off": buckets, "by_data_set": kinds}


def importance(make, x, y, groups, names):
    total = np.zeros(len(names))
    for train, test in GroupKFold(FOLDS).split(x, y, groups):
        model = make().fit(x[train], y[train])
        total += permutation_importance(model, x[test], y[test], scoring="roc_auc", n_repeats=3, random_state=0).importances_mean
    ranked = sorted(zip(names, total / FOLDS), key=lambda item: -item[1])
    return {name: round(float(value), 4) for name, value in ranked}


def show(report):
    for label in ("wrong", "wrong_exact"):
        print(f"\n== label {label}")
        for kind, s in report[label]["current"].items():
            print(f"current  {kind:13} bars {s['bars']:5} wrong {s['wrong']:5} shaded {s['shaded_share']:.3f} "
                  f"unshaded right {s['unshaded_right']} wrong shaded {s['wrong_shaded_share']} right-but-shaded {s['right_but_shaded']}")
        for name in models():
            r = report[label][name]
            print(f"-- {name} auc {r['auc']}  (current shading as score: {r['auc_current']})")
            for target, by_kind in r["held_out"].items():
                for kind, s in by_kind.items():
                    print(f"   held-out {target} {kind:13} shaded {s['shaded_share']:.3f} unshaded right {s['unshaded_right']} "
                          f"wrong left {s['wrong_unshaded']}/{s['wrong']} right-but-shaded {s['right_but_shaded']}")
            if "left_at_half" in r:
                print("   wrong bars left unshaded at 50% shaded:", r["left_at_half"])
            if "importance" in r:
                print("   importance", list(r["importance"].items())[:10])
    print("\nunpaired truth bars (missing from reading, cannot be shaded):", report["truth_bars_unpaired"])


if __name__ == "__main__":
    sys.exit(main())
