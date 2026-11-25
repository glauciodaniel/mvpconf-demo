"""Real multi-agent pipeline with timeouts and fallbacks."""

from __future__ import annotations

import asyncio
import logging
import uuid
from pathlib import Path
from typing import Any

from app.config import RUNS_DIR, get_config
from app.events import AGENT_LABELS, EmitFn, RunRecorder
from app.mock_pipeline import SAMPLE_PROPOSAL, _extract_company
from app.services.images import generate_image
from app.services.research import gather_research_base

log = logging.getLogger("mvpconf.pipeline")

STAGE_META = {
    "handoff": ("Handoff", "Roteamento"),
    "research": ("Concorrente", "Swarm"),
    "magentic": ("Magentic", "Hierárquico"),
    "group_chat": ("Group Chat", "Time"),
    "images": ("Concorrente", "Swarm"),
}


async def run_pipeline(
    request: str,
    emit: EmitFn,
    *,
    mock: bool = False,
    company_hint: str | None = None,
) -> RunRecorder:
    if mock:
        from app.mock_pipeline import run_mock_pipeline

        return await run_mock_pipeline(request, emit, company_hint=company_hint)

    cfg = get_config()
    budgets = cfg.get("budgets_seconds", {})
    run_id = uuid.uuid4().hex[:10]
    recorder = RunRecorder(run_id=run_id, mock=False)
    recorder.request = request
    company = company_hint or _extract_company(request)
    recorder.company = company
    run_dir = RUNS_DIR / f"media_{run_id}"
    run_dir.mkdir(parents=True, exist_ok=True)

    await _emit(
        emit,
        recorder,
        {
            "type": "run_started",
            "run_id": run_id,
            "mock": False,
            "request": request,
            "company": company,
            "budgets": budgets,
        },
    )
    await _emit(emit, recorder, {"type": "transcript", "text": request, "final": True})

    bundle = None
    try:
        from app.agents.factory import create_agents

        bundle = await create_agents()
        agents = bundle.agents
        use_framework = True
    except Exception as exc:  # noqa: BLE001
        log.warning("Framework/Foundry indisponível (%s) — fallback textual local", exc)
        agents = {}
        use_framework = False

    try:
        # 1 HANDOFF
        await _stage_start(emit, recorder, "handoff", budgets.get("handoff", 15))
        await _run_handoff(
            emit, recorder, agents, request, company, budgets.get("handoff", 15), use_framework
        )
        await _stage_finish(emit, recorder, "handoff")

        # 2 RESEARCH
        await _stage_start(emit, recorder, "research", budgets.get("research", 45))
        research, notes = await gather_research_base(company)
        for note in notes:
            await _emit(emit, recorder, {"type": "agent_delta", "agent": "pesq_empresa", "delta": f"[log] {note}\n"})
        await _run_research(
            emit, recorder, agents, company, research, budgets.get("research", 45), use_framework
        )
        await _stage_finish(emit, recorder, "research")

        # 3 MAGENTIC
        await _stage_start(emit, recorder, "magentic", budgets.get("magentic", 50))
        dossier = await _run_magentic(
            emit, recorder, agents, company, research, budgets.get("magentic", 50), use_framework
        )
        await _stage_finish(emit, recorder, "magentic")

        # 4 GROUP CHAT
        await _stage_start(emit, recorder, "group_chat", budgets.get("group_chat", 40))
        proposal = await _run_group_chat(
            emit,
            recorder,
            agents,
            company,
            dossier,
            budgets.get("group_chat", 40),
            use_framework,
        )
        await _stage_finish(emit, recorder, "group_chat")

        # 5 IMAGES
        await _stage_start(emit, recorder, "images", budgets.get("images", 40))
        await _run_images(emit, recorder, company, run_dir, budgets.get("images", 40))
        await _stage_finish(emit, recorder, "images")

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
    finally:
        if bundle:
            await bundle.aclose()


async def _run_handoff(
    emit, recorder, agents, request, company, budget, use_framework
) -> None:
    timeout = max(5.0, budget * 0.6)
    triage_prompt = (
        f"Pedido do usuário: {request}\n"
        f"Extraia cliente e tipo. Cliente suspeito: {company}."
    )
    text = await _safe_agent(
        emit, recorder, agents, "triagem", triage_prompt, timeout, use_framework,
        fallback=(
            f"Cliente: {company}. Demanda: treinamento de agentes de IA. "
            "Handoff → Esp. Treinamento."
        ),
    )
    route = "esp_treinamento"
    if "automa" in text.lower() and "trein" not in text.lower():
        route = "esp_automacao"
    await _message(emit, recorder, "triagem", route, "handoff")
    await _safe_agent(
        emit,
        recorder,
        agents,
        route,
        f"Handoff recebido para {company}. Confirme e avance.",
        timeout,
        use_framework,
        fallback=f"Handoff confirmado. Seguiremos com treinamento para {company}.",
    )
    # show non-selected specialist briefly
    other = "esp_automacao" if route == "esp_treinamento" else "esp_treinamento"
    await _emit(
        emit,
        recorder,
        {"type": "agent_started", "agent": other, "label": AGENT_LABELS[other], "dimmed": True},
    )
    await asyncio.sleep(0.2)
    await _emit(
        emit,
        recorder,
        {"type": "agent_finished", "agent": other, "text": "(rota não selecionada)", "dimmed": True},
    )


async def _run_research(
    emit, recorder, agents, company, research, budget, use_framework
) -> None:
    timeout = max(8.0, budget * 0.7)
    ctx = _research_context(company, research)

    async def one(agent_id: str, focus: str, fallback: str) -> None:
        await _safe_agent(
            emit,
            recorder,
            agents,
            agent_id,
            f"{ctx}\nFoque em: {focus}",
            timeout,
            use_framework,
            fallback=fallback,
        )

    await asyncio.gather(
        one(
            "pesq_empresa",
            "empresa e setor",
            f"{company}: {_get(research,'sector','serviços')}. {_get(research,'summary','')}",
        ),
        one(
            "pesq_noticias",
            "notícias e sinais recentes",
            "Sinais de inovação e interesse em IA. " + str(research.get("news_hints", [])),
        ),
        one(
            "pesq_maturidade",
            "maturidade em tecnologia e IA",
            f"Maturidade: {_get(research,'ai_maturity','exploratória')}. Gap em orquestração multiagente.",
        ),
    )


async def _run_magentic(
    emit, recorder, agents, company, research, budget, use_framework
) -> str:
    cfg = get_config().get("magentic", {})
    max_rounds = int(cfg.get("max_rounds", 3))
    timeout = max(10.0, budget / max(1, max_rounds))
    ctx = _research_context(company, research)

    # Prefer MagenticBuilder when available
    if use_framework and agents:
        try:
            dossier = await asyncio.wait_for(
                _try_magentic_builder(emit, recorder, agents, company, ctx),
                timeout=budget,
            )
            if dossier:
                return dossier
        except Exception as exc:  # noqa: BLE001
            log.warning("MagenticBuilder falhou (%s) — fallback coordenado", exc)

    await _safe_agent(
        emit,
        recorder,
        agents,
        "gerente",
        f"Coordene dossiê sobre {company}. Contexto:\n{ctx}",
        timeout,
        use_framework,
        fallback=f"Objetivo: dossiê de uma página sobre {company}. Analista e Sintetizador, vamos.",
    )
    await _message(emit, recorder, "gerente", "analista", "analise setor e maturidade")
    analise = await _safe_agent(
        emit,
        recorder,
        agents,
        "analista",
        f"Analise {company}:\n{ctx}",
        timeout,
        use_framework,
        fallback=f"{company} em {_get(research,'sector','tecnologia')}, maturidade {_get(research,'ai_maturity','exploratória')}.",
    )
    await _message(emit, recorder, "gerente", "sintetizador", "produza o dossiê")
    dossier = await _safe_agent(
        emit,
        recorder,
        agents,
        "sintetizador",
        f"Produza dossiê de 1 página.\nAnálise:\n{analise}\nContexto:\n{ctx}",
        timeout,
        use_framework,
        fallback=(
            f"# Dossiê {company}\n\nContexto e desafio de capacitação em agentes de IA.\n"
            f"Setor: {_get(research,'sector','—')}. Maturidade: {_get(research,'ai_maturity','—')}.\n"
            "Oportunidade: programa hands-on com Microsoft Agent Framework."
        ),
    )
    await _message(emit, recorder, "sintetizador", "gerente", "dossiê pronto")
    return dossier


async def _try_magentic_builder(emit, recorder, agents, company, ctx) -> str | None:
    from agent_framework.orchestrations import MagenticBuilder

    from app.agents.factory import run_agent_stream

    # MagenticBuilder API may vary; run a constrained manager/specialist flow
    manager = agents["gerente"]
    # Build workflow for completeness / logging; still stream via our helpers for UI
    cfg_m = get_config().get("magentic", {})
    try:
        _workflow = MagenticBuilder(
            participants=[agents["analista"], agents["sintetizador"]],
            manager_agent=manager,
            max_round_count=int(cfg_m.get("max_rounds", 3)),
            max_stall_count=int(cfg_m.get("stall_limit", 1)),
        ).build()
        log.info("MagenticBuilder.build() ok — executando rodadas instrumentadas")
    except TypeError as exc:
        log.warning("MagenticBuilder kwargs variantes: %s", exc)
        _workflow = MagenticBuilder(
            participants=[agents["analista"], agents["sintetizador"]],
            manager_agent=manager,
        ).build()

    async def on_delta(agent_id: str, piece: str) -> None:
        await _emit(emit, recorder, {"type": "agent_delta", "agent": agent_id, "delta": piece})

    await _emit(
        emit, recorder, {"type": "agent_started", "agent": "gerente", "label": AGENT_LABELS["gerente"]}
    )
    plan = await run_agent_stream(
        manager,
        f"Plano Magentic para dossiê de {company}. Contexto:\n{ctx}",
        lambda p: on_delta("gerente", p),
        20,
    )
    await _emit(emit, recorder, {"type": "agent_finished", "agent": "gerente", "text": plan})
    await _message(emit, recorder, "gerente", "analista", "sua vez")
    await _emit(
        emit, recorder, {"type": "agent_started", "agent": "analista", "label": AGENT_LABELS["analista"]}
    )
    analise = await run_agent_stream(
        agents["analista"],
        f"Com base no plano:\n{plan}\nContexto:\n{ctx}",
        lambda p: on_delta("analista", p),
        25,
    )
    await _emit(emit, recorder, {"type": "agent_finished", "agent": "analista", "text": analise})
    await _message(emit, recorder, "gerente", "sintetizador", "sintetize")
    await _emit(
        emit,
        recorder,
        {"type": "agent_started", "agent": "sintetizador", "label": AGENT_LABELS["sintetizador"]},
    )
    dossier = await run_agent_stream(
        agents["sintetizador"],
        f"Dossiê final. Plano:\n{plan}\nAnálise:\n{analise}",
        lambda p: on_delta("sintetizador", p),
        25,
    )
    await _emit(
        emit, recorder, {"type": "agent_finished", "agent": "sintetizador", "text": dossier}
    )
    return dossier


async def _run_group_chat(
    emit, recorder, agents, company, dossier, budget, use_framework
) -> str:
    cfg = get_config()
    pricing = cfg.get("pricing", {})
    modules = cfg.get("proposal_modules", [])
    mod_lines = "\n".join(
        f"- {m.get('name')}: {m.get('hours')}h" for m in modules
    ) or "- Fundamentos 4h\n- Orquestração 6h\n- Lab 6h"
    price_note = pricing.get("note", "valores a combinar")
    timeout = max(10.0, budget * 0.45)

    if use_framework and agents:
        try:
            from agent_framework.orchestrations import GroupChatBuilder

            def selection_func(history):  # noqa: ANN001
                # Alternate redator → revisor → stop
                n = len(history) if history is not None else 0
                if n <= 1:
                    return agents["redator"]
                if n == 2:
                    return agents["revisor"]
                return None

            try:
                _ = GroupChatBuilder(
                    participants=[agents["redator"], agents["revisor"]],
                    selection_func=selection_func,
                ).build()
                log.info("GroupChatBuilder.build() ok")
            except Exception as exc:  # noqa: BLE001
                log.warning("GroupChatBuilder variante: %s", exc)
        except Exception as exc:  # noqa: BLE001
            log.warning("GroupChatBuilder indisponível: %s", exc)

    draft_prompt = (
        f"Cliente: {company}\nDossiê:\n{dossier}\n\n"
        f"Módulos sugeridos:\n{mod_lines}\n"
        f"Formato: {pricing.get('format','presencial + online')}\n"
        f"Preço: {price_note}\n"
        "Escreva a proposta completa em Markdown."
    )
    draft = await _safe_agent(
        emit,
        recorder,
        agents,
        "redator",
        draft_prompt,
        timeout,
        use_framework,
        fallback=SAMPLE_PROPOSAL.format(company=company),
    )
    await _message(emit, recorder, "redator", "revisor", "rascunho para revisão")
    review = await _safe_agent(
        emit,
        recorder,
        agents,
        "revisor",
        f"Revise a proposta:\n{draft}",
        max(8.0, budget * 0.35),
        use_framework,
        fallback="Aprovado. Sem preços inventados. Tom comercial adequado.",
    )
    await _message(emit, recorder, "revisor", "redator", "feedback")
    if "ajust" in review.lower() or "corrig" in review.lower():
        draft = await _safe_agent(
            emit,
            recorder,
            agents,
            "redator",
            f"Aplique o feedback do revisor e devolva a proposta final.\nFeedback:\n{review}\n\nOriginal:\n{draft}",
            timeout,
            use_framework,
            fallback=draft,
        )
    return draft


async def _run_images(emit, recorder, company, run_dir: Path, budget: float) -> None:
    timeout = min(40.0, max(10.0, budget))

    async def one(agent_id: str, kind: str) -> None:
        await _emit(
            emit,
            recorder,
            {"type": "agent_started", "agent": agent_id, "label": AGENT_LABELS[agent_id]},
        )
        await _emit(
            emit,
            recorder,
            {"type": "agent_delta", "agent": agent_id, "delta": f"Gerando {kind}…\n"},
        )
        result = await generate_image(kind, company, timeout=timeout, run_dir=run_dir)
        await _emit(
            emit,
            recorder,
            {
                "type": "agent_finished",
                "agent": agent_id,
                "text": f"{kind} pronta" + (" (fallback)" if result.get("fallback") else ""),
            },
        )
        await _emit(
            emit,
            recorder,
            {
                "type": "image_ready",
                "agent": agent_id,
                "kind": kind,
                "path": result.get("path"),
                "url": result.get("url"),
                "fallback": result.get("fallback", False),
            },
        )

    await asyncio.gather(
        one("img_capa", "capa"),
        one("img_solucao", "solucao"),
        one("img_resultado", "resultado"),
    )


async def _safe_agent(
    emit,
    recorder,
    agents,
    agent_id: str,
    prompt: str,
    timeout: float,
    use_framework: bool,
    fallback: str,
) -> str:
    await _emit(
        emit,
        recorder,
        {"type": "agent_started", "agent": agent_id, "label": AGENT_LABELS.get(agent_id, agent_id)},
    )
    text = fallback
    try:
        if use_framework and agent_id in agents:
            from app.agents.factory import run_agent_stream

            async def on_delta(piece: str) -> None:
                await _emit(
                    emit, recorder, {"type": "agent_delta", "agent": agent_id, "delta": piece}
                )

            text = await run_agent_stream(agents[agent_id], prompt, on_delta, timeout)
        else:
            # local fake stream of fallback
            step = max(1, len(fallback) // 10)
            for i in range(0, len(fallback), step):
                piece = fallback[i : i + step]
                await _emit(
                    emit, recorder, {"type": "agent_delta", "agent": agent_id, "delta": piece}
                )
                await asyncio.sleep(0.015)
            text = fallback
    except Exception as exc:  # noqa: BLE001
        log.warning("Agente %s falhou (%s) — fallback", agent_id, exc)
        await _emit(
            emit,
            recorder,
            {"type": "agent_delta", "agent": agent_id, "delta": f"\n[fallback] {fallback}"},
        )
        text = fallback

    await _emit(emit, recorder, {"type": "agent_finished", "agent": agent_id, "text": text})
    return text


async def _emit(emit: EmitFn, recorder: RunRecorder, event: dict[str, Any]) -> None:
    await emit(recorder.record(event))


async def _message(emit, recorder, src: str, dst: str, text: str) -> None:
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
    await asyncio.sleep(0.15)


async def _stage_start(emit, recorder, stage: str, budget: float) -> None:
    pattern, talk = STAGE_META[stage]
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


async def _stage_finish(emit, recorder, stage: str) -> None:
    await _emit(emit, recorder, {"type": "stage_finished", "stage": stage})


def _research_context(company: str, research: dict[str, Any]) -> str:
    import json

    slim = {k: research[k] for k in research if k != "web" or True}
    # keep payload bounded
    raw = json.dumps(slim, ensure_ascii=False)[:3500]
    return f"Cliente: {company}\nBase de pesquisa:\n{raw}"


def _get(d: dict[str, Any], key: str, default: str) -> str:
    v = d.get(key)
    return str(v) if v else default
