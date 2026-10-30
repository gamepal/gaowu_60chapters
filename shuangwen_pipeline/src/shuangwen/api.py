"""FastAPI 服务：REST + SSE，供 Web Studio 提交原稿、审阅赛马看板、钦定胜出分支。"""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, PlainTextResponse, StreamingResponse
from pydantic import BaseModel, Field

from .config import AppSettings
from .export import render_book, render_judge_report
from .graph import build_graph, open_checkpointer
from .llm import build_llm_client
from .nodes import Deps
from .service import RunConflict, RunManager, RunNotFound, build_event_bus

STATIC_DIR = Path(__file__).parent / "static"


class CreateRunRequest(BaseModel):
    raw_ch1_3: str = Field(min_length=1, description="原始第1-3章正文")
    title: str = ""
    settings: dict = Field(default_factory=dict, description="PipelineSettings 覆盖项，如 total_chapters/arc_size")


class SelectionRequest(BaseModel):
    winning_branch: str
    notes: str = ""
    override_chapters: dict[str, str] = Field(default_factory=dict)


def create_app(settings: AppSettings | None = None) -> FastAPI:
    settings = settings or AppSettings.from_env()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        llm = build_llm_client(settings)
        bus = build_event_bus(settings.redis_url)
        async with open_checkpointer(settings) as saver:
            graph = build_graph(Deps(llm=llm, output_dir=settings.output_dir), saver)
            app.state.manager = RunManager(graph, bus, llm)
            yield
            await app.state.manager.shutdown()
            await bus.close()

    app = FastAPI(title="Shuangwen Production Pipeline", version="0.1.0", lifespan=lifespan)

    def manager() -> RunManager:
        return app.state.manager

    async def guard(coro):
        try:
            return await coro
        except RunNotFound:
            raise HTTPException(404, "run 不存在")
        except RunConflict as exc:
            raise HTTPException(409, str(exc))
        except ValueError as exc:
            raise HTTPException(422, str(exc))

    @app.get("/", response_class=HTMLResponse)
    async def studio():
        return (STATIC_DIR / "studio.html").read_text(encoding="utf-8")

    @app.get("/api/health")
    async def health():
        return {"ok": True, "mock_llm": settings.mock_llm, "models": {r.value: m.model for r, m in settings.routes.items()}}

    @app.get("/api/runs")
    async def list_runs():
        return manager().list_runs()

    @app.post("/api/runs", status_code=201)
    async def create_run(req: CreateRunRequest):
        run_id = await guard(manager().start(raw_ch1_3=req.raw_ch1_3, title=req.title, settings=req.settings))
        return {"run_id": run_id}

    @app.get("/api/runs/{run_id}")
    async def get_run(run_id: str):
        return await guard(manager().status(run_id))

    @app.get("/api/runs/{run_id}/board")
    async def race_board(run_id: str):
        """三路赛马看板：资产诊断 + 三份候选正文 + 裁判报告。"""
        v = await guard(manager().values(run_id))
        return {
            "assets": v.get("extracted_assets"),
            "candidates": v.get("candidates", {}),
            "judge_report": v.get("judge_report"),
            "winning_branch": v.get("winning_branch"),
        }

    @app.post("/api/runs/{run_id}/selection", status_code=202)
    async def select(run_id: str, req: SelectionRequest):
        await guard(manager().select(run_id, req.model_dump()))
        return {"ok": True}

    @app.post("/api/runs/{run_id}/resume", status_code=202)
    async def resume(run_id: str):
        await guard(manager().resume(run_id))
        return {"ok": True}

    @app.get("/api/runs/{run_id}/outline")
    async def outline(run_id: str):
        v = await guard(manager().values(run_id))
        return {"arcs": v.get("outline_arcs", []), "state_card": v.get("global_state_card")}

    @app.get("/api/runs/{run_id}/chapters")
    async def chapters(run_id: str):
        v = await guard(manager().values(run_id))
        titles = v.get("chapter_titles", {})
        reports = v.get("chapter_reports", {})
        return [
            {"chapter": int(k), "title": titles.get(k, ""), "chars": len(t), "report": reports.get(k)}
            for k, t in sorted(v.get("chapters_text", {}).items(), key=lambda kv: int(kv[0]))
        ]

    @app.get("/api/runs/{run_id}/chapters/{n}")
    async def chapter(run_id: str, n: int):
        v = await guard(manager().values(run_id))
        text = v.get("chapters_text", {}).get(str(n))
        if text is None:
            raise HTTPException(404, "章节尚未生成")
        return {"chapter": n, "title": v.get("chapter_titles", {}).get(str(n), ""), "text": text}

    @app.get("/api/runs/{run_id}/export", response_class=PlainTextResponse)
    async def export(run_id: str, kind: str = "book"):
        v = await guard(manager().values(run_id))
        if kind == "judge":
            return render_judge_report(v)
        return render_book(v)

    @app.get("/api/runs/{run_id}/events")
    async def events(run_id: str):
        await guard(manager().status(run_id))

        async def stream():
            async for ev in manager().bus.subscribe(run_id):
                yield f"event: {ev.get('event', 'message')}\ndata: {json.dumps(ev, ensure_ascii=False)}\n\n"
                if ev.get("event") == "finished":  # 全书完成后关闭流
                    break

        return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})

    return app


def get_app() -> FastAPI:
    """uvicorn 工厂入口：``uvicorn shuangwen.api:get_app --factory``。"""
    return create_app()
