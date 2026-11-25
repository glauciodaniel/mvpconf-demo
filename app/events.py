"""WebSocket event schema and run recorder."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable

from app.config import RUNS_DIR, ensure_dirs

EmitFn = Callable[[dict[str, Any]], Awaitable[None]]


@dataclass
class RunRecorder:
    """Records all events with relative timestamps for replay."""

    run_id: str
    mock: bool = False
    events: list[dict[str, Any]] = field(default_factory=list)
    started_at: float = field(default_factory=time.perf_counter)
    stage_times: dict[str, float] = field(default_factory=dict)
    images: list[str] = field(default_factory=list)
    proposal_md: str = ""
    company: str = ""
    request: str = ""
    _stage_start: dict[str, float] = field(default_factory=dict)

    def relative_ms(self) -> int:
        return int((time.perf_counter() - self.started_at) * 1000)

    def record(self, event: dict[str, Any]) -> dict[str, Any]:
        payload = dict(event)
        payload.setdefault("t_ms", self.relative_ms())
        self.events.append(payload)

        et = payload.get("type")
        if et == "stage_started":
            stage = payload.get("stage")
            if stage:
                self._stage_start[stage] = time.perf_counter()
        elif et == "stage_finished":
            stage = payload.get("stage")
            if stage and stage in self._stage_start:
                self.stage_times[stage] = round(
                    time.perf_counter() - self._stage_start[stage], 3
                )
        elif et == "image_ready":
            path = payload.get("path") or payload.get("url")
            if path:
                self.images.append(path)
        elif et == "run_finished":
            self.proposal_md = payload.get("proposal_md") or self.proposal_md
            if payload.get("stage_times"):
                self.stage_times.update(payload["stage_times"])
        return payload

    def save(self, mark_golden: bool = False) -> Path:
        ensure_dirs()
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        path = RUNS_DIR / f"{stamp}_{self.run_id}.json"
        data = {
            "run_id": self.run_id,
            "mock": self.mock,
            "company": self.company,
            "request": self.request,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "duration_ms": self.relative_ms(),
            "stage_times": self.stage_times,
            "images": self.images,
            "proposal_md": self.proposal_md,
            "events": self.events,
        }
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        latest = RUNS_DIR / "latest.json"
        latest.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        if mark_golden:
            golden = RUNS_DIR / "golden.json"
            golden.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return path


def load_run(path: Path | str | None = None) -> dict[str, Any]:
    ensure_dirs()
    if path is None:
        candidates = [RUNS_DIR / "golden.json", RUNS_DIR / "latest.json"]
        for c in candidates:
            if c.exists():
                path = c
                break
        else:
            runs = sorted(RUNS_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
            runs = [r for r in runs if r.name not in ("latest.json", "golden.json")]
            if not runs:
                raise FileNotFoundError("Nenhum run gravado em runs/")
            path = runs[0]
    p = Path(path)
    if not p.is_absolute():
        p = RUNS_DIR / p
    return json.loads(p.read_text(encoding="utf-8"))


# Stage metadata for UI
STAGES = [
    {
        "id": "handoff",
        "pattern": "Handoff",
        "talk_name": "Roteamento",
        "agents": ["triagem", "esp_treinamento", "esp_automacao"],
    },
    {
        "id": "research",
        "pattern": "Concorrente",
        "talk_name": "Swarm",
        "agents": ["pesq_empresa", "pesq_noticias", "pesq_maturidade"],
    },
    {
        "id": "magentic",
        "pattern": "Magentic",
        "talk_name": "Hierárquico",
        "agents": ["gerente", "analista", "sintetizador"],
    },
    {
        "id": "group_chat",
        "pattern": "Group Chat",
        "talk_name": "Time",
        "agents": ["redator", "revisor"],
    },
    {
        "id": "images",
        "pattern": "Concorrente",
        "talk_name": "Swarm",
        "agents": ["img_capa", "img_solucao", "img_resultado"],
    },
]

AGENT_LABELS = {
    "triagem": "Triagem",
    "esp_treinamento": "Esp. Treinamento",
    "esp_automacao": "Esp. Automação",
    "pesq_empresa": "Empresa & Setor",
    "pesq_noticias": "Notícias",
    "pesq_maturidade": "Maturidade IA",
    "gerente": "Gerente",
    "analista": "Analista",
    "sintetizador": "Sintetizador",
    "redator": "Redator",
    "revisor": "Revisor",
    "img_capa": "Capa",
    "img_solucao": "Solução",
    "img_resultado": "Resultado",
}
