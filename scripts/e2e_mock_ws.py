#!/usr/bin/env python3
"""End-to-end mock via WebSocket: start → run_finished under 3 minutes."""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("MOCK_FAST", "1")


async def main(port: int = 8765) -> None:
    import websockets

    url = f"ws://127.0.0.1:{port}/ws"
    t0 = time.perf_counter()
    types: list[str] = []
    finished = None
    async with websockets.connect(url) as ws:
        hello = json.loads(await ws.recv())
        assert hello.get("type") == "hello", hello
        await ws.send(
            json.dumps(
                {
                    "action": "start",
                    "mock": True,
                    "request": "Preciso de uma proposta de treinamento de agentes de IA para a empresa Contoso",
                }
            )
        )
        while True:
            raw = await asyncio.wait_for(ws.recv(), timeout=180)
            ev = json.loads(raw)
            types.append(ev.get("type"))
            if ev.get("type") == "run_finished":
                finished = ev
                break
            if ev.get("type") == "error":
                raise RuntimeError(ev)

    elapsed = time.perf_counter() - t0
    required = {
        "run_started",
        "stage_started",
        "agent_started",
        "agent_delta",
        "agent_message",
        "stage_finished",
        "image_ready",
        "run_finished",
    }
    missing = required - set(types)
    print(f"elapsed={elapsed:.2f}s events={len(types)} missing={missing or 'none'}")
    print(f"company={finished.get('company')} total={finished.get('total_seconds')}")
    print(f"images={finished.get('images')}")
    print(f"proposal_chars={len(finished.get('proposal_md') or '')}")
    if missing:
        sys.exit(2)
    if elapsed > 180:
        sys.exit(1)
    # quick replay check against latest.json
    from app.replay import replay_run

    evs = []

    async def emit(e):
        evs.append(e.get("type"))

    await replay_run(emit, ROOT / "runs" / "latest.json", speed=8.0)
    assert "run_finished" in evs or "replay_finished" in evs
    print(f"replay_ok events={len(evs)}")
    print("E2E MOCK OK")


if __name__ == "__main__":
    asyncio.run(main(int(sys.argv[1]) if len(sys.argv) > 1 else 8765))
