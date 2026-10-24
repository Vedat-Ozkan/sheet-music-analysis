"""The display rules (tools/display_check.py) on the whole corpus: one test per corpus item, plus the page pins.

The corpus is drawn once, in parallel, through the real entry points. A failure lists every violation of that item;
`python -m tools.display_check` prints the same list with crops of each one."""

from pathlib import Path

import pytest

from tools import display_check

ROOT = Path(__file__).parent.parent
ITEMS = display_check.corpus(ROOT)


@pytest.fixture(scope="module")
def report():
    return display_check.run(ROOT)


def _lines(violations):
    return "\n".join(display_check.Violation(**v).line() for v in violations)


@pytest.mark.slow
@pytest.mark.parametrize("group, name", ITEMS, ids=[f"{g}/{n}" for g, n in ITEMS])
def test_display_rules(report, group, name):
    result = next(r for r in report["results"] if r["item"] == f"{group}/{name}")
    if result["error"] and "no cached Audiveris reading" in result["error"]:
        pytest.skip(result["error"].splitlines()[0])
    assert not result["error"], result["error"]
    assert not result["violations"], "\n" + _lines(result["violations"])


@pytest.mark.slow
def test_page_counts_match_the_pinned_baseline(report):
    assert not report["pins"], "\n" + _lines(report["pins"])
