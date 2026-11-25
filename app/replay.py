"""Replay a recorded run with original relative timings (offline)."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

from app.events import EmitFn, load_run

log = logging.getLogger("mvpconf.replay")


async def replay_run(
    emit: EmitFn,
    path: str | Path | None = None,
    *,
    speed: float = 1.0,
) -> dict[str, Any]:
    data = load_run(path)
    events = data.get("events") or []
    if not events:
        raise ValueError("Run sem eventos")

    # Mark as replay for the UI
    await emit(
        {
            "type": "replay_started",
            "run_id": data.get("run_id"),
            "source": str(path) if path else "latest/golden",
            "mock": data.get("mock"),
            "company": data.get("company"),
        }
    )

    speed = max(0.25, min(speed, 4.0))
    prev_t = 0
    for event in events:
        t_ms = int(event.get("t_ms", prev_t))
        delay = max(0.0, (t_ms - prev_t) / 1000.0 / speed)
        if delay:
            await asyncio.sleep(delay)
        prev_t = t_ms
        payload = dict(event)
        payload["replay"] = True
        await emit(payload)

    await emit(
        {
            "type": "replay_finished",
            "run_id": data.get("run_id"),
            "duration_ms": data.get("duration_ms"),
        }
    )
    return data
