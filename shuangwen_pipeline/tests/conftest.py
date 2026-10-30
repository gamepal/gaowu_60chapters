import pytest

from shuangwen.config import default_routes
from shuangwen.llm import LLMClient
from shuangwen.mock import MockBackend


class SpyBackend(MockBackend):
    """记录每次调用的完整 messages，用于断言权限隔离与 prompt 组装。"""

    def __init__(self, fail_tasks=(), overrides=None):
        super().__init__()
        self.fail_tasks = set(fail_tasks)
        self.overrides = overrides or {}
        self.messages: dict[str, list] = {}

    async def complete(self, *, task, route, messages, schema, meta):
        self.messages.setdefault(task, []).append({"route": route, "messages": messages, "meta": meta})
        if task in self.fail_tasks:
            raise RuntimeError(f"boom:{task}")
        if task in self.overrides:
            from shuangwen.llm import Completion

            out = self.overrides[task]
            return Completion(text=out(meta) if callable(out) else out)
        return await super().complete(task=task, route=route, messages=messages, schema=schema, meta=meta)


@pytest.fixture
def spy():
    return SpyBackend()


@pytest.fixture
def llm(spy):
    return LLMClient(spy, default_routes())
