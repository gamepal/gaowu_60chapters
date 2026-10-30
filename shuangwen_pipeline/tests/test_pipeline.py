import json

import pytest
from langgraph.types import Command

from shuangwen.config import AppSettings, default_routes
from shuangwen.graph import build_graph, open_checkpointer, run_config
from shuangwen.llm import LLMClient
from shuangwen.nodes import Deps
from conftest import SpyBackend

SHORT = {"total_chapters": 24, "arc_size": 12}


def initial(run_id="r1", settings=SHORT):
    return {"run_id": run_id, "title": "测试书", "raw_ch1_3": "原稿独有标记XYZ", "settings": settings, "errors": []}


async def run_until_interrupt(graph, run_id="r1", settings=SHORT):
    cfg = run_config(run_id)
    async for _ in graph.astream(initial(run_id, settings), cfg):
        pass
    return await graph.aget_state(cfg)


async def test_full_pipeline_with_human_selection(spy, llm, tmp_path):
    graph = build_graph(Deps(llm=llm, output_dir=str(tmp_path)))
    snap = await run_until_interrupt(graph)
    assert snap.next == ("select",)
    value = snap.interrupts[0].value
    assert value["scores"] == {"2A": 78, "2B": 96, "2C": 93}
    assert set(snap.values["candidates"]) == {"2A", "2B", "2C"}
    assert set(snap.values["candidates"]["2C"]["chapters"]) == {"1", "2", "3"}
    assert snap.values["candidates"]["2C"]["story_card"].startswith("主角")

    cfg = run_config("r1")
    async for _ in graph.astream(Command(resume={"winning_branch": "2C", "notes": "加个马屁精", "override_chapters": {"1": "人工改过的第一章"}}), cfg):
        pass
    v = (await graph.aget_state(cfg)).values
    assert v["stage"] == "completed"
    assert sorted(map(int, v["chapters_text"])) == list(range(1, 25))
    assert v["chapters_text"]["1"] == "人工改过的第一章"
    assert len(v["outline_arcs"]) == 2 and len(v["full_outlines"]) == 24
    assert v["global_state_card"]["current_chapter"] == 24
    assert len(v["global_state_card"]["used_tropes_blacklist"]) == 15
    assert v["chapter_reports"]["4"]["expanded"] is True
    assert "高密嘴炮对白草稿" in v["chapter_reports"]["10"]["slices_used"]
    assert "亲密张力切片草稿" in v["chapter_reports"]["14"]["slices_used"]

    # 人工批注传递到节拍器；2C 胜出时用它自己的人设卡
    planner_user = spy.messages["plan_arc"][0]["messages"][1]["content"]
    assert "加个马屁精" in planner_user and "一心想亏钱" in planner_user
    # 主笔 system 前缀带缓存标记，且包含锚点与全书细纲
    writer_call = spy.messages["write_chapter"][0]
    sys_block = writer_call["messages"][0]["content"][0]
    assert sys_block["cache_control"]["type"] == "ephemeral"
    assert "语感锚点" in sys_block["text"] and "第24章" in sys_block["text"]
    # 所有章节的 system 前缀完全一致（缓存命中前提）
    assert len({c["messages"][0]["content"][0]["text"] for c in spy.messages["write_chapter"]}) == 1
    # 防越界锁 + 上一章尾部滑窗
    user = writer_call["messages"][1]["content"]
    assert "防越界死命令" in user and "第5章" in user and "人工改过的第一章" not in user
    # 路由到正确模型
    assert spy.messages["banter_slice"][0]["route"].model.startswith("openai/gpt-4o")
    assert spy.messages["intimate_slice"][0]["route"].model.startswith("xai/grok")
    assert spy.messages["state_update"][0]["route"].model.endswith("gemini-2.5-flash")

    out = tmp_path / "r1"
    assert (out / "book.md").exists() and len(list((out / "chapters").glob("*.md"))) == 24
    assert json.loads((out / "outline.json").read_text())[1]["chapters"][0]["chapter_num"] == 13


async def test_branch_isolation(spy, llm):
    graph = build_graph(Deps(llm=llm))
    await run_until_interrupt(graph)
    as_text = lambda task: json.dumps(spy.messages[task][0]["messages"], ensure_ascii=False)
    assert "原稿独有标记XYZ" in as_text("skeleton_2A")
    assert "original_event_chain" in as_text("skeleton_2A")
    # 2B 物理屏蔽原事件链与原文
    assert "原稿独有标记XYZ" not in as_text("skeleton_2B")
    assert "original_event_chain" not in as_text("skeleton_2B") and "内部看剧本" not in as_text("skeleton_2B")
    assert "夏燃" in as_text("skeleton_2B")
    # 2C 只拿到题材种子
    c = as_text("prose_2C")
    assert "文抄公" in c and "夏燃" not in c and "原稿独有标记XYZ" not in c
    assert spy.messages["prose_2C"][0]["route"].temperature == 0.9
    assert spy.messages["judge"][0]["route"].temperature == 0.1


async def test_failed_branch_and_slice_do_not_block():
    spy = SpyBackend(fail_tasks={"prose_2A", "intimate_slice"})
    llm = LLMClient(spy, default_routes())
    graph = build_graph(Deps(llm=llm))
    snap = await run_until_interrupt(graph)
    assert set(snap.values["candidates"]) == {"2B", "2C"}
    assert any("2A" in e for e in snap.values["errors"])
    assert [e["branch_id"] for e in snap.values["judge_report"]["evaluations"]] == ["2B_Reconstructed", "2C_Radical"]
    cfg = run_config("r1")
    async for _ in graph.astream(Command(resume={"winning_branch": "2B"}), cfg):
        pass
    v = (await graph.aget_state(cfg)).values
    assert v["stage"] == "completed"
    assert v["chapter_reports"]["14"]["slice_errors"] and v["chapter_reports"]["14"]["slices_used"] == []


async def test_invalid_selection_raises(llm):
    graph = build_graph(Deps(llm=llm))
    await run_until_interrupt(graph)
    with pytest.raises(Exception):
        async for _ in graph.astream(Command(resume={"winning_branch": "2Z"}), run_config("r1")):
            pass


async def test_guardrail_rewrites_writer_output():
    spy = SpyBackend(overrides={"write_chapter": lambda meta: ("他耸了耸肩。\n" + "主角一巴掌拍桌上，反派当场破防。\n" * 200)})
    llm = LLMClient(spy, default_routes())
    graph = build_graph(Deps(llm=llm))
    await run_until_interrupt(graph)
    async for _ in graph.astream(Command(resume={"winning_branch": "2B"}), run_config("r1")):
        pass
    v = (await graph.aget_state(run_config("r1"))).values
    assert "耸了耸肩" not in v["chapters_text"]["5"]
    assert v["chapter_reports"]["5"]["guardrail_rounds"] == 1


async def test_sqlite_checkpoint_resume_after_crash(tmp_path):
    settings = AppSettings(sqlite_path=str(tmp_path / "cp.sqlite"))
    calls = {"n": 0}

    def flaky(meta):
        calls["n"] += 1
        if meta.get("chapter") == 6 and calls["n"] < 100:
            calls["n"] = 100
            raise RuntimeError("网络抖动")
        from shuangwen.mock import _prose
        return _prose(3200, meta.get("chapter", 0))

    class Flaky(SpyBackend):
        async def complete(self, *, task, route, messages, schema, meta):
            if task == "write_chapter":
                from shuangwen.llm import Completion
                return Completion(text=flaky(meta))
            return await super().complete(task=task, route=route, messages=messages, schema=schema, meta=meta)

    async with open_checkpointer(settings) as saver:
        graph = build_graph(Deps(llm=LLMClient(Flaky(), default_routes())), saver)
        await run_until_interrupt(graph)
        with pytest.raises(RuntimeError):
            async for _ in graph.astream(Command(resume={"winning_branch": "2B"}), run_config("r1")):
                pass

    # 新进程：从同一个 SQLite 断点续跑，已完成的章节不重写
    async with open_checkpointer(settings) as saver:
        spy = Flaky()
        graph = build_graph(Deps(llm=LLMClient(spy, default_routes())), saver)
        snap = await graph.aget_state(run_config("r1"))
        assert snap.next == ("write_chapter",) and snap.values["current_chapter_num"] == 6
        async for _ in graph.astream(None, run_config("r1")):
            pass
        v = (await graph.aget_state(run_config("r1"))).values
        assert v["stage"] == "completed" and len(v["chapters_text"]) == 24
        assert "extract" not in spy.calls and "plan_arc" not in spy.calls
