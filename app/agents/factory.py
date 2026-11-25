"""Create Agents against Microsoft Foundry / Azure OpenAI deployments.

API note (agent-framework 1.26): use ``Agent`` + ``OpenAIChatClient`` with
``azure_endpoint`` and Azure credential — not the older ``ChatAgent`` /
``AzureAIAgentClient`` names from early samples.
"""

from __future__ import annotations

import logging
from contextlib import AsyncExitStack
from dataclasses import dataclass
from typing import Any

from app.config import (
    deployment_fast,
    deployment_strong,
    env,
    get_config,
    project_endpoint,
)

log = logging.getLogger("mvpconf.agents")


@dataclass
class AgentBundle:
    stack: AsyncExitStack
    agents: dict[str, Any]
    available: bool

    async def aclose(self) -> None:
        await self.stack.aclose()


def _azure_endpoint() -> str | None:
    return env("AZURE_OPENAI_ENDPOINT") or project_endpoint()


async def create_agents() -> AgentBundle:
    """Create all demo agents. Raises if Foundry/framework unavailable."""
    endpoint = _azure_endpoint()
    if not endpoint:
        raise RuntimeError(
            "Defina AZURE_AI_PROJECT_ENDPOINT ou AZURE_OPENAI_ENDPOINT no .env"
        )

    try:
        from agent_framework import Agent
        from agent_framework.openai import OpenAIChatClient
        from azure.identity.aio import DefaultAzureCredential
    except ImportError as exc:
        raise RuntimeError(
            "Instale agent-framework e azure-identity para o pipeline real"
        ) from exc

    cfg = get_config()
    limits = cfg.get("token_limits", {})
    fast = deployment_fast()
    strong = deployment_strong()
    api_version = env("AZURE_OPENAI_API_VERSION", "2024-12-01-preview")

    stack = AsyncExitStack()
    credential = await stack.enter_async_context(DefaultAzureCredential())

    def make_client(dep: str) -> Any:
        return OpenAIChatClient(
            model=dep,
            azure_endpoint=endpoint.rstrip("/"),
            credential=credential,
            api_version=api_version,
        )

    specs = [
        ("triagem", fast, "triagem", _TRIAGEM),
        ("esp_treinamento", fast, "especialista", _ESP_TREINAMENTO),
        ("esp_automacao", fast, "especialista", _ESP_AUTOMACAO),
        ("pesq_empresa", fast, "pesquisador", _PESQ_EMPRESA),
        ("pesq_noticias", fast, "pesquisador", _PESQ_NOTICIAS),
        ("pesq_maturidade", fast, "pesquisador", _PESQ_MATURIDADE),
        ("gerente", fast, "gerente", _GERENTE),
        ("analista", fast, "analista", _ANALISTA),
        ("sintetizador", fast, "sintetizador", _SINTETIZADOR),
        ("redator", strong, "redator", _REDATOR),
        ("revisor", fast, "revisor", _REVISOR),
    ]

    agents: dict[str, Any] = {}
    for agent_id, dep, limit_key, instructions in specs:
        max_tokens = limits.get(limit_key, 300)
        client = make_client(dep)
        kwargs: dict[str, Any] = {
            "client": client,
            "instructions": instructions,
            "name": agent_id,
        }
        try:
            agent = Agent(**kwargs, default_options={"max_tokens": max_tokens})
        except TypeError:
            try:
                agent = Agent(**kwargs, default_options={"max_completion_tokens": max_tokens})
            except TypeError:
                agent = Agent(**kwargs)
        agents[agent_id] = agent

    return AgentBundle(stack=stack, agents=agents, available=True)


async def run_agent_stream(
    agent: Any,
    prompt: str,
    on_delta,
    timeout: float,
) -> str:
    """Stream agent output with timeout; returns full text."""
    import asyncio

    async def _stream() -> str:
        full = ""
        # agent-framework 1.26: agent.run(..., stream=True)
        try:
            stream = agent.run(prompt, stream=True)
            if hasattr(stream, "__aiter__"):
                async for update in stream:
                    piece = getattr(update, "text", None) or ""
                    if not piece and hasattr(update, "contents"):
                        piece = "".join(
                            getattr(c, "text", "") or ""
                            for c in (update.contents or [])
                        )
                    if piece:
                        full += piece
                        await on_delta(piece)
                if full:
                    return full
        except TypeError:
            pass
        result = await agent.run(prompt)
        text = getattr(result, "text", None) or str(result)
        step = max(1, len(text) // 12)
        for i in range(0, len(text), step):
            piece = text[i : i + step]
            await on_delta(piece)
            await asyncio.sleep(0.02)
        return text

    return await asyncio.wait_for(_stream(), timeout=timeout)


_TRIAGEM = """Você é o agente de Triagem. Extraia o nome do cliente e o tipo de demanda
(treinamento vs automação n8n). Responda em português, curto. Termine indicando o handoff
para Esp. Treinamento ou Esp. Automação. Sem preços."""

_ESP_TREINAMENTO = """Você é o Especialista em Treinamento da Hcode Training.
Confirme o handoff e descreva em 2-3 frases o próximo passo (pesquisa do cliente). Português."""

_ESP_AUTOMACAO = """Você é o Especialista em Automação (n8n). Só atue se a demanda for automação.
Respostas curtas em português."""

_PESQ_EMPRESA = """Pesquisador: empresa e setor. Use o contexto fornecido. 4-6 frases, português, sem inventar números."""

_PESQ_NOTICIAS = """Pesquisador: notícias/sinais recentes. Use o contexto. 4-6 frases, português, sem inventar fatos específicos não dados."""

_PESQ_MATURIDADE = """Pesquisador: maturidade em tecnologia e IA. Use o contexto. 4-6 frases, português."""

_GERENTE = """Gerente Magentic. Coordene Analista e Sintetizador para um dossiê de uma página.
Ordens curtas em português. Máximo 3 rodadas."""

_ANALISTA = """Analista. Sintetize setor e maturidade do cliente. Português, objetivo."""

_SINTETIZADOR = """Sintetizador. Produza dossiê de uma página: contexto, desafio, oportunidade de capacitação. Português."""

_REDATOR = """Redator comercial Hcode Training. Escreva proposta em Markdown com:
contexto do cliente, desafio, solução proposta, programa (módulos/carga/formato), próximos passos.
NÃO invente preços: use 'valores a combinar' se não houver valor. Português."""

_REVISOR = """Revisor. Verifique tom, ausência de preços inventados e clareza. Aprove ou peça 1 ajuste. Português, curto."""
