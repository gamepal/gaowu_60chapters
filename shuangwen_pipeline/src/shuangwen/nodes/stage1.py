"""STAGE 1：语义剥离（Node 1）与三路并发赛马（Node 2A/2B/2C）。"""

from __future__ import annotations

import asyncio

from ..config import TEMP_EXTRACT, TEMP_RADICAL_2C, TEMP_SKELETON_2A, TEMP_SKELETON_2B, PipelineSettings, Role
from ..guardrails import describe_hits, enforce, split_chapters
from ..prompts import (
    CHAPTER_FORMAT_RULE,
    PROMPT_NODE_1_EXTRACTOR,
    PROMPT_NODE_2_PROSE,
    PROMPT_NODE_2A_SKELETON,
    PROMPT_NODE_2B_RECONSTRUCT,
    PROMPT_NODE_2C_RADICAL,
    PROMPT_STYLE_BIBLE_COLLOQUIAL,
    dumps,
)
from ..schemas import BRANCH_LABELS, BranchCandidate, BranchSkeleton, StoryAssetsSchema
from . import Deps, emit, meta

# ---------------------------------------------------------------------------
# Node 1
# ---------------------------------------------------------------------------


async def node_1_extract(state: dict, deps: Deps) -> dict:
    emit("stage", stage="extract", message="Node 1：语义剥离与憋屈度药检")
    assets = await deps.llm.structured(
        Role.ARCHITECT,
        [
            {"role": "system", "content": PROMPT_NODE_1_EXTRACTOR},
            {"role": "user", "content": f"【原始Ch1-3样章】\n{state['raw_ch1_3']}"},
        ],
        StoryAssetsSchema,
        task="extract",
        temperature=TEMP_EXTRACT,
        meta=meta(state),
    )
    emit("extracted", assets=assets.model_dump())
    return {"extracted_assets": assets.model_dump(), "stage": "race"}


# ---------------------------------------------------------------------------
# Node 2：三路赛马（权限隔离并发）
# ---------------------------------------------------------------------------


def _skeleton_text(skeleton: BranchSkeleton) -> str:
    lines = [f"【60章主线三幕高潮预览】\n{skeleton.mainline_preview}\n"]
    for ch in skeleton.chapters:
        lines.append(f"第{ch.chapter_num}章《{ch.title}》")
        lines.extend(f"  - 场景{i + 1}：{s}" for i, s in enumerate(ch.scenes))
        lines.append(f"  - 章末钩子：{ch.chapter_hook}")
    return "\n".join(lines)


async def _prose_from_skeleton(deps: Deps, state: dict, branch: str, skeleton: BranchSkeleton) -> BranchCandidate:
    prose = await deps.llm.text(
        Role.WRITER,
        [
            {"role": "system", "content": PROMPT_NODE_2_PROSE + "\n" + PROMPT_STYLE_BIBLE_COLLOQUIAL + "\n" + CHAPTER_FORMAT_RULE},
            {"role": "user", "content": f"请按以下分场骨架扩写为极致大白话搞笑爽文Ch1-3正文：\n{_skeleton_text(skeleton)}"},
        ],
        task=f"prose_{branch}",
        meta=meta(state, branch=branch),
    )
    _, chapters, titles = split_chapters(prose)
    for ch in skeleton.chapters:
        titles.setdefault(str(ch.chapter_num), ch.title)
    return BranchCandidate(
        branch=branch,
        label=BRANCH_LABELS[branch],
        mainline_preview=skeleton.mainline_preview,
        skeleton=skeleton,
        chapters=chapters,
        titles=titles,
    )


async def run_branch_2a(deps: Deps, state: dict, assets: StoryAssetsSchema) -> BranchCandidate:
    """策略1：保核改写（传入完整资产 + 原文，Opus 改结构 → Gemini 洗大白话）。"""
    skeleton = await deps.llm.structured(
        Role.ARCHITECT,
        [
            {"role": "system", "content": PROMPT_NODE_2A_SKELETON},
            {"role": "user", "content": f"资产诊断：{assets.model_dump_json()}\n原稿：\n{state['raw_ch1_3']}"},
        ],
        BranchSkeleton,
        task="skeleton_2A",
        temperature=TEMP_SKELETON_2A,
        meta=meta(state, branch="2A"),
    )
    return await _prose_from_skeleton(deps, state, "2A", skeleton)


async def run_branch_2b(deps: Deps, state: dict, assets: StoryAssetsSchema) -> BranchCandidate:
    """策略2：保值重建（物理屏蔽 original_event_chain 与原文，防止被原慢热剧情污染）。"""
    filtered = assets.model_dump(exclude={"original_event_chain"})
    skeleton = await deps.llm.structured(
        Role.ARCHITECT,
        [
            {"role": "system", "content": PROMPT_NODE_2B_RECONSTRUCT},
            {"role": "user", "content": f"保留以下核心价值资产，彻底重建高烈度冲突开局：\n{dumps(filtered)}"},
        ],
        BranchSkeleton,
        task="skeleton_2B",
        temperature=TEMP_SKELETON_2B,
        meta=meta(state, branch="2B"),
    )
    return await _prose_from_skeleton(deps, state, "2B", skeleton)


async def run_branch_2c(deps: Deps, state: dict, assets: StoryAssetsSchema) -> BranchCandidate:
    """策略3：种子重创（仅传 genre_seed，Gemini 直接放飞自我）。"""
    raw = await deps.llm.text(
        Role.WRITER,
        [
            {"role": "system", "content": PROMPT_NODE_2C_RADICAL + "\n" + PROMPT_STYLE_BIBLE_COLLOQUIAL + "\n" + CHAPTER_FORMAT_RULE},
            {"role": "user", "content": f"题材种子：{assets.genre_seed.model_dump_json()}"},
        ],
        task="prose_2C",
        temperature=TEMP_RADICAL_2C,
        meta=meta(state, branch="2C"),
    )
    preamble, chapters, titles = split_chapters(raw)
    story_card, preview = preamble, ""
    if "【60章主线三幕高潮预览】" in preamble:
        story_card, preview = preamble.split("【60章主线三幕高潮预览】", 1)
    story_card = story_card.replace("【新故事人设卡】", "").strip()
    return BranchCandidate(
        branch="2C",
        label=BRANCH_LABELS["2C"],
        story_card=story_card,
        mainline_preview=preview.strip(),
        chapters=chapters,
        titles=titles,
    )


async def _finalize_candidate(deps: Deps, state: dict, cand: BranchCandidate) -> BranchCandidate:
    """全策略中文去翻译腔终审：逐章过正则护栏，命中则局部重写。"""
    settings = PipelineSettings.from_dict(state.get("settings"))
    residual: list[str] = []
    for key in sorted(cand.chapters, key=int):
        fixed, _, hits = await enforce(
            deps.llm,
            cand.chapters[key],
            max_rounds=settings.max_guardrail_rewrites,
            task="local_rewrite",
            meta=meta(state, branch=cand.branch, chapter=int(key)),
        )
        cand.chapters[key] = fixed
        residual += [f"第{key}章 {d}" for d in describe_hits(hits)]
    cand.guardrail_hits = residual
    expected = {str(i) for i in range(1, settings.golden_chapters + 1)}
    missing = expected - set(cand.chapters)
    if missing:
        cand.guardrail_hits.append(f"缺少章节：{','.join(sorted(missing, key=int))}")
    return cand


async def node_2_parallel_race(state: dict, deps: Deps) -> dict:
    emit("stage", stage="race", message="Node 2：三路赛马并发生成")
    assets = StoryAssetsSchema.model_validate(state["extracted_assets"])

    async def run(branch: str, fn) -> BranchCandidate:
        emit("branch_started", branch=branch)
        cand = await _finalize_candidate(deps, state, await fn(deps, state, assets))
        emit("branch_done", branch=branch, chars=sum(len(c) for c in cand.chapters.values()))
        return cand

    # 三路并发执行，耗时取决于最慢的单路
    results = await asyncio.gather(
        run("2A", run_branch_2a),
        run("2B", run_branch_2b),
        run("2C", run_branch_2c),
        return_exceptions=True,
    )
    candidates: dict[str, dict] = {}
    errors: list[str] = []  # errors 通道是追加型 reducer，只返回新增条目
    for branch, res in zip(("2A", "2B", "2C"), results):
        if isinstance(res, BaseException):
            errors.append(f"分支 {branch} 生成失败：{res!r}")
            emit("branch_failed", branch=branch, error=repr(res))
        else:
            candidates[branch] = res.model_dump()
    if not candidates:
        raise RuntimeError("三路赛马全部失败：" + "；".join(errors[-3:]))
    return {"candidates": candidates, "errors": errors, "stage": "judge"}
