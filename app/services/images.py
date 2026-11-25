"""Image generation with local SVG fallbacks."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

from app.config import FALLBACK_DIR, RUNS_DIR, ensure_dirs

log = logging.getLogger("mvpconf.images")

KINDS = ("capa", "solucao", "resultado")

PROMPTS = {
    "capa": (
        "Professional training proposal cover, abstract multi-agent network, "
        "navy blue #001635 and electric blue #008EFF, clean corporate, no text"
    ),
    "solucao": (
        "Illustration of AI agent orchestration pipeline with five stages, "
        "modern flat design, navy and blue palette, no text"
    ),
    "resultado": (
        "Illustration of trained team delivering an AI proposal, "
        "optimistic, orange accent #FF760C and white, no text"
    ),
}


def ensure_fallback_svgs() -> None:
    ensure_dirs()
    specs = {
        "capa": ("#001635", "#008EFF", "Capa da proposta"),
        "solucao": ("#001635", "#364459", "Solução multiagente"),
        "resultado": ("#FFFFFF", "#FF760C", "Resultado do time"),
    }
    for kind, (bg, accent, label) in specs.items():
        path = FALLBACK_DIR / f"{kind}.svg"
        if path.exists():
            continue
        fg = "#FFFFFF" if bg.lower() != "#ffffff" else "#101010"
        path.write_text(
            f"""<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="720" viewBox="0 0 1280 720">
  <rect width="1280" height="720" fill="{bg}"/>
  <circle cx="980" cy="180" r="160" fill="{accent}" opacity="0.35"/>
  <circle cx="220" cy="560" r="200" fill="{accent}" opacity="0.2"/>
  <rect x="120" y="260" width="640" height="16" rx="8" fill="{accent}"/>
  <text x="120" y="360" font-family="Arial,sans-serif" font-size="56" fill="{fg}">{label}</text>
  <text x="120" y="420" font-family="Arial,sans-serif" font-size="28" fill="{accent}">Hcode Training · MVP Conf</text>
</svg>
""",
            encoding="utf-8",
        )


async def generate_image(
    kind: str,
    company: str,
    timeout: float = 40.0,
    run_dir: Path | None = None,
) -> dict[str, Any]:
    """Try Foundry/OpenAI image; on failure return local fallback."""
    ensure_fallback_svgs()
    fallback = FALLBACK_DIR / f"{kind}.svg"
    fallback_url = f"/assets/fallback/{kind}.svg"

    try:
        result = await asyncio.wait_for(
            _try_foundry_image(kind, company, run_dir),
            timeout=timeout,
        )
        if result:
            return result
    except Exception as exc:  # noqa: BLE001
        log.warning("Imagem %s falhou/timeout: %s — usando fallback", kind, exc)

    # copy fallback into run folder if provided
    out_url = fallback_url
    if run_dir:
        run_dir.mkdir(parents=True, exist_ok=True)
        dest = run_dir / f"{kind}.svg"
        dest.write_bytes(fallback.read_bytes())
        out_url = f"/runs/{run_dir.name}/{kind}.svg"

    return {
        "kind": kind,
        "path": out_url,
        "url": out_url,
        "fallback": True,
    }


async def _try_foundry_image(
    kind: str, company: str, run_dir: Path | None
) -> dict[str, Any] | None:
    """Best-effort image generation via Azure OpenAI images API if configured."""
    from app.config import deployment_image, env, project_endpoint

    endpoint = env("AZURE_OPENAI_ENDPOINT") or project_endpoint()
    if not endpoint:
        return None

    # Prefer openai SDK if present
    try:
        from azure.identity import DefaultAzureCredential, get_bearer_token_provider
        from openai import AsyncAzureOpenAI
    except ImportError:
        log.warning("openai/azure-identity ausentes para imagens")
        return None

    token_provider = get_bearer_token_provider(
        DefaultAzureCredential(), "https://cognitiveservices.azure.com/.default"
    )
    # Normalize endpoint for Azure OpenAI style
    base = endpoint.rstrip("/")
    if "services.ai.azure.com" in base and "/openai" not in base:
        # Foundry project endpoints vary; skip if not classic AOAI
        log.info("Endpoint Foundry sem AOAI clássico — skip imagem remota")
        return None

    client = AsyncAzureOpenAI(
        azure_endpoint=base,
        azure_ad_token_provider=token_provider,
        api_version=env("AZURE_OPENAI_API_VERSION", "2024-12-01-preview")
        or "2024-12-01-preview",
    )
    prompt = f"{PROMPTS.get(kind, PROMPTS['capa'])}. Cliente: {company}."
    resp = await client.images.generate(
        model=deployment_image(),
        prompt=prompt,
        size="1024x1024",
        n=1,
    )
    import base64

    item = resp.data[0]
    ensure_dirs()
    target_dir = run_dir or (RUNS_DIR / "images")
    target_dir.mkdir(parents=True, exist_ok=True)
    out = target_dir / f"{kind}.png"

    if getattr(item, "b64_json", None):
        out.write_bytes(base64.b64decode(item.b64_json))
    elif getattr(item, "url", None):
        import httpx

        async with httpx.AsyncClient() as http:
            r = await http.get(item.url, timeout=30)
            r.raise_for_status()
            out.write_bytes(r.content)
    else:
        return None

    rel = f"/runs/{target_dir.name}/{kind}.png" if run_dir else f"/assets/generated/{kind}.png"
    return {"kind": kind, "path": str(out), "url": rel, "fallback": False}
