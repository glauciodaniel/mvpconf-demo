"""Client research: cache → static client file → optional web."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from app.config import CACHE_DIR, CLIENTS_DIR, ensure_dirs, slugify

log = logging.getLogger("mvpconf.research")


def cache_path(company: str) -> Path:
    return CACHE_DIR / f"{slugify(company)}.json"


def client_path(company: str) -> Path:
    return CLIENTS_DIR / f"{slugify(company)}.json"


def load_cache(company: str) -> dict[str, Any] | None:
    ensure_dirs()
    p = cache_path(company)
    if p.exists():
        log.info("Usando cache pré-aquecido: %s", p)
        return json.loads(p.read_text(encoding="utf-8"))
    return None


def load_client_file(company: str) -> dict[str, Any] | None:
    ensure_dirs()
    p = client_path(company)
    if p.exists():
        log.info("Usando data/clients (sem cache/web): %s", p)
        return json.loads(p.read_text(encoding="utf-8"))
    # try generic
    generic = CLIENTS_DIR / "default.json"
    if generic.exists():
        log.info("Usando cliente default: %s", generic)
        data = json.loads(generic.read_text(encoding="utf-8"))
        data = {**data, "company": company}
        return data
    return None


def save_cache(company: str, data: dict[str, Any]) -> Path:
    ensure_dirs()
    p = cache_path(company)
    payload = {"company": company, **data}
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return p


async def web_enrich(company: str, timeout: float = 8.0) -> dict[str, Any] | None:
    """Best-effort web enrichment; returns None on failure."""
    try:
        from duckduckgo_search import DDGS  # type: ignore
    except ImportError:
        log.warning("duckduckgo-search não instalado — pulando web.")
        return None

    import asyncio

    def _search() -> dict[str, Any]:
        with DDGS() as ddgs:
            results = list(ddgs.text(f"{company} empresa IA tecnologia", max_results=5))
            news = list(ddgs.news(company, max_results=5))
        return {
            "web_results": results,
            "news": news,
        }

    try:
        return await asyncio.wait_for(asyncio.to_thread(_search), timeout=timeout)
    except Exception as exc:  # noqa: BLE001
        log.warning("Busca web falhou/timeout: %s", exc)
        return None


async def gather_research_base(company: str) -> tuple[dict[str, Any], list[str]]:
    """Return research base + log notes for the UI."""
    notes: list[str] = []
    base: dict[str, Any] = {"company": company}

    cached = load_cache(company)
    if cached:
        base.update(cached)
        notes.append(f"cache hit: {cache_path(company).name}")
    else:
        client = load_client_file(company)
        if client:
            base.update(client)
            notes.append("usando data/clients (sem cache)")
        else:
            base.update(_synthetic_client(company))
            notes.append("sem cache/web/arquivo — base sintética")

    web = await web_enrich(company)
    if web:
        base["web"] = web
        notes.append("web complementou a base")
    else:
        notes.append("web indisponível — seguindo só com cache/arquivo")

    return base, notes


def _synthetic_client(company: str) -> dict[str, Any]:
    return {
        "company": company,
        "sector": "Tecnologia / Serviços",
        "summary": (
            f"{company} busca capacitar times em orquestração de agentes de IA "
            "com padrões do Microsoft Agent Framework."
        ),
        "ai_maturity": "exploratória",
        "news_hints": ["interesse crescente em IA generativa", "foco em produtividade"],
        "tech_signals": ["nuvem", "automação", "dados"],
    }


async def warmup_company(company: str) -> Path:
    """Pre-warm research cache for stage day."""
    base, notes = await gather_research_base(company)
    base["warmup_notes"] = notes
    # Prefer saving a cleaned snapshot
    snapshot = {
        "company": company,
        "sector": base.get("sector"),
        "summary": base.get("summary"),
        "ai_maturity": base.get("ai_maturity"),
        "news_hints": base.get("news_hints") or base.get("news") or [],
        "tech_signals": base.get("tech_signals", []),
        "web": base.get("web"),
        "warmup_notes": notes,
    }
    path = save_cache(company, snapshot)
    log.info("Warmup salvo em %s — %s", path, "; ".join(notes))
    return path
