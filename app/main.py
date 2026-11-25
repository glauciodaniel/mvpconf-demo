"""FastAPI + WebSocket server for the MVP Conf stage demo."""

from __future__ import annotations

import asyncio
import json
import logging
import shutil
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.config import (
    ASSETS_DIR,
    BRAND_DIR,
    FALLBACK_DIR,
    ROOT,
    RUNS_DIR,
    STATIC_DIR,
    ensure_dirs,
    get_config,
)
from app.events import STAGES, load_run
from app.pipeline import run_pipeline
from app.replay import replay_run
from app.services.images import ensure_fallback_svgs

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
log = logging.getLogger("mvpconf")

app = FastAPI(title="MVP Conf · Demo Multiagente", version="0.1.0")

# Global flags set by run.py
APP_STATE: dict[str, Any] = {
    "force_mock": False,
    "active_task": None,
}


class Hub:
    def __init__(self) -> None:
        self.clients: set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            self.clients.add(ws)

    async def disconnect(self, ws: WebSocket) -> None:
        async with self._lock:
            self.clients.discard(ws)

    async def broadcast(self, event: dict[str, Any]) -> None:
        dead: list[WebSocket] = []
        async with self._lock:
            targets = list(self.clients)
        for ws in targets:
            try:
                await ws.send_json(event)
            except Exception:  # noqa: BLE001
                dead.append(ws)
        for ws in dead:
            await self.disconnect(ws)


hub = Hub()


@app.on_event("startup")
async def startup() -> None:
    ensure_dirs()
    ensure_fallback_svgs()
    _ensure_brand_placeholders()
    log.info("Demo pronta. force_mock=%s", APP_STATE.get("force_mock"))


def _ensure_brand_placeholders() -> None:
    BRAND_DIR.mkdir(parents=True, exist_ok=True)
    readme = BRAND_DIR / "README.md"
    readme.write_text(
        """# Brand assets — Hcode Training

| Arquivo | Uso |
|---------|-----|
| `hcode-training-color.png` | Tela final da proposta (fundo branco) |
| `hcode-training-white.png` | Tema navy da MVP Conf (palco) |

Origem: `media/brand/` do Project store.
""",
        encoding="utf-8",
    )
    # Keep a tiny SVG fallback only if PNGs are missing
    color = BRAND_DIR / "hcode-training-color.png"
    mark = BRAND_DIR / "hcode-training-placeholder.svg"
    if not color.exists() and not mark.exists():
        mark.write_text(
            """<svg xmlns="http://www.w3.org/2000/svg" width="480" height="96" viewBox="0 0 480 96">
  <rect width="480" height="96" fill="#FFFFFF"/>
  <text x="0" y="62" font-family="Inter,Arial,sans-serif" font-size="42" font-weight="700" fill="#101010">hcode</text>
  <text x="168" y="62" font-family="Inter,Arial,sans-serif" font-size="42" font-weight="500" fill="#FF760C">training</text>
</svg>
""",
            encoding="utf-8",
        )


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/health")
async def health() -> dict[str, Any]:
    return {
        "ok": True,
        "force_mock": bool(APP_STATE.get("force_mock")),
        "stages": STAGES,
    }


@app.get("/api/config")
async def api_config() -> dict[str, Any]:
    cfg = get_config()
    return {
        "budgets_seconds": cfg.get("budgets_seconds"),
        "mock": cfg.get("mock"),
        "stages": STAGES,
        "force_mock": bool(APP_STATE.get("force_mock")),
    }


@app.get("/api/runs")
async def list_runs() -> list[dict[str, Any]]:
    ensure_dirs()
    items = []
    for p in sorted(RUNS_DIR.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True):
        if p.name.startswith("media_"):
            continue
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            items.append(
                {
                    "file": p.name,
                    "run_id": data.get("run_id"),
                    "company": data.get("company"),
                    "mock": data.get("mock"),
                    "duration_ms": data.get("duration_ms"),
                    "created_at": data.get("created_at"),
                }
            )
        except Exception:  # noqa: BLE001
            continue
    return items


@app.post("/api/mark-golden")
async def mark_golden(body: dict[str, Any] | None = None) -> dict[str, Any]:
    ensure_dirs()
    src_name = (body or {}).get("file")
    if src_name:
        src = RUNS_DIR / src_name
    else:
        src = RUNS_DIR / "latest.json"
    if not src.exists():
        return JSONResponse({"ok": False, "error": "run não encontrado"}, status_code=404)
    shutil.copy2(src, RUNS_DIR / "golden.json")
    return {"ok": True, "golden": "golden.json", "from": src.name}


@app.post("/api/warmup-ping")
async def warmup_ping() -> dict[str, Any]:
    from app.services.warmup_ping import ping_deployments

    return await ping_deployments()


@app.post("/api/transcribe")
async def transcribe(file: UploadFile = File(...)) -> dict[str, Any]:
    from app.services.voice import transcribe_audio

    data = await file.read()
    try:
        text = await transcribe_audio(data, file.filename or "audio.webm")
        return {"ok": True, "text": text}
    except Exception as exc:  # noqa: BLE001
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=501)


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket) -> None:
    await hub.connect(ws)
    try:
        await ws.send_json({"type": "hello", "force_mock": APP_STATE.get("force_mock")})
        while True:
            raw = await ws.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                await ws.send_json({"type": "error", "message": "JSON inválido"})
                continue
            await _handle_client_message(ws, msg)
    except WebSocketDisconnect:
        await hub.disconnect(ws)
    except Exception as exc:  # noqa: BLE001
        log.exception("WS error: %s", exc)
        await hub.disconnect(ws)


async def _handle_client_message(ws: WebSocket, msg: dict[str, Any]) -> None:
    action = msg.get("action") or msg.get("type")
    if action == "start":
        if APP_STATE.get("active_task") and not APP_STATE["active_task"].done():
            await ws.send_json({"type": "error", "message": "Já existe uma execução em andamento"})
            return
        request = (msg.get("request") or msg.get("text") or "").strip()
        if not request:
            request = "Preciso de uma proposta de treinamento de agentes de IA para a empresa Contoso"
        mock = bool(msg.get("mock", APP_STATE.get("force_mock")))
        company = msg.get("company")
        task = asyncio.create_task(_run_and_broadcast(request, mock=mock, company_hint=company))
        APP_STATE["active_task"] = task
    elif action == "replay":
        if APP_STATE.get("active_task") and not APP_STATE["active_task"].done():
            await ws.send_json({"type": "error", "message": "Aguarde a execução atual"})
            return
        path = msg.get("file")
        speed = float(msg.get("speed") or 1.0)
        task = asyncio.create_task(_replay_and_broadcast(path, speed=speed))
        APP_STATE["active_task"] = task
    elif action == "mark_golden":
        latest = RUNS_DIR / "latest.json"
        if latest.exists():
            shutil.copy2(latest, RUNS_DIR / "golden.json")
            await hub.broadcast({"type": "info", "message": "Replay oficial gravado (golden.json)"})
        else:
            await ws.send_json({"type": "error", "message": "Nenhum latest.json"})
    elif action == "warmup_ping":
        from app.services.warmup_ping import ping_deployments

        result = await ping_deployments()
        await ws.send_json({"type": "warmup_result", "result": result})
    elif action == "stop":
        task = APP_STATE.get("active_task")
        if task and not task.done():
            task.cancel()
            await hub.broadcast({"type": "info", "message": "Execução cancelada"})
    else:
        await ws.send_json({"type": "error", "message": f"Ação desconhecida: {action}"})


async def _run_and_broadcast(
    request: str, *, mock: bool, company_hint: str | None
) -> None:
    async def emit(event: dict[str, Any]) -> None:
        await hub.broadcast(event)

    try:
        await run_pipeline(request, emit, mock=mock, company_hint=company_hint)
    except asyncio.CancelledError:
        await hub.broadcast({"type": "run_cancelled"})
    except Exception as exc:  # noqa: BLE001
        log.exception("Pipeline falhou")
        await hub.broadcast({"type": "error", "message": str(exc)})


async def _replay_and_broadcast(path: str | None, speed: float) -> None:
    async def emit(event: dict[str, Any]) -> None:
        await hub.broadcast(event)

    try:
        await replay_run(emit, path, speed=speed)
    except Exception as exc:  # noqa: BLE001
        log.exception("Replay falhou")
        await hub.broadcast({"type": "error", "message": str(exc)})


# Static mounts
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
app.mount("/assets", StaticFiles(directory=str(ASSETS_DIR)), name="assets")
app.mount("/runs", StaticFiles(directory=str(RUNS_DIR)), name="runs")
