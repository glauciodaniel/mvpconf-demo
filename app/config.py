"""Load config.json and environment variables."""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
CACHE_DIR = DATA_DIR / "cache"
CLIENTS_DIR = DATA_DIR / "clients"
RUNS_DIR = ROOT / "runs"
ASSETS_DIR = ROOT / "assets"
BRAND_DIR = ASSETS_DIR / "brand"
FALLBACK_DIR = ASSETS_DIR / "fallback"
STATIC_DIR = ROOT / "static"
CONFIG_PATH = ROOT / "config.json"

load_dotenv(ROOT / ".env")


@lru_cache(maxsize=1)
def get_config() -> dict[str, Any]:
    with CONFIG_PATH.open(encoding="utf-8") as f:
        return json.load(f)


def reload_config() -> dict[str, Any]:
    get_config.cache_clear()
    return get_config()


def env(name: str, default: str | None = None) -> str | None:
    return os.getenv(name, default)


def project_endpoint() -> str | None:
    return env("AZURE_AI_PROJECT_ENDPOINT") or env("FOUNDRY_PROJECT_ENDPOINT")


def deployment_fast() -> str:
    return env("AZURE_DEPLOYMENT_FAST", "gpt-4o-mini") or "gpt-4o-mini"


def deployment_strong() -> str:
    return env("AZURE_DEPLOYMENT_STRONG", "gpt-4o") or "gpt-4o"


def deployment_image() -> str:
    return env("AZURE_DEPLOYMENT_IMAGE", "dall-e-3") or "dall-e-3"


def deployment_transcribe() -> str | None:
    return env("AZURE_DEPLOYMENT_TRANSCRIBE") or None


def ensure_dirs() -> None:
    for path in (CACHE_DIR, CLIENTS_DIR, RUNS_DIR, BRAND_DIR, FALLBACK_DIR):
        path.mkdir(parents=True, exist_ok=True)


def slugify(name: str) -> str:
    import re

    s = name.strip().lower()
    s = re.sub(r"[^\w\s-]", "", s, flags=re.UNICODE)
    s = re.sub(r"[\s_]+", "-", s)
    return s or "empresa"
