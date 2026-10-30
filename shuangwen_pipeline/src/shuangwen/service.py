"""运行管理：后台驱动 LangGraph、事件总线（内存 / Redis）与运行快照。"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from collections import defaultdict
from typing import Any, AsyncIterator

from langgraph.types import Command

from .config import PipelineSettings
from .graph import run_config
from .schemas import HumanSelection

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 事件总线
# ---------------------------------------------------------------------------


class MemoryEventBus:
    """进程内事件总线，保留每个 run 的历史事件，晚到的 SSE 订阅者可补齐。"""

    def __init__(self, history: int = 2000):
        self.history = history
        self._events: dict[str, list[dict]] = defaultdict(list)
        self._subs: dict[str, set[asyncio.Queue]] = defaultdict(set)

    async def publish(self, run_id: str, event: dict) -> None:
        event = {"ts": time.time(), **event}
        buf = self._events[run_id]
        buf.append(event)
        del buf[: -self.history]
        for q in list(self._subs[run_id]):
            q.put_nowait(event)

    async def subscribe(self, run_id: str) -> AsyncIterator[dict]:
        q: asyncio.Queue = asyncio.Queue()
        self._subs[run_id].add(q)
        try:
            for ev in list(self._events[run_id]):
                yield ev
            while True:
                yield await q.get()
        finally:
            self._subs[run_id].discard(q)

    async def close(self) -> None:
        pass


class RedisEventBus:
    """多 worker 部署用：事件写入 Redis List（历史）并通过 Pub/Sub 广播。"""

    def __init__(self, url: str, history: int = 2000):
        import redis.asyncio as redis

        self.redis = redis.from_url(url, decode_responses=True)
        self.history = history

    @staticmethod
    def _keys(run_id: str) -> tuple[str, str]:
        return f"sw:events:{run_id}", f"sw:chan:{run_id}"

    async def publish(self, run_id: str, event: dict) -> None:
        key, chan = self._keys(run_id)
        payload = json.dumps({"ts": time.time(), **event}, ensure_ascii=False)
        pipe = self.redis.pipeline()
        pipe.rpush(key, payload)
        pipe.ltrim(key, -self.history, -1)
        pipe.expire(key, 7 * 24 * 3600)
        pipe.publish(chan, payload)
        await pipe.execute()

    async def subscribe(self, run_id: str) -> AsyncIterator[dict]:
        key, chan = self._keys(run_id)
        pubsub = self.redis.pubsub()
        await pubsub.subscribe(chan)
        try:
            # 先订阅再读历史，避免两者之间的事件丢失；用时间戳去掉重复项
            last_ts = 0.0
            for raw in await self.redis.lrange(key, 0, -1):
                ev = json.loads(raw)
                last_ts = max(last_ts, ev.get("ts", 0.0))
                yield ev
            async for msg in pubsub.listen():
                if msg.get("type") != "message":
                    continue
                ev = json.loads(msg["data"])
                if ev.get("ts", 0.0) <= last_ts:
                    continue
                yield ev
        finally:
            await pubsub.unsubscribe(chan)
            await pubsub.aclose()

    async def close(self) -> None:
        await self.redis.aclose()


def build_event_bus(redis_url: str | None):
    return RedisEventBus(redis_url) if redis_url else MemoryEventBus()


# ---------------------------------------------------------------------------
# 运行管理
# ---------------------------------------------------------------------------


class RunNotFound(KeyError):
    pass


class RunConflict(RuntimeError):
    pass


class RunManager:
    def __init__(self, graph, bus, llm=None):
        self.graph = graph
        self.bus = bus
        self.llm = llm
        self._tasks: dict[str, asyncio.Task] = {}
        self._errors: dict[str, str] = {}
        self._index: dict[str, dict] = {}

    # ---- 生命周期 ----

    async def start(self, *, raw_ch1_3: str, title: str = "", settings: dict | None = None) -> str:
        if not raw_ch1_3.strip():
            raise ValueError("原始 Ch1-3 不能为空")
        pipeline_settings = PipelineSettings.from_dict(settings)
        run_id = uuid.uuid4().hex[:12]
        self._index[run_id] = {"run_id": run_id, "title": title, "created_at": time.time()}
        initial = {
            "run_id": run_id,
            "title": title,
            "raw_ch1_3": raw_ch1_3,
            "settings": pipeline_settings.to_dict(),
            "stage": "extract",
            "errors": [],
        }
        self._spawn(run_id, initial)
        return run_id

    async def select(self, run_id: str, selection: dict) -> None:
        snap = await self._snapshot(run_id)
        if self.is_running(run_id):
            raise RunConflict("运行仍在进行中")
        if not snap.interrupts:
            raise RunConflict("当前不在人工定标断点")
        parsed = HumanSelection.model_validate(selection)
        if parsed.winning_branch not in snap.values.get("candidates", {}):
            raise ValueError(f"分支 {parsed.winning_branch} 不可选")
        await self.bus.publish(run_id, {"event": "selected", "winning_branch": parsed.winning_branch})
        self._spawn(run_id, Command(resume=parsed.model_dump()))

    async def resume(self, run_id: str) -> None:
        """从最近一次 checkpoint 继续（用于进程重启或节点报错后的断点续跑）。"""
        snap = await self._snapshot(run_id)
        if self.is_running(run_id):
            raise RunConflict("运行仍在进行中")
        if snap.interrupts:
            raise RunConflict("等待人工定标，请调用 selection 接口")
        if not snap.next:
            raise RunConflict("运行已完成")
        self._errors.pop(run_id, None)
        self._spawn(run_id, None)

    def is_running(self, run_id: str) -> bool:
        task = self._tasks.get(run_id)
        return bool(task and not task.done())

    def _spawn(self, run_id: str, payload: Any) -> None:
        self._tasks[run_id] = asyncio.create_task(self._drive(run_id, payload), name=f"run-{run_id}")

    async def _drive(self, run_id: str, payload: Any) -> None:
        config = run_config(run_id)
        try:
            async for mode, chunk in self.graph.astream(payload, config, stream_mode=["updates", "custom"]):
                if mode == "custom":
                    await self.bus.publish(run_id, chunk)
                elif mode == "updates":
                    for node, update in chunk.items():
                        if node == "__interrupt__":
                            await self.bus.publish(
                                run_id, {"event": "interrupt", "payload": [i.value for i in update]}
                            )
                        else:
                            await self.bus.publish(run_id, {"event": "node_done", "node": node})
            snap = await self.graph.aget_state(config)
            if not snap.next:
                await self.bus.publish(run_id, {"event": "finished"})
        except Exception as exc:  # 节点失败：checkpoint 保留，可调用 resume 断点续跑
            log.exception("run %s failed", run_id)
            self._errors[run_id] = repr(exc)
            await self.bus.publish(run_id, {"event": "error", "error": repr(exc)})

    async def shutdown(self) -> None:
        for task in self._tasks.values():
            task.cancel()
        await asyncio.gather(*self._tasks.values(), return_exceptions=True)

    # ---- 查询 ----

    async def _snapshot(self, run_id: str):
        snap = await self.graph.aget_state(run_config(run_id))
        if not snap.values:
            raise RunNotFound(run_id)
        return snap

    async def status(self, run_id: str) -> dict:
        snap = await self._snapshot(run_id)
        v = snap.values
        if self.is_running(run_id):
            status = "running"
        elif snap.interrupts:
            status = "awaiting_selection"
        elif not snap.next:
            status = "completed"
        elif run_id in self._errors:
            status = "failed"
        else:
            status = "paused"
        settings = PipelineSettings.from_dict(v.get("settings"))
        written = len(v.get("chapters_text", {})) if v.get("winning_branch") else 0
        return {
            "run_id": run_id,
            "title": v.get("title", ""),
            "status": status,
            "stage": v.get("stage"),
            "next": list(snap.next),
            "error": self._errors.get(run_id),
            "errors": v.get("errors", []),
            "winning_branch": v.get("winning_branch"),
            "progress": {
                "chapters_written": written,
                "total_chapters": settings.total_chapters,
                "arcs_planned": len(v.get("outline_arcs", [])),
                "total_arcs": settings.n_arcs,
            },
            "interrupt": [i.value for i in snap.interrupts] if snap.interrupts else None,
            "usage": self.llm.ledger.summary(run_id) if self.llm else None,
        }

    async def values(self, run_id: str) -> dict:
        return (await self._snapshot(run_id)).values

    def list_runs(self) -> list[dict]:
        return sorted(self._index.values(), key=lambda r: r["created_at"], reverse=True)
