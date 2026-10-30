"""LangGraph 编排：有状态图 + 人工断点 + 两个自循环（分卷细纲 / 滚动连载）。

    extract → race → judge → [interrupt] select → init_context
            → plan_arc ↺ (×n_arcs) → write_chapter ↺ (Ch4..60) → finalize → END
"""

from __future__ import annotations

import functools
import operator
from contextlib import asynccontextmanager
from typing import Annotated, Any, AsyncIterator, TypedDict

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

from .config import AppSettings
from .nodes import Deps
from .nodes.stage1 import node_1_extract, node_2_parallel_race
from .nodes.stage2 import node_3_judge, node_init_context, node_wait_for_human_selection
from .nodes.stage3 import (
    node_4_plan_arc,
    node_5_rolling_chapter_writer,
    node_finalize,
    route_after_plan,
    route_after_write,
)


class PipelineState(TypedDict, total=False):
    run_id: str
    title: str
    raw_ch1_3: str
    settings: dict
    stage: str
    extracted_assets: dict
    candidates: dict[str, dict]
    judge_report: dict
    selection: dict
    winning_branch: str
    style_anchors: list[str]
    outline_arcs: list[dict]
    full_outlines: list[dict]
    global_state_card: dict
    chapters_text: dict[str, str]
    chapter_titles: dict[str, str]
    chapter_reports: dict[str, dict]
    current_chapter_num: int
    export_path: str | None
    errors: Annotated[list[str], operator.add]


def _bind(fn, deps: Deps):
    @functools.wraps(fn)
    async def node(state: dict) -> dict:
        return await fn(state, deps)

    return node


def build_graph(deps: Deps, checkpointer: BaseCheckpointSaver | None = None):
    g = StateGraph(PipelineState)
    g.add_node("extract", _bind(node_1_extract, deps))
    g.add_node("race", _bind(node_2_parallel_race, deps))
    g.add_node("judge", _bind(node_3_judge, deps))
    g.add_node("select", node_wait_for_human_selection)
    g.add_node("init_context", _bind(node_init_context, deps))
    g.add_node("plan_arc", _bind(node_4_plan_arc, deps))
    g.add_node("write_chapter", _bind(node_5_rolling_chapter_writer, deps))
    g.add_node("finalize", _bind(node_finalize, deps))

    g.add_edge(START, "extract")
    g.add_edge("extract", "race")
    g.add_edge("race", "judge")
    g.add_edge("judge", "select")
    g.add_edge("select", "init_context")
    g.add_edge("init_context", "plan_arc")
    g.add_conditional_edges("plan_arc", route_after_plan, ["plan_arc", "write_chapter"])
    g.add_conditional_edges("write_chapter", route_after_write, ["write_chapter", "finalize"])
    g.add_edge("finalize", END)
    return g.compile(checkpointer=checkpointer or InMemorySaver())


def run_config(run_id: str) -> dict[str, Any]:
    # 每章 1 步 + 每卷 1 步 + 固定节点，留足余量
    return {"configurable": {"thread_id": run_id}, "recursion_limit": 1000}


@asynccontextmanager
async def open_checkpointer(settings: AppSettings) -> AsyncIterator[BaseCheckpointSaver]:
    """按配置选择 checkpoint 存储：Postgres > SQLite > 内存。"""
    if settings.postgres_dsn:
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

        async with AsyncPostgresSaver.from_conn_string(settings.postgres_dsn) as saver:
            await saver.setup()
            yield saver
    elif settings.sqlite_path:
        import os

        from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

        os.makedirs(os.path.dirname(os.path.abspath(settings.sqlite_path)), exist_ok=True)
        async with AsyncSqliteSaver.from_conn_string(settings.sqlite_path) as saver:
            yield saver
    else:
        yield InMemorySaver()
