import json
import os
from dataclasses import dataclass, field

import requests

from categories import CATEGORIES
from prompt import build_prompt

# Baseline classifier: one synchronous, blocking Ollama call per ticket. No caching, retries,
# queuing or batching -- Assignment 1 measures this as-is.

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://ollama:11434/api/generate")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2:1b")
OLLAMA_TIMEOUT_S = float(os.getenv("OLLAMA_TIMEOUT_S", "600"))
# "true"/"false" is sent as Ollama's `think` flag; anything else (baseline: "default") sends
# nothing, so each model behaves as shipped -- gemma4 thinks, the other candidates cannot.
OLLAMA_THINK = os.getenv("OLLAMA_THINK", "default").strip().lower()

# Structured output: decoding is constrained to a JSON object whose value is one category name.
RESPONSE_FORMAT = {
    "type": "object",
    "properties": {"category": {"type": "string", "enum": CATEGORIES}},
    "required": ["category"],
}
OPTIONS = {"temperature": 0, "seed": 42}


class OllamaError(Exception):
    """Ollama returned a non-200 response."""


class ClassificationError(Exception):
    """Ollama answered, but no single valid category could be recovered from the answer."""

    def __init__(self, message: str, ollama: dict):
        super().__init__(message)
        self.ollama = ollama


@dataclass
class Classification:
    category: str
    ollama: dict = field(default_factory=dict)  # Ollama's own timing breakdown for the call


def _request_body(narrative: str) -> dict:
    body = {
        "model": OLLAMA_MODEL,
        "prompt": build_prompt(narrative),
        "stream": False,
        "format": RESPONSE_FORMAT,
        "options": OPTIONS,
    }
    if OLLAMA_THINK in ("true", "false"):
        body["think"] = OLLAMA_THINK == "true"
    return body


def _timings(payload: dict) -> dict:
    """Ollama durations are in nanoseconds; total minus the parts is time spent waiting."""
    return {
        "ollama_total_ms": round(payload.get("total_duration", 0) / 1e6, 1),
        "ollama_load_ms": round(payload.get("load_duration", 0) / 1e6, 1),
        "prompt_tokens": payload.get("prompt_eval_count", 0),
        "prompt_eval_ms": round(payload.get("prompt_eval_duration", 0) / 1e6, 1),
        "eval_tokens": payload.get("eval_count", 0),
        "eval_ms": round(payload.get("eval_duration", 0) / 1e6, 1),
    }


def _parse_category(text: str) -> str | None:
    try:
        value = json.loads(text).get("category")
    except (ValueError, AttributeError):
        value = text
    if isinstance(value, str):
        for category in CATEGORIES:
            if value.strip().lower() == category.lower():
                return category
    # Free-text fallback: accept only if exactly one category name appears in the answer.
    found = [c for c in CATEGORIES if c.lower() in text.lower()]
    return found[0] if len(found) == 1 else None


def classify_detailed(narrative: str) -> Classification:
    response = requests.post(OLLAMA_URL, json=_request_body(narrative), timeout=OLLAMA_TIMEOUT_S)
    if response.status_code != 200:
        raise OllamaError(f"Ollama HTTP {response.status_code}: {response.text[:200]}")
    payload = response.json()
    timings = _timings(payload)
    category = _parse_category(payload.get("response", ""))
    if category is None:
        raise ClassificationError(
            f"no single valid category in model output: {payload.get('response', '')[:200]!r}",
            timings,
        )
    return Classification(category=category, ollama=timings)


def classify(narrative: str) -> str:
    return classify_detailed(narrative).category
