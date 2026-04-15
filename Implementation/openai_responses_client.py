#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import urllib.request
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class OpenAIConfig:
    api_key: str
    model: str
    base_url: str = "https://api.openai.com/v1/responses"


class OpenAIError(RuntimeError):
    pass


def load_config(model: str) -> OpenAIConfig | None:
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        return None
    base_url = os.environ.get("OPENAI_BASE_URL", "").strip() or "https://api.openai.com/v1/responses"
    return OpenAIConfig(api_key=api_key, model=model, base_url=base_url)


def responses_create(config: OpenAIConfig, payload: dict[str, Any], timeout_s: int = 120) -> dict[str, Any]:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        config.base_url,
        data=data,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {config.api_key}",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw)
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode("utf-8")
        except Exception:
            body = ""
        raise OpenAIError(f"HTTP {e.code}: {body or e.reason}") from e
    except Exception as e:
        raise OpenAIError(str(e)) from e


def extract_output_text(response: dict[str, Any]) -> str:
    # Responses API returns `output` items; simplest is to concatenate text.
    parts: list[str] = []
    for item in response.get("output", []) or []:
        for content in item.get("content", []) or []:
            if content.get("type") == "output_text" and "text" in content:
                parts.append(content["text"])
    return "".join(parts).strip()

