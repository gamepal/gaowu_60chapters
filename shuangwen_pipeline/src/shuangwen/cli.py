"""命令行入口。

    shuangwen run --input ch1-3.md --title 书名 [--select auto|ask|2A|2B|2C] [--mock]
    shuangwen resume --run-id <id> --sqlite ./data/cp.sqlite [--select ...]
    shuangwen serve [--host 0.0.0.0 --port 8000] [--mock]
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import uuid
from pathlib import Path

from langgraph.types import Command

from .config import AppSettings, PipelineSettings
from .export import render_judge_report
from .graph import build_graph, open_checkpointer, run_config
from .llm import build_llm_client
from .nodes import Deps
from .schemas import normalize_branch


def _settings_from_args(args) -> AppSettings:
    settings = AppSettings.from_env()
    if getattr(args, "mock", False):
        settings.mock_llm = True
    if getattr(args, "sqlite", None):
        settings.sqlite_path = args.sqlite
    if getattr(args, "postgres", None):
        settings.postgres_dsn = args.postgres
    if getattr(args, "out", None):
        settings.output_dir = args.out
    return settings


def _print_event(chunk: dict) -> None:
    ev = chunk.get("event")
    if ev == "stage":
        print(f"\n▶ {chunk['message']}", flush=True)
    elif ev in {"branch_done", "branch_failed"}:
        print(f"  · {ev} {chunk.get('branch')} {chunk.get('chars') or chunk.get('error', '')}", flush=True)
    elif ev == "chapter_done":
        r = chunk["report"]
        extra = "（扩写）" if r["expanded"] else ""
        print(f"  · 第{chunk['chapter']}章《{chunk['title']}》{r['char_count']}字{extra}", flush=True)
    elif ev == "slice_failed":
        print(f"  ! 第{chunk['chapter']}章切片失败：{chunk['error']}", flush=True)
    elif ev == "completed":
        print(f"\n✔ 完成，输出目录：{chunk.get('output_dir')}", flush=True)


def _choose(interrupt_value: dict, mode: str) -> dict:
    recommended = normalize_branch(interrupt_value["recommended_branch"])
    if mode == "auto":
        return {"winning_branch": recommended}
    if mode != "ask":
        return {"winning_branch": normalize_branch(mode)}
    print(f"\n可选分支：{interrupt_value['available_branches']}  得分：{interrupt_value['scores']}")
    print(f"裁判推荐：{recommended}｜{interrupt_value['recommendation']}")
    choice = input(f"请钦定胜出分支 [{recommended}]：").strip() or recommended
    notes = input("（可选）给节拍器的主编批注：").strip()
    return {"winning_branch": normalize_branch(choice), "notes": notes}


async def _drive(graph, payload, run_id: str, select_mode: str) -> None:
    config = run_config(run_id)
    while True:
        async for mode, chunk in graph.astream(payload, config, stream_mode=["updates", "custom"]):
            if mode == "custom":
                _print_event(chunk)
        snap = await graph.aget_state(config)
        if not snap.interrupts:
            return
        print("\n" + render_judge_report(snap.values))
        payload = Command(resume=_choose(snap.interrupts[0].value, select_mode))


async def cmd_run(args) -> None:
    settings = _settings_from_args(args)
    raw = Path(args.input).read_text(encoding="utf-8")
    pipeline = PipelineSettings.from_dict({"total_chapters": args.chapters, "arc_size": args.arc_size})
    run_id = args.run_id or uuid.uuid4().hex[:12]
    llm = build_llm_client(settings)
    async with open_checkpointer(settings) as saver:
        graph = build_graph(Deps(llm=llm, output_dir=settings.output_dir), saver)
        print(f"run_id = {run_id}")
        initial = {
            "run_id": run_id,
            "title": args.title or Path(args.input).stem,
            "raw_ch1_3": raw,
            "settings": pipeline.to_dict(),
            "stage": "extract",
            "errors": [],
        }
        await _drive(graph, initial, run_id, args.select)
    print(f"\n用量：{llm.ledger.summary()}")


async def cmd_resume(args) -> None:
    settings = _settings_from_args(args)
    llm = build_llm_client(settings)
    async with open_checkpointer(settings) as saver:
        graph = build_graph(Deps(llm=llm, output_dir=settings.output_dir), saver)
        snap = await graph.aget_state(run_config(args.run_id))
        if not snap.values:
            sys.exit(f"找不到 run {args.run_id}（需要使用同一个持久化存储）")
        payload = None
        if snap.interrupts:
            print(render_judge_report(snap.values))
            payload = Command(resume=_choose(snap.interrupts[0].value, args.select))
        await _drive(graph, payload, args.run_id, args.select)


def cmd_serve(args) -> None:
    import uvicorn

    from .api import create_app

    uvicorn.run(create_app(_settings_from_args(args)), host=args.host, port=args.port)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="shuangwen", description="多智能体爽文生产流水线")
    parser.add_argument("-v", "--verbose", action="store_true")
    sub = parser.add_subparsers(dest="cmd", required=True)

    def common(p):
        p.add_argument("--mock", action="store_true", help="使用离线 Mock 模型（不消耗 API）")
        p.add_argument("--sqlite", help="SQLite checkpoint 路径（断点续跑必需）")
        p.add_argument("--postgres", help="Postgres DSN")
        p.add_argument("--out", help="输出目录（默认 ./output）")

    p_run = sub.add_parser("run", help="从原始 Ch1-3 跑完整流水线")
    p_run.add_argument("--input", required=True, help="原始 Ch1-3 文本文件")
    p_run.add_argument("--title", default="")
    p_run.add_argument("--run-id")
    p_run.add_argument("--chapters", type=int, default=60)
    p_run.add_argument("--arc-size", type=int, default=12)
    p_run.add_argument("--select", default="ask", help="ask（交互）/ auto（采纳裁判推荐）/ 2A / 2B / 2C")
    common(p_run)

    p_resume = sub.add_parser("resume", help="从 checkpoint 断点续跑")
    p_resume.add_argument("--run-id", required=True)
    p_resume.add_argument("--select", default="ask")
    common(p_resume)

    p_serve = sub.add_parser("serve", help="启动 FastAPI + Web Studio")
    p_serve.add_argument("--host", default="127.0.0.1")
    p_serve.add_argument("--port", type=int, default=8000)
    common(p_serve)

    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.WARNING)
    if args.cmd == "serve":
        cmd_serve(args)
    else:
        asyncio.run(cmd_run(args) if args.cmd == "run" else cmd_resume(args))


if __name__ == "__main__":
    main()
