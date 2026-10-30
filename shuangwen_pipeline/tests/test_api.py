import time

from fastapi.testclient import TestClient

from shuangwen.api import create_app
from shuangwen.config import AppSettings


def wait_for(client, run_id, status, timeout=20):
    deadline = time.time() + timeout
    while time.time() < deadline:
        s = client.get(f"/api/runs/{run_id}").json()
        if s["status"] == status:
            return s
        time.sleep(0.05)
    raise AssertionError(f"timeout waiting for {status}: {s}")


def test_api_end_to_end(tmp_path):
    app = create_app(AppSettings(mock_llm=True, output_dir=str(tmp_path)))
    with TestClient(app) as client:
        assert "爽文工坊" in client.get("/").text
        assert client.get("/api/health").json()["mock_llm"] is True
        assert client.post("/api/runs", json={"raw_ch1_3": "", "title": "x"}).status_code == 422
        assert client.post("/api/runs", json={"raw_ch1_3": "x", "settings": {"total_chapters": 25}}).status_code == 422
        assert client.get("/api/runs/nope").status_code == 404

        run_id = client.post("/api/runs", json={"raw_ch1_3": "原稿", "title": "测试", "settings": {"total_chapters": 24}}).json()["run_id"]
        s = wait_for(client, run_id, "awaiting_selection")
        assert s["interrupt"][0]["recommended_branch"] == "2B_Reconstructed"
        board = client.get(f"/api/runs/{run_id}/board").json()
        assert set(board["candidates"]) == {"2A", "2B", "2C"} and board["judge_report"]["evaluations"]
        assert "评审报告" in client.get(f"/api/runs/{run_id}/export?kind=judge").text
        assert client.post(f"/api/runs/{run_id}/resume").status_code == 409
        assert client.post(f"/api/runs/{run_id}/selection", json={"winning_branch": "2X"}).status_code == 422

        assert client.post(f"/api/runs/{run_id}/selection", json={"winning_branch": "B"}).status_code == 202
        s = wait_for(client, run_id, "completed")
        assert s["progress"]["chapters_written"] == 24 and s["usage"]["calls"] > 0
        assert len(client.get(f"/api/runs/{run_id}/chapters").json()) == 24
        assert client.get(f"/api/runs/{run_id}/chapters/10").json()["text"]
        assert client.get(f"/api/runs/{run_id}/chapters/99").status_code == 404
        assert "## 第24章" in client.get(f"/api/runs/{run_id}/export").text
        assert len(client.get(f"/api/runs/{run_id}/outline").json()["arcs"]) == 2
        assert client.get("/api/runs").json()[0]["run_id"] == run_id

        # SSE：历史事件可补齐
        with client.stream("GET", f"/api/runs/{run_id}/events") as resp:
            seen = []
            for line in resp.iter_lines():
                if line.startswith("event: "):
                    seen.append(line[7:])
                if "finished" in seen:
                    break
        assert {"judged", "interrupt", "selected", "chapter_done", "completed"} <= set(seen)
    assert (tmp_path / run_id / "book.md").exists()
