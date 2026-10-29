"""Kết nối OpenAI-compatible API."""
from urllib.parse import urlparse

import httpx
from openai import OpenAI


def normalize_base_url(url: str) -> str:
    url = (url or "").strip().rstrip("/")
    if url and urlparse(url).path in ("", "/"):
        url += "/v1"
    return url


def make_client(cfg: dict) -> OpenAI:
    return OpenAI(
        base_url=normalize_base_url(cfg["base_url"]),
        api_key=cfg.get("api_key") or "none",
        timeout=httpx.Timeout(300, connect=20),
        max_retries=2,
    )


def list_models(cfg: dict) -> list[str]:
    # 10 giây là đủ cho danh sách model; không để luồng nền treo khi máy chủ không phản hồi
    return sorted(m.id for m in make_client(cfg).with_options(timeout=10, max_retries=0).models.list().data)
