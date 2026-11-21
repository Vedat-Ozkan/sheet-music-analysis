import json
import re
from pathlib import Path

import pytest

from engine import read_pdf
from server import app

ROOT = Path(__file__).parent.parent
SITE = ROOT / "site"


def page(name: str) -> str:
    return re.sub(r"\s+", " ", (SITE / name).read_text())


def stored_scores_days() -> int:
    deploy = (ROOT / "server/deploy.sh").read_text()
    rules = json.loads(re.search(r"lifecycle\.json <<'EOF'\n(.*?)\nEOF", deploy, re.S).group(1))["rule"]
    return next(rule["condition"]["age"] for rule in rules if "scores/" in rule["condition"]["matchesPrefix"])


@pytest.mark.parametrize("name", ["terms.html", "privacy.html", "docs.html"])
def test_retention_matches_the_storage_lifecycle(name):
    days = stored_scores_days()
    assert f"kept for {days} days" in page(name) or f"last {days} days" in page(name)


def test_docs_state_the_server_limits():
    docs = page("docs.html")
    assert f"up to {app.PERSON_SCORE_LIMIT} new scores a day" in docs
    assert f"only the first {read_pdf.READ_PAGES} are read" in docs
    assert f"up to {app.MAX_SCORE_BYTES // (1024 * 1024)} MB" in docs


@pytest.mark.parametrize("name", sorted(path.name for path in SITE.glob("*.html")))
def test_no_stale_wording(name):
    text = page(name).lower()
    for stale in ("two days", "function colours", "a few minutes"):
        assert stale not in text


def test_every_repository_file_the_readme_names_exists():
    readme = (ROOT / "README.md").read_text()
    named = set(re.findall(r"`((?:\.github|docs|engine|eval|plugin|proxy|server|site|skill|tests|tools)/[\w./-]+\.\w+)`", readme))
    assert named and not sorted(path for path in named if not (ROOT / path).exists())
