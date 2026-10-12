from pathlib import Path

import pytest

from engine.annotations import AnnotationList

ROOT = Path(__file__).parent.parent


@pytest.fixture(scope="session")
def chopin() -> bytes:
    return (ROOT / "tests/data/chopin_nocturne_op9_no2.mxl").read_bytes()


@pytest.fixture(scope="session")
def chopin_annotations() -> AnnotationList:
    return AnnotationList.model_validate_json((ROOT / "examples/chopin_op9_no2_m1-8.json").read_text())


# --- Make the suite give the same result in any worktree, with no env vars. ---
# Model runtime, checkpoint and a few fixtures are git-ignored, so a fresh
# worktree lacks them. We borrow them from the main checkout; if even that lacks
# them the tests SKIP with a reason (never silently pass).
import os  # noqa: E402
import subprocess  # noqa: E402


def main_checkout() -> Path:
    try:
        common = subprocess.run(
            ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
            cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
        return Path(common).parent
    except Exception:
        return ROOT


MAIN = main_checkout()
# Ignored (or partly ignored) trees that tests read under ROOT.
BORROWED = ["out/engraving", "spike/omr/truth"]


def _borrow() -> None:
    if MAIN == ROOT:
        return
    for rel, env, default in [
        (".venv-agnn/bin/python", "ANALYSISGNN_PYTHON", None),
        ("artifacts/models/model.ckpt", "ANALYSISGNN_CHECKPOINT", None),
    ]:
        if not (ROOT / rel).exists() and (MAIN / rel).exists():
            os.environ.setdefault(env, str(MAIN / rel))
    for rel in BORROWED:
        mine, theirs = ROOT / rel, MAIN / rel
        if not mine.exists() and theirs.exists():
            mine.parent.mkdir(parents=True, exist_ok=True)
            mine.symlink_to(theirs, target_is_directory=True)
            # keep `git status` clean: the link is local plumbing, never committed
            try:
                exclude = Path(subprocess.run(
                    ["git", "rev-parse", "--path-format=absolute", "--git-path", "info/exclude"],
                    cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip())
                with exclude.open("a") as f:
                    f.write(f"/{rel}\n")
            except Exception:
                pass


_borrow()


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """A missing ignored fixture is a skip with a reason, not a failure."""
    outcome = yield
    report = outcome.get_result()
    if call.excinfo and call.excinfo.errisinstance(FileNotFoundError):
        name = str(getattr(call.excinfo.value, "filename", "") or "")
        if any(f"/{rel}" in name for rel in BORROWED) or "/.venv-agnn/" in name or "model.ckpt" in name:
            report.outcome = "skipped"
            report.longrepr = (str(item.path), item.location[1], f"Skipped: ignored fixture missing everywhere: {name}")
