import threading
import time
from pathlib import Path

import anyio
from mcp.client.client import Client

from server import app

SCORE = Path(__file__).parent / "data/chopin_nocturne_op9_no2.mxl"


def test_two_requests_take_turns_with_the_score_work(monkeypatch, tmp_path):
    monkeypatch.setattr(app, "store", app.LocalStore(tmp_path))
    app.store.put("scores/CHOPIN", SCORE.read_bytes())
    running, most = [0], [0]
    lock = threading.Lock()
    performance_text = app.performance_text

    def watched(*args, **kwargs):
        with lock:
            running[0] += 1
            most[0] = max(most[0], running[0])
        time.sleep(0.3)
        with lock:
            running[0] -= 1
        return performance_text(*args, **kwargs)

    monkeypatch.setattr(app, "performance_text", watched)

    async def both():
        async with Client(app.mcp) as first, Client(app.mcp) as second:
            async with anyio.create_task_group() as group:
                for client in (first, second):
                    group.start_soon(client.call_tool, "play", {"score_id": "CHOPIN", "measure_range": "1-2"})

    anyio.run(both)
    assert most[0] == 1
