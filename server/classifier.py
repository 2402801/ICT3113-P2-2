import json
import os
import time
from dataclasses import dataclass, field

import requests

from categories import CATEGORIES
from prompt import build_prompt

# Baseline classifier: one synchronous, blocking Ollama call per ticket. No caching, retries,
# queuing or batching -- Assignment 1 measures this as-is.

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://ollama:11434/api/generate")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2:1b")  # the single model, or the cascade's first (small) model
OLLAMA_TIMEOUT_S = float(os.getenv("OLLAMA_TIMEOUT_S", "600"))
# "true"/"false" is sent as Ollama's `think` flag; anything else (baseline: "default") sends
# nothing, so each model behaves as shipped -- gemma4 thinks, the other candidates cannot.
OLLAMA_THINK = os.getenv("OLLAMA_THINK", "default").strip().lower()

# A2 cascade (datasets/a2/escalation_rule.md). OLLAMA_MODEL answers first; its answer is kept when it is in the
# setting's accept list, otherwise the ticket is escalated to CASCADE_LARGE_MODEL, whose answer is final.
# "off" keeps the single-model behaviour. Both models must be resident (OLLAMA_MAX_LOADED_MODELS=2).
CASCADE_SETTING = os.getenv("CASCADE_SETTING", "off").strip().lower()
CASCADE_LARGE_MODEL = os.getenv("CASCADE_LARGE_MODEL", "gemma4:e4b")
_S1_ACCEPT = {"Consumer loan", "Debt collection", "Credit card", "Money transfer or service"}
CASCADE_ACCEPT = {"s1": _S1_ACCEPT, "s2": _S1_ACCEPT | {"Mortgage"}}
if CASCADE_SETTING != "off" and CASCADE_SETTING not in CASCADE_ACCEPT:
    raise ValueError(f"CASCADE_SETTING must be off, s1 or s2, not {CASCADE_SETTING!r}")
assert all(c in CATEGORIES for accept in CASCADE_ACCEPT.values() for c in accept)

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
    ollama: dict = field(default_factory=dict)  # Ollama's own timing breakdown for the final call
    route: dict = field(default_factory=dict)  # which model gave the final answer and whether it was escalated


def _request_body(model: str, narrative: str) -> dict:
    body = {
        "model": model,
        "prompt": build_prompt(narrative),
        "stream": False,
        "format": RESPONSE_FORMAT,
        "options": OPTIONS,
    }
    # Only gemma4 can think; the flag is not sent to the other models, so a cascade with think=false changes
    # gemma4 only and the small model's call stays identical.
    if OLLAMA_THINK in ("true", "false") and model.startswith("gemma4"):
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


def _call(model: str, narrative: str) -> Classification:
    start = time.perf_counter()
    response = requests.post(OLLAMA_URL, json=_request_body(model, narrative), timeout=OLLAMA_TIMEOUT_S)
    call_ms = round((time.perf_counter() - start) * 1000, 1)
    if response.status_code != 200:
        raise OllamaError(f"Ollama HTTP {response.status_code}: {response.text[:200]}")
    payload = response.json()
    timings = {**_timings(payload), "call_ms": call_ms}
    category = _parse_category(payload.get("response", ""))
    if category is None:
        raise ClassificationError(
            f"no single valid category in model output: {payload.get('response', '')[:200]!r}",
            timings,
        )
    return Classification(category=category, ollama=timings)


def _cascade(narrative: str) -> Classification:
    route = {"cascade": CASCADE_SETTING, "final_model": OLLAMA_MODEL, "escalated": 0}
    try:
        small = _call(OLLAMA_MODEL, narrative)
        route.update(small_answer=small.category, small_ms=small.ollama["call_ms"])
    except ClassificationError as exc:  # no valid category from the small model: escalate
        small = None
        route.update(small_answer="-", small_ms=exc.ollama.get("call_ms", 0))
    except Exception as exc:
        exc.route = route
        raise
    if small is not None and small.category in CASCADE_ACCEPT[CASCADE_SETTING]:
        small.route = route
        return small

    route.update(final_model=CASCADE_LARGE_MODEL, escalated=1)
    try:
        large = _call(CASCADE_LARGE_MODEL, narrative)
    except Exception as exc:
        exc.route = route
        raise
    large.route = {**route, "large_ms": large.ollama["call_ms"]}
    return large


def classify_detailed(narrative: str) -> Classification:
    if CASCADE_SETTING != "off":
        return _cascade(narrative)
    result = _call(OLLAMA_MODEL, narrative)
    result.route = {"final_model": OLLAMA_MODEL, "escalated": 0}
    return result


def classify(narrative: str) -> str:
    return classify_detailed(narrative).category
