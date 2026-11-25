#!/usr/bin/env python3
"""Measure mock/real pipeline duration three times."""

from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


async def _one(mock: bool, company: str) -> dict:
    from app.pipeline import run_pipeline

    events = []

    async def emit(e):
        events.append(e)

    t0 = time.perf_counter()
    recorder = await run_pipeline(
        f"Preciso de uma proposta de treinamento de agentes de IA para a empresa {company}",
        emit,
        mock=mock,
        company_hint=company,
    )
    elapsed = time.perf_counter() - t0
    return {
        "elapsed": round(elapsed, 2),
        "stage_times": dict(recorder.stage_times),
        "run_id": recorder.run_id,
        "mock": recorder.mock,
    }


def measure(mock: bool = True, rounds: int = 3, *, fast: bool = True) -> None:
    import os

    if fast:
        os.environ["MOCK_FAST"] = "1"
    results = []
    for i in range(rounds):
        print(f"\n--- Round {i+1}/{rounds} ({'mock' if mock else 'real'}{', fast' if fast and mock else ''}) ---")
        r = asyncio.run(_one(mock, f"Contoso{i+1}"))
        results.append(r)
        print(f"Total: {r['elapsed']}s")
        for stage, sec in r["stage_times"].items():
            print(f"  {stage}: {sec}s")

    print("\n=== Resumo ===")
    times = [r["elapsed"] for r in results]
    print(f"Tempos: {times}")
    print(f"Máximo: {max(times):.2f}s | Meta: <= 180s")
    if max(times) > 180:
        print("FALHOU critério de 3 minutos")
        sys.exit(1)
    print("OK — todas as execuções < 3 minutos")


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser()
    p.add_argument("--real", action="store_true")
    p.add_argument("--rounds", type=int, default=3)
    p.add_argument("--stage-pace", action="store_true", help="Usa pacing de palco (~90s), não MOCK_FAST")
    args = p.parse_args()
    measure(mock=not args.real, rounds=args.rounds, fast=not args.stage_pace)
