#!/usr/bin/env python3
"""Entry point: python run.py [--mock] [--warmup "Empresa"] [--port 8765] [--no-browser]."""

from __future__ import annotations

import argparse
import asyncio
import sys
import threading
import time
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> None:
    parser = argparse.ArgumentParser(description="Demo de palco MVP Conf — orquestração de agentes")
    parser.add_argument("--mock", action="store_true", help="Força modo mock (sem Azure)")
    parser.add_argument("--warmup", type=str, default=None, help='Pré-aquece pesquisa: --warmup "Empresa"')
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--host", type=str, default="127.0.0.1")
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--measure", action="store_true", help="Roda 3x mock e imprime tempos")
    args = parser.parse_args()

    if args.warmup:
        from app.services.research import warmup_company

        path = asyncio.run(warmup_company(args.warmup))
        print(f"Warmup salvo em: {path}")
        return

    if args.measure:
        from scripts.measure_runs import measure

        measure(mock=True, rounds=3)
        return

    import uvicorn

    from app.config import ensure_dirs
    from app.main import APP_STATE
    from app.services.images import ensure_fallback_svgs

    ensure_dirs()
    ensure_fallback_svgs()
    APP_STATE["force_mock"] = bool(args.mock)

    url = f"http://{args.host}:{args.port}/"
    if not args.no_browser:
        threading.Thread(target=_open_browser, args=(url,), daemon=True).start()

    mode = "MOCK" if args.mock else "REAL (fallback local se sem Azure)"
    print(f"\n=== MVP Conf Demo [{mode}] ===")
    print(f"Abra: {url}")
    print("Atalhos: Espaço (mic), R (replay), Shift+R (golden), Enter no texto para iniciar\n")

    uvicorn.run(
        "app.main:app",
        host=args.host,
        port=args.port,
        reload=False,
        log_level="info",
    )


def _open_browser(url: str) -> None:
    time.sleep(0.8)
    try:
        webbrowser.open(url)
    except Exception:
        pass


if __name__ == "__main__":
    main()
