"""Provider-neutral structured-chat adapter; no provider is required for tests."""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Protocol


class LLMUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class ToolCall:
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class LLMReply:
    text: str
    tool_calls: list[ToolCall]


class LLMProvider(Protocol):
    def complete(self, messages: list[dict], tools: list[dict]) -> LLMReply: ...


class UnavailableProvider:
    def complete(self, messages, tools):
        raise LLMUnavailable("The chat provider is not configured.")


class MockProvider:
    """Deterministic provider for tests; it never contacts an external service."""
    def complete(self, messages, tools):
        if any(message.get("role") == "tool" for message in messages):
            return LLMReply("I used the available authorized POLARIS X data. Satellite findings are thermal anomalies, not confirmed wildfires, and POLARIS X does not provide validated wildfire occurrence or spread predictions.", [])
        text = str(messages[-1].get("content", "")).lower()
        if "location" in text or "place" in text:
            return LLMReply("", [ToolCall("list_monitoring_locations", {})])
        if "alert" in text or "notification" in text:
            return LLMReply("", [ToolCall("list_recent_alerts", {})])
        return LLMReply("POLARIS X can report your authorized monitoring data. It does not provide validated wildfire occurrence or spread predictions.", [])


class OpenAICompatibleProvider:
    def __init__(self, api_base_url: str, model: str, api_key: str, timeout: float):
        if not api_base_url or not model or not api_key:
            raise LLMUnavailable("The chat provider is not configured.")
        self.url, self.model, self.api_key, self.timeout = api_base_url.rstrip("/") + "/chat/completions", model, api_key, timeout

    def complete(self, messages: list[dict], tools: list[dict]) -> LLMReply:
        payload = json.dumps({"model": self.model, "messages": messages, "tools": tools, "tool_choice": "auto"}).encode()
        request = urllib.request.Request(self.url, data=payload, headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                body = json.loads(response.read())
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError) as exc:
            raise LLMUnavailable("The chat provider is temporarily unavailable.") from exc
        try:
            message = body["choices"][0]["message"]
            calls = [ToolCall(item["function"]["name"], json.loads(item["function"].get("arguments") or "{}")) for item in message.get("tool_calls", [])]
            return LLMReply(message.get("content") or "", calls)
        except (KeyError, TypeError, json.JSONDecodeError) as exc:
            raise LLMUnavailable("The chat provider returned an invalid response.") from exc


def provider_from_config(config) -> LLMProvider:
    if config.get("LLM_PROVIDER") == "mock":
        return MockProvider()
    if config.get("LLM_PROVIDER") in {"openai_compatible", "openai"}:
        return OpenAICompatibleProvider(config.get("LLM_API_BASE_URL", ""), config.get("LLM_MODEL", ""), config.get("LLM_API_KEY", ""), float(config.get("LLM_TIMEOUT_SECONDS", 15)))
    return UnavailableProvider()
