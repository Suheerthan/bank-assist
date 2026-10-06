"""Thin LLM client. Any failure returns None so the caller falls back to rules/templates.

The app is fully usable with LLM_PROVIDER=none, which matters on hackathon Wi-Fi.

Resilience (Gemini is often busy and answers 503):
  * tries GEMINI_MODEL first, then each model in GEMINI_FALLBACK_MODELS;
  * retries a busy model (429/500/503) once after a short pause;
  * remembers the last model that worked and starts there next time;
  * if every model fails, pauses AI calls for LLM_COOLDOWN_SECONDS so the console stays instant
    (rules + templates answer meanwhile), then tries again automatically.
"""
import json
import re
import time

import httpx

from . import config

RETRYABLE = {429, 500, 502, 503, 504}
_state = {"working_model": None, "cooldown_until": 0.0}


def _gemini_models() -> list[str]:
    models = [config.GEMINI_MODEL] + [m.strip() for m in config.GEMINI_FALLBACK_MODELS.split(",") if m.strip()]
    seen, ordered = set(), []
    if _state["working_model"] in models:
        models.insert(0, _state["working_model"])
    for m in models:
        if m not in seen:
            seen.add(m)
            ordered.append(m)
    return ordered


def provider_name() -> str:
    if config.LLM_PROVIDER == "gemini" and config.GEMINI_API_KEY:
        return f"Gemini ({_state['working_model'] or config.GEMINI_MODEL})"
    if config.LLM_PROVIDER == "anthropic" and config.ANTHROPIC_API_KEY:
        return f"Claude ({config.ANTHROPIC_MODEL})"
    return "Offline rules + templates"


def enabled() -> bool:
    return provider_name() != "Offline rules + templates"


def load_prompt(name: str) -> str:
    return (config.PROMPT_DIR / f"{name}.txt").read_text(encoding="utf-8")


def _log(msg: str) -> None:
    for secret in (config.GEMINI_API_KEY, config.ANTHROPIC_API_KEY):
        if secret:
            msg = msg.replace(secret, "***")
    print(f"[llm] {msg}")


def _gemini(prompt: str, max_tokens: int) -> str | None:
    for model in _gemini_models():
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        for attempt in range(2):
            try:
                r = httpx.post(
                    url,
                    headers={"x-goog-api-key": config.GEMINI_API_KEY},  # header, so the key never appears in logs
                    json={"contents": [{"parts": [{"text": prompt}]}],
                          "generationConfig": {"temperature": 0.2, "maxOutputTokens": max_tokens}},
                    timeout=config.LLM_TIMEOUT_SECONDS,
                )
            except httpx.HTTPError as exc:  # timeout, no internet
                _log(f"{model}: {exc.__class__.__name__}, trying next model")
                break
            if r.status_code == 200:
                try:
                    parts = r.json()["candidates"][0]["content"]["parts"]
                    text = "".join(p.get("text", "") for p in parts).strip()
                except (KeyError, IndexError, ValueError):
                    text = ""
                if text:
                    if _state["working_model"] != model:
                        _log(f"using {model}")
                    _state["working_model"] = model
                    return text
                _log(f"{model}: empty answer, trying next model")
                break
            if r.status_code in RETRYABLE and attempt == 0:
                _log(f"{model}: busy ({r.status_code}), retrying once")
                time.sleep(1.0)
                continue
            _log(f"{model}: HTTP {r.status_code}, trying next model")
            break
    return None


def _anthropic(prompt: str, max_tokens: int) -> str | None:
    try:
        r = httpx.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": config.ANTHROPIC_API_KEY, "anthropic-version": "2023-06-01",
                     "content-type": "application/json"},
            json={"model": config.ANTHROPIC_MODEL, "max_tokens": max_tokens, "temperature": 0.2,
                  "messages": [{"role": "user", "content": prompt}]},
            timeout=config.LLM_TIMEOUT_SECONDS,
        )
        r.raise_for_status()
        return "".join(b.get("text", "") for b in r.json()["content"] if b.get("type") == "text").strip() or None
    except Exception as exc:  # network, quota, bad key, bad model name
        _log(f"call failed: {str(exc).splitlines()[0]}")
        return None


def complete(prompt: str, max_tokens: int = 600) -> str | None:
    if not enabled():
        return None
    if time.monotonic() < _state["cooldown_until"]:
        return None  # AI recently unavailable: answer instantly from rules + templates
    text = _gemini(prompt, max_tokens) if config.LLM_PROVIDER == "gemini" else _anthropic(prompt, max_tokens)
    if text is None:
        _state["cooldown_until"] = time.monotonic() + config.LLM_COOLDOWN_SECONDS
        _log(f"AI unavailable, using rules + templates for the next {config.LLM_COOLDOWN_SECONDS:.0f}s")
    return text


def complete_json(prompt: str) -> dict | None:
    text = complete(prompt, max_tokens=800)
    if not text:
        return None
    text = re.sub(r"```(?:json)?", "", text).strip()
    m = re.search(r"\{.*\}", text, re.S)
    try:
        return json.loads(m.group(0)) if m else None
    except json.JSONDecodeError:
        return None
