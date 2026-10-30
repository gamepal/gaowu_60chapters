"""STAGE 2：量化评审（Node 3）、人工断点（HITL）与连载上下文初始化。"""

from __future__ import annotations

from langgraph.types import interrupt

from ..config import TEMP_JUDGE, PipelineSettings, Role
from ..prompts import PROMPT_INIT_CONTEXT, PROMPT_NODE_3_JUDGE
from ..schemas import BRANCH_FULL_NAMES, BranchCandidate, HumanSelection, InitialContext, JudgeReport
from . import Deps, emit, meta

_PLAN_NAMES = {"2A": "方案A（保核）", "2B": "方案B（重建）", "2C": "方案C（另创）"}


async def node_3_judge(state: dict, deps: Deps) -> dict:
    emit("stage", stage="judge", message="Node 3：毒舌裁判五维打分")
    blocks = []
    for code, raw in sorted(state["candidates"].items()):
        cand = BranchCandidate.model_validate(raw)
        blocks.append(f"==================== 【{_PLAN_NAMES[code]}】 branch_id={BRANCH_FULL_NAMES[code]} ====================\n{cand.full_text()}")
    report = await deps.llm.structured(
        Role.ARCHITECT,
        [
            {"role": "system", "content": PROMPT_NODE_3_JUDGE},
            {"role": "user", "content": "\n\n".join(blocks)},
        ],
        JudgeReport,
        task="judge",
        temperature=TEMP_JUDGE,
        meta=meta(state),
    )
    # 只保留真实存在的分支的评估
    report.evaluations = [e for e in report.evaluations if e.code in state["candidates"]]
    emit("judged", report=report.model_dump())
    return {"judge_report": report.model_dump(), "stage": "awaiting_selection"}


def node_wait_for_human_selection(state: dict) -> dict:
    """挂起工作流（checkpoint 已落库），等待人工钦定胜出分支。"""
    report = JudgeReport.model_validate(state["judge_report"])
    decision = interrupt(
        {
            "type": "select_branch",
            "available_branches": sorted(state["candidates"]),
            "scores": {e.code: e.total_score for e in report.evaluations},
            "recommended_branch": report.recommended_branch,
            "recommendation": report.recommendation,
        }
    )
    selection = HumanSelection.model_validate(decision)
    if selection.winning_branch not in state["candidates"]:
        raise ValueError(f"分支 {selection.winning_branch} 不存在或生成失败")
    winner = BranchCandidate.model_validate(state["candidates"][selection.winning_branch])
    chapters = dict(winner.chapters)
    chapters.update({str(k): v for k, v in selection.override_chapters.items()})
    return {
        "selection": selection.model_dump(),
        "winning_branch": selection.winning_branch,
        "chapters_text": chapters,
        "chapter_titles": dict(winner.titles),
        "stage": "init_context",
    }


async def node_init_context(state: dict, deps: Deps) -> dict:
    """用轻量模型从胜出的黄金三章抽取初始状态卡与 3 个语感锚点段落。"""
    emit("stage", stage="init_context", message="初始化全局状态卡与语感锚点")
    settings = PipelineSettings.from_dict(state.get("settings"))
    golden = _golden_text(state, settings)
    ctx = await deps.llm.structured(
        Role.LIGHT,
        [
            {"role": "system", "content": PROMPT_INIT_CONTEXT},
            {"role": "user", "content": golden},
        ],
        InitialContext,
        task="init_context",
        meta=meta(state),
    )
    card = ctx.state_card
    card.current_chapter = settings.golden_chapters
    card.used_tropes_blacklist = card.used_tropes_blacklist[-settings.blacklist_size :]
    anchors = [a for a in ctx.style_anchors if a.strip()][:3]
    # 裁判提取的胜出方案高光切片也作为语感锚点
    report = JudgeReport.model_validate(state["judge_report"])
    winner_eval = report.by_code().get(state["winning_branch"])
    if winner_eval and winner_eval.highlight_snippet and winner_eval.highlight_snippet not in anchors:
        anchors.append(winner_eval.highlight_snippet)
    return {
        "global_state_card": card.model_dump(),
        "style_anchors": anchors,
        "outline_arcs": [],
        "full_outlines": [],
        "stage": "plan",
    }


def _golden_text(state: dict, settings: PipelineSettings) -> str:
    titles = state.get("chapter_titles", {})
    parts = []
    for i in range(1, settings.golden_chapters + 1):
        key = str(i)
        parts.append(f"### 第{i}章 {titles.get(key, '')}".rstrip() + "\n" + state["chapters_text"].get(key, ""))
    return "\n\n".join(parts)
