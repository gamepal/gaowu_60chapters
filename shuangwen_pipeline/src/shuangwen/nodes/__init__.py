"""LangGraph 节点实现。每个节点是 ``async def node(state, deps) -> dict``。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from langgraph.config import get_stream_writer

from ..llm import LLMClient


@dataclass
class Deps:
    llm: LLMClient
    output_dir: str | None = None


def emit(event: str, **data: Any) -> None:
    """向 SSE 推送自定义进度事件（在图外调用时静默忽略）。"""
    try:
        writer = get_stream_writer()
    except Exception:
        return
    writer({"event": event, **data})


def meta(state: dict, **extra: Any) -> dict:
    return {"run_id": state.get("run_id"), **extra}
