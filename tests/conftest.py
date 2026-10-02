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
