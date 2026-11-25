"""Mock multi-agent pipeline — no Azure credentials required."""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

from app.config import get_config
from app.events import AGENT_LABELS, EmitFn, RunRecorder


SAMPLE_PROPOSAL = """# Proposta de Treinamento em Agentes de IA

## Contexto do cliente
A **{company}** atua em um mercado competitivo e busca acelerar a adoção de IA com equipes capazes de orquestrar agentes de forma segura e produtiva.

## Desafio
Traduzir o interesse em IA generativa em capacidade operacional: times que desenhem, orquestrem e governem agentes alinhados ao negócio — sem inventar processos soltos.

## Solução proposta
Programa hands-on da **Hcode Training**, alinhado ao Microsoft Agent Framework, cobrindo os cinco padrões de orquestração (Roteamento, Swarm, Hierárquico, Time e Swarm de imagens) aplicados a um caso real da {company}.

## Programa
| Módulo | Carga |
|--------|-------|
| Fundamentos de Agentes de IA | 4h |
| Orquestração Multiagente | 6h |
| Laboratório Hands-on | 6h |

- **Carga total:** 16 horas
- **Formato:** presencial + online
- **Investimento:** valores a combinar

## Próximos passos
1. Workshop de discovery (90 min) com stakeholders
2. Ajuste do programa ao contexto da {company}
3. Kickoff da turma piloto
"""

MOCK_TEXTS: dict[str, list[str]] = {
    "triagem": [
        "Analisando o pedido… ",
        "Cliente identificado: {company}. ",
        "Tipo de demanda: treinamento de agentes de IA. ",
        "Roteando para Especialista em Treinamento.",
    ],
    "esp_treinamento": [
        "Recebi o handoff da Triagem. ",
        "Demanda confirma linha Treinamento Hcode. ",
        "Vou acionar o swarm de pesquisa sobre {company}.",
    ],
    "pesq_empresa": [
        "{company}: perfil setorial e posicionamento. ",
        "Presença digital relevante; foco em transformação digital. ",
        "Oportunidade clara para capacitação de times de produto e TI.",
    ],
    "pesq_noticias": [
        "Buscando sinais recentes… ",
        "Menções a inovação e produtividade com IA. ",
        "Momento favorável para proposta de treinamento executivo + hands-on.",
    ],
    "pesq_maturidade": [
        "Maturidade em IA: exploratória → operacional. ",
        "Há POCs; falta padronizar orquestração e governança. ",
        "Gap principal: multiagente em produção com padrões claros.",
    ],
    "gerente": [
        "Objetivo: dossiê de uma página sobre {company}. ",
        "Analista: sintetize setor e maturidade. ",
        "Sintetizador: una notícias ao desafio de capacitação.",
    ],
    "analista": [
        "Setor com pressão por eficiência. ",
        "Times precisam de padrões (handoff, concurrent, Magentic). ",
        "Recomendo foco em Agent Framework + laboratório com caso da {company}.",
    ],
    "sintetizador": [
        "Dossiê: {company} pronta para upskilling. ",
        "Desafio = passar de POCs isoladas a orquestração confiável. ",
        "Proposta deve destacar os cinco padrões em uma única demo viva.",
    ],
    "redator": [
        "Escrevendo proposta comercial…\n\n",
        "## Contexto\nCliente {company}, demanda de treinamento em agentes.\n\n",
        "## Solução\nPrograma Hcode Training com Agent Framework.\n\n",
        "## Programa\nFundamentos (4h), Orquestração (6h), Lab (6h).\n\n",
        "Investimento: valores a combinar. Próximos passos: discovery → kickoff.",
    ],
    "revisor": [
        "Revisão: tom comercial ok, sem preços inventados. ",
        "Sugestão: reforçar alinhamento MVP Conf / Microsoft. ",
        "Aprovado para geração de imagens e entrega final.",
    ],
    "img_capa": ["Gerando capa da proposta… ", "Composição navy → laranja Hcode."],
    "img_solucao": ["Ilustrando a solução multiagente… ", "Cinco padrões em um pipeline."],
    "img_resultado": ["Ilustrando o resultado… ", "Time capacitado e proposta pronta."],
}


async def _emit(emit: EmitFn, recorder: RunRecorder, event: dict[str, Any]) -> None:
    payload = recorder.record(event)
    await emit(payload)


async def _stream_agent(
    emit: EmitFn,
    recorder: RunRecorder,
    agent_id: str,
    chunks: list[str],
    company: str,
    char_delay: float = 0.012,
) -> str:
    label = AGENT_LABELS.get(agent_id, agent_id)
    await _emit(
        emit,
        recorder,
        {"type": "agent_started", "agent": agent_id, "label": label},
    )
    full = ""
    for chunk in chunks:
        text = chunk.format(company=company)
        full += text
        # stream in small pieces for visual effect
        step = max(1, len(text) // 4) if len(text) > 20 else len(text) or 1
        for i in range(0, len(text), step):
            piece = text[i : i + step]
            await _emit(
                emit,
                recorder,
                {"type": "agent_delta", "agent": agent_id, "delta": piece},
            )
            await asyncio.sleep(char_delay)
    await _emit(
        emit,
        recorder,
        {"type": "agent_finished", "agent": agent_id, "text": full},
    )
    return full


async def _message(
    emit: EmitFn, recorder: RunRecorder, src: str, dst: str, text: str
) -> None:
    await _emit(
        emit,
        recorder,
        {
            "type": "agent_message",
            "from": src,
            "to": dst,
            "text": text,
            "from_label": AGENT_LABELS.get(src, src),
            "to_label": AGENT_LABELS.get(dst, dst),
        },
    )
    await asyncio.sleep(0.25)


async def run_mock_pipeline(
    request: str,
    emit: EmitFn,
    company_hint: str | None = None,
    *,
    fast: bool | None = None,
) -> RunRecorder:
    import os

    cfg = get_config()
    mock_cfg = cfg.get("mock", {})
    stage_secs = mock_cfg.get("stage_seconds", {})
    if fast is None:
        fast = os.getenv("MOCK_FAST", "").lower() in ("1", "true", "yes")
    # Pace toward configured stage budgets on stage; compress when MOCK_FAST=1
    pace_factor = 0.15 if fast else 0.85
    char_delay = 0.004 if fast else 0.028
    run_id = uuid.uuid4().hex[:10]
    recorder = RunRecorder(run_id=run_id, mock=True)
    recorder.request = request

    company = company_hint or _extract_company(request)
    recorder.company = company

    await _emit(
        emit,
        recorder,
        {
            "type": "run_started",
            "run_id": run_id,
            "mock": True,
            "request": request,
            "company": company,
            "budgets": cfg.get("budgets_seconds", {}),
        },
    )
    await _emit(emit, recorder, {"type": "transcript", "text": request, "final": True})

    # --- 1 HANDOFF ---
    t0 = asyncio.get_event_loop().time()
    budget = stage_secs.get("handoff", 8)
    await _stage_start(emit, recorder, "handoff", budget)
    await _stream_agent(emit, recorder, "triagem", MOCK_TEXTS["triagem"], company, char_delay)
    await _message(emit, recorder, "triagem", "esp_treinamento", "handoff: treinamento")
    await _stream_agent(
        emit, recorder, "esp_treinamento", MOCK_TEXTS["esp_treinamento"], company, char_delay
    )
    # show automacao briefly as non-selected route
    await _emit(
        emit,
        recorder,
        {
            "type": "agent_started",
            "agent": "esp_automacao",
            "label": AGENT_LABELS["esp_automacao"],
            "dimmed": True,
        },
    )
    await asyncio.sleep(0.3)
    await _emit(
        emit,
        recorder,
        {
            "type": "agent_finished",
            "agent": "esp_automacao",
            "text": "(rota não selecionada)",
            "dimmed": True,
        },
    )
    await _pace(t0, budget, pace_factor)
    await _stage_finish(emit, recorder, "handoff")

    # --- 2 RESEARCH CONCURRENT ---
    t0 = asyncio.get_event_loop().time()
    budget = stage_secs.get("research", 20)
    await _stage_start(emit, recorder, "research", budget)
    await asyncio.gather(
        _stream_agent(emit, recorder, "pesq_empresa", MOCK_TEXTS["pesq_empresa"], company, char_delay),
        _stream_agent(emit, recorder, "pesq_noticias", MOCK_TEXTS["pesq_noticias"], company, char_delay),
        _stream_agent(
            emit, recorder, "pesq_maturidade", MOCK_TEXTS["pesq_maturidade"], company, char_delay
        ),
    )
    await _pace(t0, budget, pace_factor)
    await _stage_finish(emit, recorder, "research")

    # --- 3 MAGENTIC ---
    t0 = asyncio.get_event_loop().time()
    budget = stage_secs.get("magentic", 22)
    await _stage_start(emit, recorder, "magentic", budget)
    await _stream_agent(emit, recorder, "gerente", MOCK_TEXTS["gerente"], company, char_delay)
    await _message(emit, recorder, "gerente", "analista", "elabore análise setorial")
    await _stream_agent(emit, recorder, "analista", MOCK_TEXTS["analista"], company, char_delay)
    await _message(emit, recorder, "gerente", "sintetizador", "produza o dossiê")
    await _stream_agent(emit, recorder, "sintetizador", MOCK_TEXTS["sintetizador"], company, char_delay)
    await _message(emit, recorder, "sintetizador", "gerente", "dossiê pronto")
    await _pace(t0, budget, pace_factor)
    await _stage_finish(emit, recorder, "magentic")

    # --- 4 GROUP CHAT ---
    t0 = asyncio.get_event_loop().time()
    budget = stage_secs.get("group_chat", 20)
    await _stage_start(emit, recorder, "group_chat", budget)
    await _stream_agent(emit, recorder, "redator", MOCK_TEXTS["redator"], company, char_delay * 0.7)
    await _message(emit, recorder, "redator", "revisor", "rascunho da proposta")
    await _stream_agent(emit, recorder, "revisor", MOCK_TEXTS["revisor"], company, char_delay)
    await _message(emit, recorder, "revisor", "redator", "aprovado com ajustes menores")
    await _pace(t0, budget, pace_factor)
    await _stage_finish(emit, recorder, "group_chat")

    # --- 5 IMAGES ---
    t0 = asyncio.get_event_loop().time()
    budget = stage_secs.get("images", 12)
    await _stage_start(emit, recorder, "images", budget)

    async def _img(agent_id: str, kind: str) -> None:
        await _stream_agent(emit, recorder, agent_id, MOCK_TEXTS[agent_id], company, char_delay)
        path = f"/assets/fallback/{kind}.svg"
        await _emit(
            emit,
            recorder,
            {
                "type": "image_ready",
                "agent": agent_id,
                "kind": kind,
                "path": path,
                "url": path,
                "fallback": True,
            },
        )

    await asyncio.gather(
        _img("img_capa", "capa"),
        _img("img_solucao", "solucao"),
        _img("img_resultado", "resultado"),
    )
    await _pace(t0, budget, pace_factor)
    await _stage_finish(emit, recorder, "images")

    proposal = SAMPLE_PROPOSAL.format(company=company)
    recorder.proposal_md = proposal
    total = round(recorder.relative_ms() / 1000, 2)
    await _emit(
        emit,
        recorder,
        {
            "type": "run_finished",
            "run_id": run_id,
            "proposal_md": proposal,
            "stage_times": dict(recorder.stage_times),
            "total_seconds": total,
            "images": list(recorder.images),
            "company": company,
        },
    )
    recorder.save()
    return recorder


async def _pace(started: float, budget: float, factor: float) -> None:
    """Sleep so the stage roughly fills budget * factor (stage-friendly pacing)."""
    elapsed = asyncio.get_event_loop().time() - started
    remaining = budget * factor - elapsed
    if remaining > 0.05:
        await asyncio.sleep(remaining)


async def _stage_start(
    emit: EmitFn, recorder: RunRecorder, stage: str, budget: float
) -> None:
    meta = {
        "handoff": ("Handoff", "Roteamento"),
        "research": ("Concorrente", "Swarm"),
        "magentic": ("Magentic", "Hierárquico"),
        "group_chat": ("Group Chat", "Time"),
        "images": ("Concorrente", "Swarm"),
    }
    pattern, talk = meta[stage]
    await _emit(
        emit,
        recorder,
        {
            "type": "stage_started",
            "stage": stage,
            "pattern": pattern,
            "talk_name": talk,
            "budget_seconds": budget,
        },
    )


async def _stage_finish(emit: EmitFn, recorder: RunRecorder, stage: str) -> None:
    await _emit(emit, recorder, {"type": "stage_finished", "stage": stage})


def _extract_company(request: str) -> str:
    import re

    # "para a empresa X" / "para a X" / "cliente X"
    patterns = [
        r"empresa\s+([A-Za-zÀ-ÿ0-9][\wÀ-ÿ0-9&\.\- ]{1,40})",
        r"cliente\s+([A-Za-zÀ-ÿ0-9][\wÀ-ÿ0-9&\.\- ]{1,40})",
        r"para\s+(?:a|o|na|no)\s+([A-Za-zÀ-ÿ0-9][\wÀ-ÿ0-9&\.\- ]{1,40})",
    ]
    for p in patterns:
        m = re.search(p, request, re.IGNORECASE)
        if m:
            name = m.group(1).strip(" .,!?;:")
            # cut trailing filler
            for stop in (" preciso", " com", " de", " para"):
                if stop in name.lower():
                    name = name[: name.lower().index(stop)]
            return name.strip() or "Empresa X"
    return "Empresa X"
