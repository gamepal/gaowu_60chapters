#!/usr/bin/env python3
from __future__ import annotations

import argparse
import concurrent.futures as cf
import json
import threading
from pathlib import Path

from openai import OpenAI


THREAD_LOCAL = threading.local()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="按9原章->2目标章生成结构化章卡。")
    parser.add_argument("--task-dir", required=True)
    parser.add_argument("--model", default="gpt-5")
    parser.add_argument("--workers", type=int, default=5)
    return parser.parse_args()


def get_client() -> OpenAI:
    if not hasattr(THREAD_LOCAL, "client"):
        THREAD_LOCAL.client = OpenAI(timeout=900.0, max_retries=3)
    return THREAD_LOCAL.client


def schema() -> dict:
    scene = {
        "type": "object",
        "properties": {
            "sequence": {"type": "integer"},
            "setting": {"type": "string"},
            "cast": {"type": "string"},
            "action": {"type": "string"},
            "conflict": {"type": "string"},
            "payoff": {"type": "string"},
        },
        "required": ["sequence", "setting", "cast", "action", "conflict", "payoff"],
        "additionalProperties": False,
    }
    card = {
        "type": "object",
        "properties": {
            "target_chapter": {"type": "integer"},
            "title": {"type": "string"},
            "source_coverage": {"type": "string"},
            "purpose": {"type": "string"},
            "opening": {"type": "string"},
            "scenes": {"type": "array", "items": scene, "minItems": 3, "maxItems": 6},
            "must_keep": {"type": "array", "items": {"type": "string"}},
            "character_changes": {"type": "array", "items": {"type": "string"}},
            "numeric_ledger": {"type": "array", "items": {"type": "string"}},
            "continuity_in": {"type": "array", "items": {"type": "string"}},
            "continuity_out": {"type": "array", "items": {"type": "string"}},
            "style_beats": {"type": "array", "items": {"type": "string"}},
            "closing_hook": {"type": "string"},
            "target_length_chars": {"type": "integer"},
        },
        "required": [
            "target_chapter",
            "title",
            "source_coverage",
            "purpose",
            "opening",
            "scenes",
            "must_keep",
            "character_changes",
            "numeric_ledger",
            "continuity_in",
            "continuity_out",
            "style_beats",
            "closing_hook",
            "target_length_chars",
        ],
        "additionalProperties": False,
    }
    return {
        "type": "object",
        "properties": {
            "pack_id": {"type": "integer"},
            "source_range": {"type": "string"},
            "chapters": {"type": "array", "items": card, "minItems": 2, "maxItems": 2},
            "pair_transition": {"type": "string"},
            "pack_exit_state": {"type": "string"},
            "fidelity_notes": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["pack_id", "source_range", "chapters", "pair_transition", "pack_exit_state", "fidelity_notes"],
        "additionalProperties": False,
    }


def make_prompt(task_dir: Path, row: dict, prev_row: dict | None, next_row: dict | None) -> str:
    out = row["output"]
    pid = int(out["pack_id"])
    target_a = pid * 2 - 1
    target_b = pid * 2
    source_text = Path(row["input"]).read_text(encoding="utf-8")
    story_bible = (task_dir / "analysis" / "story_bible.md").read_text(encoding="utf-8")
    prev_context = "无，这是全书开端。" if prev_row is None else (
        prev_row["output"]["chronological_plot"] + "\n必须带入：\n" + prev_row["output"]["continuity_facts"]
    )
    next_context = "无，这是所给原稿终点。" if next_row is None else (
        next_row["output"]["chronological_plot"] + "\n后续约束：\n" + next_row["output"]["continuity_facts"]
    )
    return f"""# 章卡任务

将原稿分包{pid:02d}（{out['source_range']}）重组为目标第{target_a:02d}章和第{target_b:02d}章。两个目标章合计必须覆盖分包内全部关键事件、人物变化、数值变化与伏笔；不得挪用后续分包事件，不得添加原稿没有的结果。每章建议3800-5000个中文字符，3-6个场景；开头承接上一章，结尾必须有强钩子。

标题应短、狠、有网文点击感，优先使用本分包核心荒诞点或冲突，不要连续多章采用相同句式。`source_coverage`必须写清原稿具体章节范围。`numeric_ledger`中只写原文有依据的数值或明确写“需回查原章”，禁止臆造。最后一包的目标第60章必须停在原稿第270章既有悬念，不得补完翻山州任务。

## 权威故事圣经

{story_bible}

## 前一分包结尾状态

{prev_context}

## 本分包既有分析

### 剧情链
{out['chronological_plot']}

### 逐章摘要
{out['chapter_digest']}

### 人物状态
{out['characters']}

### 世界观
{out['worldbuilding']}

### 连续性事实
{out['continuity_facts']}

### 文风特征
{out['style_features']}

### 初步两章方案
{out['target_two_chapter_plan']}

### 已知风险
{out['continuity_risks']}

## 后一分包开局状态

{next_context}

## 本分包原文

{source_text}
"""


def validate(data: dict, pid: int) -> None:
    expected = [pid * 2 - 1, pid * 2]
    got = [item["target_chapter"] for item in data["chapters"]]
    if data["pack_id"] != pid or got != expected:
        raise ValueError(f"分包{pid}章号不匹配：{got}，期望{expected}")
    for item in data["chapters"]:
        if not 3200 <= item["target_length_chars"] <= 5500:
            raise ValueError(f"第{item['target_chapter']}章目标字数异常：{item['target_length_chars']}")


def main() -> None:
    args = parse_args()
    task_dir = Path(args.task_dir)
    catalog = json.loads((task_dir / "metadata" / "model_catalog.json").read_text(encoding="utf-8"))
    model_ids = {item["id"] for item in catalog.get("data", [])}
    if args.model not in model_ids:
        raise SystemExit(f"实时模型目录中不存在模型：{args.model}")

    results_data = json.loads((task_dir / "analysis" / "pack_analysis_results.json").read_text(encoding="utf-8"))
    rows = sorted(
        [row for row in results_data["results"] if not row.get("error")],
        key=lambda row: row["output"]["pack_id"],
    )
    prompt_dir = task_dir / "outline" / "prompts"
    raw_dir = task_dir / "outline" / "raw"
    prompt_dir.mkdir(parents=True, exist_ok=True)
    raw_dir.mkdir(parents=True, exist_ok=True)

    def one(index: int) -> dict:
        row = rows[index]
        pid = int(row["output"]["pack_id"])
        prompt = make_prompt(
            task_dir,
            row,
            rows[index - 1] if index > 0 else None,
            rows[index + 1] if index + 1 < len(rows) else None,
        )
        (prompt_dir / f"pack_{pid:02d}.md").write_text(prompt, encoding="utf-8")
        response = get_client().chat.completions.create(
            model=args.model,
            messages=[
                {
                    "role": "system",
                    "content": "你是中文长篇网文总策划。严格依据用户原稿制作结构化章卡，只输出符合JSON Schema的数据。",
                },
                {"role": "user", "content": prompt},
            ],
            max_completion_tokens=9000,
            extra_body={"reasoning": {"effort": "low"}},
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "two_chapter_outline",
                    "strict": True,
                    "schema": schema(),
                },
            },
        )
        content = response.choices[0].message.content or ""
        data = json.loads(content)
        validate(data, pid)
        payload = {
            "data": data,
            "usage": {
                "model": response.model,
                "finish_reason": response.choices[0].finish_reason,
                "prompt_tokens": getattr(response.usage, "prompt_tokens", None),
                "completion_tokens": getattr(response.usage, "completion_tokens", None),
                "total_tokens": getattr(response.usage, "total_tokens", None),
            },
        }
        (raw_dir / f"pack_{pid:02d}.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return payload

    payloads: list[dict | None] = [None] * len(rows)
    failures: list[str] = []
    with cf.ThreadPoolExecutor(max_workers=args.workers) as executor:
        future_map = {executor.submit(one, idx): idx for idx in range(len(rows))}
        for future in cf.as_completed(future_map):
            idx = future_map[future]
            pid = int(rows[idx]["output"]["pack_id"])
            try:
                payloads[idx] = future.result()
                print(f"OK pack={pid:02d}", flush=True)
            except Exception as exc:
                failures.append(f"pack={pid:02d}: {exc}")
                print(f"FAIL pack={pid:02d}: {exc}", flush=True)

    if failures:
        raise RuntimeError("章卡生成失败：\n" + "\n".join(failures))

    cards = [chapter for payload in payloads if payload for chapter in payload["data"]["chapters"]]
    combined = {
        "model": args.model,
        "pack_count": len(payloads),
        "chapter_count": len(cards),
        "chapters": cards,
        "packs": [payload["data"] for payload in payloads if payload],
    }
    (task_dir / "outline" / "chapter_cards.json").write_text(
        json.dumps(combined, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    usage_rows = [payload["usage"] for payload in payloads if payload]
    usage_summary = {
        "calls": len(usage_rows),
        "model": args.model,
        "prompt_tokens": sum(row.get("prompt_tokens") or 0 for row in usage_rows),
        "completion_tokens": sum(row.get("completion_tokens") or 0 for row in usage_rows),
        "total_tokens": sum(row.get("total_tokens") or 0 for row in usage_rows),
    }
    (task_dir / "logs" / "outline_generation_usage.json").write_text(
        json.dumps(usage_summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(usage_summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
