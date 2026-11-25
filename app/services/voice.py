"""Voice transcription: Foundry → faster-whisper → reject (client uses Web Speech / text)."""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path

log = logging.getLogger("mvpconf.voice")


async def transcribe_audio(data: bytes, filename: str = "audio.webm") -> str:
    text = await _try_foundry(data, filename)
    if text:
        return text
    text = await _try_faster_whisper(data, filename)
    if text:
        return text
    raise RuntimeError(
        "Transcrição indisponível no backend. Use Web Speech API ou a caixa de texto."
    )


async def _try_foundry(data: bytes, filename: str) -> str | None:
    from app.config import deployment_transcribe, env, project_endpoint

    dep = deployment_transcribe()
    endpoint = env("AZURE_OPENAI_ENDPOINT") or project_endpoint()
    if not dep or not endpoint:
        return None
    try:
        from azure.identity import DefaultAzureCredential, get_bearer_token_provider
        from openai import AsyncAzureOpenAI
    except ImportError:
        return None

    token_provider = get_bearer_token_provider(
        DefaultAzureCredential(), "https://cognitiveservices.azure.com/.default"
    )
    base = endpoint.rstrip("/")
    if "services.ai.azure.com" in base and "/openai" not in base:
        return None

    client = AsyncAzureOpenAI(
        azure_endpoint=base,
        azure_ad_token_provider=token_provider,
        api_version=env("AZURE_OPENAI_API_VERSION", "2024-12-01-preview")
        or "2024-12-01-preview",
    )
    suffix = Path(filename).suffix or ".webm"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(data)
        tmp_path = Path(tmp.name)
    try:
        with tmp_path.open("rb") as f:
            result = await client.audio.transcriptions.create(model=dep, file=f)
        return (result.text or "").strip() or None
    except Exception as exc:  # noqa: BLE001
        log.warning("Foundry transcribe falhou: %s", exc)
        return None
    finally:
        tmp_path.unlink(missing_ok=True)


async def _try_faster_whisper(data: bytes, filename: str) -> str | None:
    try:
        from faster_whisper import WhisperModel  # type: ignore
    except ImportError:
        log.info("faster-whisper não instalado")
        return None

    import asyncio

    suffix = Path(filename).suffix or ".webm"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(data)
        tmp_path = Path(tmp.name)

    def _run() -> str:
        model = WhisperModel("base", device="cpu", compute_type="int8")
        segments, _info = model.transcribe(str(tmp_path), language="pt")
        return " ".join(s.text.strip() for s in segments).strip()

    try:
        return await asyncio.to_thread(_run) or None
    except Exception as exc:  # noqa: BLE001
        log.warning("faster-whisper falhou: %s", exc)
        return None
    finally:
        tmp_path.unlink(missing_ok=True)
