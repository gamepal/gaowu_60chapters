"""STAGE 3：60章五幕节拍器（Node 4）与 Ch4-60 滚动连载引擎（Node 5）。"""

from __future__ import annotations

import asyncio

from ..config import TEMP_BEAT_PLANNER, PipelineSettings, Role, arc_theme
from ..guardrails import count_cjk, describe_hits, enforce, strip_leading_heading
from ..prompts import (
    BANTER_SLICE_PROMPT,
    EXPAND_PROMPT,
    INTIMATE_SLICE_PROMPT,
    PROMPT_NODE_4_BEAT_PLANNER,
    PROMPT_NODE_5_WRITER_SYSTEM,
    PROMPT_STYLE_BIBLE_COLLOQUIAL,
    STATE_UPDATE_PROMPT,
    build_arc_plan_text,
    build_writer_user_prompt,
    dumps,
)
from ..schemas import (
    ArcOutline,
    BranchCandidate,
    ChapterBeat,
    ChapterReport,
    ChapterStateUpdate,
    GlobalStateCard,
    StoryAssetsSchema,
)
from . import Deps, emit, meta
from .stage2 import _golden_text

# ---------------------------------------------------------------------------
# 共享上下文
# ---------------------------------------------------------------------------


def _character_bible(state: dict) -> str:
    """胜出方案的人物设定。2C 另创了新人物，因此用它自己的人设卡。"""
    winner = BranchCandidate.model_validate(state["candidates"][state["winning_branch"]])
    if winner.branch == "2C" and winner.story_card:
        return winner.story_card
    assets = StoryAssetsSchema.model_validate(state["extracted_assets"])
    return dumps(assets.story_value_assets.model_dump())


def _mainline_preview(state: dict) -> str:
    return state["candidates"][state["winning_branch"]].get("mainline_preview", "")


def _themes(settings: PipelineSettings) -> list[str]:
    return [arc_theme(i, settings.n_arcs) for i in range(settings.n_arcs)]


# ---------------------------------------------------------------------------
# Node 4：分批生成 Mini-Arc 细纲
# ---------------------------------------------------------------------------


async def node_4_plan_arc(state: dict, deps: Deps) -> dict:
    settings = PipelineSettings.from_dict(state.get("settings"))
    arcs = list(state.get("outline_arcs", []))
    idx = len(arcs)
    start = idx * settings.arc_size + 1
    end = start + settings.arc_size - 1
    theme = _themes(settings)[idx]
    emit("stage", stage="plan", message=f"Node 4：第{idx + 1}/{settings.n_arcs}卷细纲（Ch{start}-{end}）")

    planned = [
        f"第{b['chapter_num']}章《{b['title']}》冲突：{b['core_conflict']}｜兑现：{b['payoff_and_hook']}"
        for b in state.get("full_outlines", [])
    ]
    notes = state.get("selection", {}).get("notes", "")
    user = "\n\n".join(
        x
        for x in [
            f"【主线预览】\n{_mainline_preview(state)}",
            f"【人物设定】\n{_character_bible(state)}",
            f"【胜出的黄金三章正文】\n{_golden_text(state, settings)}",
            f"【当前全局状态卡】\n{dumps(state['global_state_card'])}",
            "【已规划的前文细纲（必须严丝合缝衔接，不得重复已用桥段）】\n" + "\n".join(planned) if planned else "",
            f"【人工主编批注（最高优先级）】\n{notes}" if notes else "",
            (
                f"注意：第1-{settings.golden_chapters}章正文已定稿，这几章的细纲请如实概括已写内容，不要改剧情。"
                if start <= settings.golden_chapters
                else ""
            ),
        ]
        if x
    )
    system = PROMPT_NODE_4_BEAT_PLANNER.format(
        arc_size=settings.arc_size,
        arc_plan=build_arc_plan_text(_themes(settings), settings.arc_size),
        arc_no=idx + 1,
        start=start,
        end=end,
        count=settings.arc_size,
    )
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]

    arc: ArcOutline | None = None
    for attempt in range(3):
        arc = await deps.llm.structured(
            Role.ARCHITECT,
            messages,
            ArcOutline,
            task="plan_arc",
            temperature=TEMP_BEAT_PLANNER,
            meta=meta(state, arc_index=idx, start=start, end=end, attempt=attempt),
        )
        if len(arc.chapters) == settings.arc_size:
            break
        messages = messages + [
            {"role": "assistant", "content": arc.model_dump_json()},
            {
                "role": "user",
                "content": f"chapters 只有 {len(arc.chapters)} 条，必须恰好 {settings.arc_size} 条（第{start}-{end}章）。请重新输出完整 JSON。",
            },
        ]
    assert arc is not None
    if len(arc.chapters) != settings.arc_size:
        raise RuntimeError(f"第{idx + 1}卷细纲章节数不正确：{len(arc.chapters)}")

    # 强制章号连续，防止模型编号漂移
    for offset, beat in enumerate(arc.chapters):
        beat.chapter_num = start + offset
    arc.arc_index = idx
    arc.arc_theme = theme

    outlines = list(state.get("full_outlines", [])) + [b.model_dump() for b in arc.chapters]
    titles = dict(state.get("chapter_titles", {}))
    for b in arc.chapters:
        if b.chapter_num > settings.golden_chapters:
            titles[str(b.chapter_num)] = b.title
    emit("arc_planned", arc_index=idx, chapters=[b.model_dump() for b in arc.chapters])
    done = len(arcs) + 1 == settings.n_arcs
    return {
        "outline_arcs": arcs + [arc.model_dump()],
        "full_outlines": outlines,
        "chapter_titles": titles,
        "current_chapter_num": settings.golden_chapters + 1,
        "stage": "write" if done else "plan",
    }


def route_after_plan(state: dict) -> str:
    settings = PipelineSettings.from_dict(state.get("settings"))
    return "plan_arc" if len(state.get("outline_arcs", [])) < settings.n_arcs else "write_chapter"


# ---------------------------------------------------------------------------
# Node 5：多模型切片路由与统稿连载引擎
# ---------------------------------------------------------------------------


def build_cached_bundle(state: dict, settings: PipelineSettings) -> str:
    """Stage 3 期间恒定不变的设定包 → 作为 system 前缀注册上下文缓存。

    文风圣经 + 语感锚点 + 人物设定 + 胜出Ch1-3全文 + 全书细纲。
    """
    anchors = "\n\n".join(f"〔锚点{i + 1}〕\n{a}" for i, a in enumerate(state.get("style_anchors", [])))
    outline = "\n".join(
        f"第{b['chapter_num']}章《{b['title']}》｜冲突：{b['core_conflict']}｜操作：{b['comic_shuang_action']}｜兑现：{b['payoff_and_hook']}"
        for b in state["full_outlines"]
    )
    return "\n\n".join(
        [
            PROMPT_NODE_5_WRITER_SYSTEM,
            PROMPT_STYLE_BIBLE_COLLOQUIAL,
            f"# 语感锚点（Few-Shot：照这个腔调写）\n{anchors}",
            f"# 人物设定\n{_character_bible(state)}",
            f"# 主线预览\n{_mainline_preview(state)}",
            f"# 黄金三章原文\n{_golden_text(state, settings)}",
            f"# 全书{settings.total_chapters}章细纲\n{outline}",
        ]
    )


async def _sub_slices(deps: Deps, state: dict, beat: ChapterBeat, characters: str) -> tuple[dict[str, str], list[str]]:
    jobs: dict[str, asyncio.Future] = {}
    n = beat.chapter_num
    if "dense_banter" in beat.scene_tags:
        jobs["高密嘴炮对白草稿"] = deps.llm.text(
            Role.BANTER,
            [{"role": "user", "content": BANTER_SLICE_PROMPT.format(characters=characters, **beat.model_dump())}],
            task="banter_slice",
            meta=meta(state, chapter=n),
        )
    if "intimate_tension" in beat.scene_tags:
        jobs["亲密张力切片草稿"] = deps.llm.text(
            Role.INTIMATE,
            [{"role": "user", "content": INTIMATE_SLICE_PROMPT.format(characters=characters, **beat.model_dump())}],
            task="intimate_slice",
            meta=meta(state, chapter=n),
        )
    if not jobs:
        return {}, []
    results = await asyncio.gather(*jobs.values(), return_exceptions=True)
    slices: dict[str, str] = {}
    errors: list[str] = []
    for name, res in zip(jobs, results):
        # 切片模型失败不阻塞主线：主笔会在没有素材的情况下自行完成
        if isinstance(res, BaseException):
            errors.append(f"{name}：{res!r}")
        elif res.strip():
            slices[name] = res.strip()
    return slices, errors


async def node_5_rolling_chapter_writer(state: dict, deps: Deps) -> dict:
    settings = PipelineSettings.from_dict(state.get("settings"))
    n = state["current_chapter_num"]
    beats = {b["chapter_num"]: b for b in state["full_outlines"]}
    beat = ChapterBeat.model_validate(beats[n])
    prev_beat = beats.get(n - 1)
    next_beat = beats.get(n + 1)
    card = GlobalStateCard.model_validate(state["global_state_card"])
    prev_text = state["chapters_text"].get(str(n - 1), "")
    tail_text = prev_text[-settings.tail_window_chars :]
    emit("chapter_started", chapter=n, title=beat.title, tags=beat.scene_tags)

    # 1. 动态切片路由
    slices, slice_errors = await _sub_slices(deps, state, beat, _character_bible(state))
    for err in slice_errors:
        emit("slice_failed", chapter=n, error=err)

    # 2. 主笔统稿（system 前缀走上下文缓存）
    route = deps.llm.route(Role.WRITER)
    system = deps.llm.system_message(build_cached_bundle(state, settings), route=route, cache=True)
    user_prompt = build_writer_user_prompt(
        n=n,
        state_card_json=card.model_dump_json(),
        blacklist=card.used_tropes_blacklist,
        tail_text=tail_text,
        prev_beat=prev_beat,
        beat=beat.model_dump(),
        next_beat=next_beat,
        sub_slices=slices,
        min_chars=settings.min_chars,
        max_chars=settings.max_chars,
    )
    messages = [system, {"role": "user", "content": user_prompt}]
    text = strip_leading_heading(await deps.llm.text(Role.WRITER, messages, task="write_chapter", meta=meta(state, chapter=n)))

    # 3. 字数滑动校准：不足下限时触发一次“细节放大扩写”
    expanded = False
    count = count_cjk(text)
    if count < settings.min_chars:
        emit("chapter_expanding", chapter=n, chars=count)
        expand_messages = messages + [
            {"role": "assistant", "content": text},
            {
                "role": "user",
                "content": EXPAND_PROMPT.format(count=count, min_chars=settings.min_chars, **beat.model_dump()),
            },
        ]
        longer = strip_leading_heading(
            await deps.llm.text(Role.WRITER, expand_messages, task="expand_chapter", meta=meta(state, chapter=n))
        )
        if count_cjk(longer) > count:
            text, expanded = longer, True

    # 4. 防翻译腔/防憋屈拦截器（局部重写）
    text, rounds, residual = await enforce(
        deps.llm,
        text,
        max_rounds=settings.max_guardrail_rewrites,
        meta=meta(state, chapter=n),
    )

    # 5. 后置轻量算子：更新状态卡 + 热梗黑名单
    update = await deps.llm.structured(
        Role.LIGHT,
        [
            {
                "role": "user",
                "content": STATE_UPDATE_PROMPT.format(
                    n=n, keep=settings.blacklist_size, state_card=card.model_dump_json(), chapter_text=text
                ),
            }
        ],
        ChapterStateUpdate,
        task="state_update",
        meta=meta(state, chapter=n),
    )
    new_card = update.state_card
    new_card.current_chapter = n
    new_card.used_tropes_blacklist = merge_blacklist(
        card.used_tropes_blacklist, update.new_tropes, settings.blacklist_size
    )

    report = ChapterReport(
        chapter_num=n,
        char_count=count_cjk(text),
        expanded=expanded,
        guardrail_rounds=rounds,
        residual_hits=describe_hits(residual),
        slices_used=list(slices),
        slice_errors=slice_errors,
    )
    emit("chapter_done", chapter=n, title=beat.title, report=report.model_dump())
    done = n >= settings.total_chapters
    return {
        "chapters_text": {**state["chapters_text"], str(n): text},
        "chapter_reports": {**state.get("chapter_reports", {}), str(n): report.model_dump()},
        "global_state_card": new_card.model_dump(),
        "current_chapter_num": n + 1,
        "stage": "finalize" if done else "write",
    }


def merge_blacklist(old: list[str], new: list[str], keep: int) -> list[str]:
    """合并去重，保留最近 keep 个（新梗在尾部）。"""
    merged: list[str] = []
    for item in [*old, *new]:
        item = item.strip()
        if not item:
            continue
        if item in merged:
            merged.remove(item)
        merged.append(item)
    return merged[-keep:]


def route_after_write(state: dict) -> str:
    settings = PipelineSettings.from_dict(state.get("settings"))
    return "write_chapter" if state["current_chapter_num"] <= settings.total_chapters else "finalize"


async def node_finalize(state: dict, deps: Deps) -> dict:
    exported = None
    if deps.output_dir:
        from ..export import export_run

        exported = str(export_run(state, deps.output_dir))
    emit("completed", output_dir=exported)
    return {"stage": "completed", "export_path": exported}
