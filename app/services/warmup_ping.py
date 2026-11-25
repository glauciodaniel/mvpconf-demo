"""Warm connection to model deployments on page open."""

from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger("mvpconf.warmup")


async def ping_deployments() -> dict[str, Any]:
    from app.config import (
        deployment_fast,
        deployment_strong,
        env,
        get_config,
        project_endpoint,
    )

    if not get_config().get("warmup_ping", True):
        return {"skipped": True, "reason": "disabled in config"}

    endpoint = env("AZURE_OPENAI_ENDPOINT") or project_endpoint()
    if not endpoint:
        return {"skipped": True, "reason": "no AZURE_AI_PROJECT_ENDPOINT / AZURE_OPENAI_ENDPOINT"}

    results: dict[str, Any] = {}
    for name, dep in (("fast", deployment_fast()), ("strong", deployment_strong())):
        try:
            ok = await _ping_one(endpoint, dep)
            results[name] = {"ok": ok, "deployment": dep}
        except Exception as exc:  # noqa: BLE001
            log.warning("Warmup %s falhou: %s", name, exc)
            results[name] = {"ok": False, "error": str(exc), "deployment": dep}
    return results


async def _ping_one(endpoint: str, deployment: str) -> bool:
    try:
        from agent_framework import Agent
        from agent_framework.openai import OpenAIChatClient
        from azure.identity.aio import AzureCliCredential
    except ImportError as exc:
        raise RuntimeError(f"agent-framework não disponível: {exc}") from exc

    from app.config import env

    api_version = env("AZURE_OPENAI_API_VERSION", "2024-12-01-preview")
    async with AzureCliCredential() as credential:
        agent = Agent(
            client=OpenAIChatClient(
                model=deployment,
                azure_endpoint=endpoint.rstrip("/"),
                credential=credential,
                api_version=api_version,
            ),
            instructions="Reply with OK only.",
            name="warmup",
        )
        result = await agent.run("ping")
        text = getattr(result, "text", None) or str(result)
        return bool(text)
