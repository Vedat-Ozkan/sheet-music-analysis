import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from mcp.client.client import Client

from server import app

ROOT = Path(__file__).resolve().parents[1]
CHOPIN = ROOT / "tests/data/chopin_nocturne_op9_no2.mxl"
CONTRADICTION = "m1 b1 vi (in Eb): its bass, C, is never the lowest note while it lasts"


def analysis(label: str) -> dict:
    return {"annotations": [{"type": "harmony", "at": {"measure": 1, "beat": 1}, "key": "Eb", "label": label},
                            {"type": "harmony", "at": {"measure": 1, "beat": 4}, "label": "I"}]}


@pytest.fixture
def chopin(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "store", app.LocalStore(tmp_path))
    monkeypatch.setattr(app, "day_keys", {})
    monkeypatch.setattr(app, "publish", lambda data, *kind: "https://example.com/file")
    app.store.put("scores/ABC", CHOPIN.read_bytes())


def reply(label: str) -> str:
    async def call():
        async with Client(app.mcp) as client:
            result = await client.call_tool("render_analysis", {"score_id": "ABC", "measure_range": "1-1", "annotations": analysis(label)})
        return next(item.text for item in result.content if item.type == "text")

    return asyncio.run(call())


def test_the_drawn_analysis_reply_names_a_label_that_contradicts_the_notes(chopin):
    assert CONTRADICTION in reply("vi")
    assert "contradict" not in reply("I")


def test_the_skill_render_prints_a_label_that_contradicts_the_notes(tmp_path):
    source = tmp_path / "annotations.json"
    source.write_text(json.dumps(analysis("vi")))
    result = subprocess.run(
        [sys.executable, str(ROOT / "skill/scripts/render_analysis.py"), str(CHOPIN), str(source),
         "--measures", "1-1", "--out-dir", str(tmp_path), "--name", "analysis"],
        capture_output=True, text=True, env={**os.environ, "PYTHONPATH": str(ROOT)},
    )
    assert result.returncode == 0, result.stderr
    assert CONTRADICTION in result.stdout
