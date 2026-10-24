"""End to end: the review gallery draws real manifest items at two refs, stamps every picture and writes the page;
a manifest line it cannot draw stops the run with no page."""

import json
import subprocess
import sys
from pathlib import Path

import pytest
from PIL import Image

ROOT = Path(__file__).parent.parent


def gallery(*args, cwd=ROOT):
    return subprocess.run([sys.executable, "-m", "tools.review_gallery", *args], cwd=cwd, capture_output=True,
                          text=True, timeout=600)


def worktrees():
    return subprocess.run(["git", "worktree", "list"], cwd=ROOT, capture_output=True, text=True).stdout


def test_two_items_make_stamped_pairs_and_a_page(tmp_path):
    before = worktrees()
    done = gallery("--out", str(tmp_path), "--items", "2,3")
    assert done.returncode == 0, done.stderr
    assert worktrees() == before, "temporary worktrees were left behind"
    page = (tmp_path / "index.html").read_text()
    sources = json.loads((tmp_path / "sources.json").read_text())
    manifest = json.loads((ROOT / "tools/review_manifest.json").read_text())
    pictures = {p["id"]: (item, p) for item in manifest["items"] if item["item"] in (2, 3) for p in item["pictures"]}
    for picture_id, (item, picture) in pictures.items():
        for side in ("before", "after"):
            shown = [s for s in sources if s["item_picture"] == picture_id and s["side"] == side]
            assert shown, f"{picture_id} {side} missing"
            for source in shown:
                for key in ("image", "chat_image"):
                    path = tmp_path / source[key]
                    assert path.is_file() and source[key] in page
                stamp = " ".join(source["stamp"])
                assert picture["input"] in stamp and f"bars {picture['bars']}" in stamp
                ref = item["before"] if side == "before" else "HEAD"
                assert f"ref {ref} = commit {source['commit'][:10]}" in stamp
                assert Image.open(tmp_path / source["chat_image"]).width == 700
                full = Image.open(tmp_path / source["image"]).convert("L")
                strip = full.crop((0, full.height - 40, full.width // 2, full.height))
                assert strip.getextrema()[0] < 200, f"{source['image']}: no stamp text in the bottom strip"
    assert 'id="note-2"' in page and 'id="note-3"' in page and "Copy all my notes" in page


@pytest.mark.parametrize("change, named", [({"input": "tests/data/no_such_score.musicxml"}, "no_such_score.musicxml"),
                                           ({"bars": "90-91"}, "bad-line")])
def test_a_line_it_cannot_draw_stops_the_run(tmp_path, change, named):
    manifest = json.loads((ROOT / "tools/review_manifest.json").read_text())
    item = next(item for item in manifest["items"] if item["item"] == 2)
    item["pictures"].append({**item["pictures"][0], "id": "bad-line", **change})
    bad = tmp_path / "manifest.json"
    bad.write_text(json.dumps(manifest))
    out = tmp_path / "out"
    done = gallery("--out", str(out), "--items", "2", "--manifest", str(bad))
    assert done.returncode == 1
    assert named in done.stderr
    assert not (out / "index.html").exists()
