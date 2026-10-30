"""统一模型调用层：LiteLLM 路由 + 结构化输出校验/修复 + 上下文缓存 + 用量账本。"""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any, Protocol, TypeVar

from pydantic import BaseModel, ValidationError

from .config import AppSettings, ModelRoute, Role

log = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)
Message = dict[str, Any]


class LLMBackend(Protocol):
    async def complete(
        self,
        *,
        task: str,
        route: ModelRoute,
        messages: list[Message],
        schema: type[BaseModel] | None,
        meta: dict[str, Any],
    ) -> "Completion": ...


@dataclass
class Completion:
    text: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cached_tokens: int = 0
    cost_usd: float = 0.0


@dataclass
class UsageRecord:
    task: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    cached_tokens: int
    cost_usd: float
    seconds: float
    run_id: str | None = None


@dataclass
class UsageLedger:
    records: list[UsageRecord] = field(default_factory=list)

    def add(self, record: UsageRecord) -> None:
        self.records.append(record)

    def summary(self, run_id: str | None = None) -> dict[str, Any]:
        rows = [r for r in self.records if run_id is None or r.run_id == run_id]
        by_model: dict[str, dict[str, float]] = {}
        for r in rows:
            agg = by_model.setdefault(
                r.model, {"calls": 0, "prompt_tokens": 0, "completion_tokens": 0, "cached_tokens": 0, "cost_usd": 0.0}
            )
            agg["calls"] += 1
            agg["prompt_tokens"] += r.prompt_tokens
            agg["completion_tokens"] += r.completion_tokens
            agg["cached_tokens"] += r.cached_tokens
            agg["cost_usd"] += r.cost_usd
        return {
            "calls": len(rows),
            "cost_usd": round(sum(r.cost_usd for r in rows), 4),
            "by_model": by_model,
        }


class StructuredOutputError(RuntimeError):
    pass


# ---------------------------------------------------------------------------
# JSON 提取
# ---------------------------------------------------------------------------

_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.S)


def extract_json(text: str) -> str:
    """从模型输出里抠出 JSON（兼容 ```json 围栏与前后废话）。"""
    text = text.strip()
    m = _FENCE_RE.search(text)
    if m:
        text = m.group(1).strip()
    if text.startswith("{") or text.startswith("["):
        return text
    start = min((i for i in (text.find("{"), text.find("[")) if i >= 0), default=-1)
    if start < 0:
        raise StructuredOutputError("输出中找不到 JSON")
    closer = "}" if text[start] == "{" else "]"
    end = text.rfind(closer)
    if end <= start:
        raise StructuredOutputError("输出中的 JSON 不完整")
    return text[start : end + 1]


def schema_instruction(schema: type[BaseModel]) -> str:
    return (
        "\n\n# JSON 输出契约\n严格输出一个符合以下 JSON Schema 的 JSON 对象，不要输出 Schema 以外的任何文字：\n"
        + json.dumps(schema.model_json_schema(), ensure_ascii=False)
    )


# ---------------------------------------------------------------------------
# LiteLLM 后端
# ---------------------------------------------------------------------------


class LiteLLMBackend:
    def __init__(self, settings: AppSettings):
        import litellm

        litellm.drop_params = True  # 不同厂商不支持的采样参数自动丢弃
        self._litellm = litellm
        self.settings = settings

    async def complete(self, *, task, route, messages, schema, meta) -> Completion:
        params: dict[str, Any] = {
            "model": route.model,
            "messages": messages,
            "temperature": route.temperature,
            "timeout": self.settings.request_timeout,
            "num_retries": self.settings.num_retries,
            "metadata": {"task": task, **{k: v for k, v in meta.items() if isinstance(v, (str, int, float))}},
        }
        if route.top_p is not None:
            params["top_p"] = route.top_p
        if route.presence_penalty is not None:
            params["presence_penalty"] = route.presence_penalty
        if route.max_tokens:
            params["max_tokens"] = route.max_tokens
        if schema is not None and route.native_json:
            params["response_format"] = {"type": "json_object"}

        resp = await self._litellm.acompletion(**params)
        text = resp.choices[0].message.content or ""
        usage = getattr(resp, "usage", None)
        prompt_tokens = getattr(usage, "prompt_tokens", 0) or 0
        completion_tokens = getattr(usage, "completion_tokens", 0) or 0
        details = getattr(usage, "prompt_tokens_details", None)
        cached = getattr(details, "cached_tokens", 0) or 0 if details else 0
        try:
            cost = float(self._litellm.completion_cost(completion_response=resp) or 0.0)
        except Exception:  # 未登记价格的模型
            cost = 0.0
        return Completion(text, prompt_tokens, completion_tokens, cached, cost)


# ---------------------------------------------------------------------------
# 客户端
# ---------------------------------------------------------------------------


class LLMClient:
    """所有节点通过它调用模型；后端可替换为 Mock 以便离线跑通全链路。"""

    def __init__(
        self,
        backend: LLMBackend,
        routes: dict[Role, ModelRoute],
        *,
        cache_ttl_seconds: int = 7200,
        max_repair_attempts: int = 2,
    ):
        self.backend = backend
        self.routes = routes
        self.cache_ttl_seconds = cache_ttl_seconds
        self.max_repair_attempts = max_repair_attempts
        self.ledger = UsageLedger()

    def route(self, role: Role, temperature: float | None = None) -> ModelRoute:
        return self.routes[role].with_temperature(temperature)

    def system_message(self, text: str, *, route: ModelRoute, cache: bool = False) -> Message:
        """构造 system 消息；cache=True 且路由启用缓存时打上 cache_control。

        LiteLLM 会把带 cache_control 的前缀转换为 Gemini CachedContent
        （或 Anthropic prompt cache），后续调用复用同一缓存，免除重复输入 Token。
        """
        if cache and route.context_cache:
            return {
                "role": "system",
                "content": [
                    {
                        "type": "text",
                        "text": text,
                        "cache_control": {"type": "ephemeral", "ttl": f"{self.cache_ttl_seconds}s"},
                    }
                ],
            }
        return {"role": "system", "content": text}

    async def _call(
        self,
        task: str,
        route: ModelRoute,
        messages: list[Message],
        schema: type[BaseModel] | None,
        meta: dict[str, Any],
    ) -> str:
        started = time.monotonic()
        result = await self.backend.complete(task=task, route=route, messages=messages, schema=schema, meta=meta)
        self.ledger.add(
            UsageRecord(
                task=task,
                model=route.model,
                prompt_tokens=result.prompt_tokens,
                completion_tokens=result.completion_tokens,
                cached_tokens=result.cached_tokens,
                cost_usd=result.cost_usd,
                seconds=round(time.monotonic() - started, 2),
                run_id=meta.get("run_id"),
            )
        )
        log.debug("llm %s via %s: %d chars", task, route.model, len(result.text))
        return result.text

    async def text(
        self,
        role: Role,
        messages: list[Message],
        *,
        task: str,
        temperature: float | None = None,
        meta: dict[str, Any] | None = None,
    ) -> str:
        route = self.route(role, temperature)
        return (await self._call(task, route, messages, None, meta or {})).strip()

    async def structured(
        self,
        role: Role,
        messages: list[Message],
        schema: type[T],
        *,
        task: str,
        temperature: float | None = None,
        meta: dict[str, Any] | None = None,
    ) -> T:
        """请求 JSON 并用 Pydantic 校验；失败时把错误回灌给模型修复，最多重试 N 次。"""
        route = self.route(role, temperature)
        messages = _append_to_system(messages, schema_instruction(schema))
        last_error: Exception | None = None
        convo = list(messages)
        for attempt in range(self.max_repair_attempts + 1):
            raw = await self._call(task, route, convo, schema, {**(meta or {}), "attempt": attempt})
            try:
                return schema.model_validate_json(extract_json(raw))
            except (ValidationError, StructuredOutputError, ValueError) as exc:
                last_error = exc
                log.warning("%s 结构化输出校验失败（第%d次）：%s", task, attempt + 1, str(exc)[:300])
                convo = list(messages) + [
                    {"role": "assistant", "content": raw},
                    {
                        "role": "user",
                        "content": f"上面的输出没有通过 JSON Schema 校验，错误如下：\n{str(exc)[:2000]}\n请修正后重新输出完整 JSON，不要任何解释。",
                    },
                ]
        raise StructuredOutputError(f"{task} 连续 {self.max_repair_attempts + 1} 次输出不合法：{last_error}")


def _append_to_system(messages: list[Message], extra: str) -> list[Message]:
    out = [dict(m) for m in messages]
    for m in out:
        if m["role"] != "system":
            continue
        if isinstance(m["content"], str):
            m["content"] = m["content"] + extra
        else:
            m["content"] = list(m["content"]) + [{"type": "text", "text": extra}]
        return out
    return [{"role": "system", "content": extra.strip()}] + out


def build_llm_client(settings: AppSettings) -> LLMClient:
    if settings.mock_llm:
        from .mock import MockBackend

        backend: LLMBackend = MockBackend()
    else:
        backend = LiteLLMBackend(settings)
    return LLMClient(backend, settings.routes, cache_ttl_seconds=settings.cache_ttl_seconds)
