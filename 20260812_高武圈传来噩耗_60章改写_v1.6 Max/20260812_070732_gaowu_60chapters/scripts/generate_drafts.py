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
    parser = argparse.ArgumentParser(description="依据结构化章卡批量生成正文初稿。")
    parser.add_argument("--task-dir", required=True)
    parser.add_argument("--model", default="claude-sonnet-4-6")
    parser.add_argument("--workers", type=int, default=5)
    return parser.parse_args()


def get_client() -> OpenAI:
    if not hasattr(THREAD_LOCAL, "client"):
        THREAD_LOCAL.client = OpenAI(timeout=900.0, max_retries=3)
    return THREAD_LOCAL.client


def make_prompt(task_dir: Path, pack: dict, chapter_idx: int) -> str:
    chapter = pack["chapters"][chapter_idx]
    pid = int(pack["pack_id"])
    source_text = Path(task_dir / "analysis" / "source_packs" / f"pack_{pid:02d}_*.md").parent.glob(f"pack_{pid:02d}_*.md")
    source_text = next(source_text).read_text(encoding="utf-8")
    story_bible = (task_dir / "analysis" / "story_bible.md").read_text(encoding="utf-8")
    
    return f"""# 写作任务

请根据以下故事圣经、原稿文本和详细章卡，撰写《高武圈传来噩耗》的第{chapter['target_chapter']:02d}章初稿。
要求：
1. **严格遵循章卡**：场景顺序、必须保留的信息、数值账目、章末钩子等必须精准执行。
2. **字数达标**：目标字数约为{chapter['target_length_chars']}个中文字符。请提供极高信息密度、丰富动作描写和荒诞细节的文本，绝不能敷衍了事。
3. **文风要求**：采用短句突击、对话驱动、反问强化、数值面板和阶级反讽。禁止平铺直叙。
4. **输出格式**：直接输出Markdown正文，无需任何自我介绍或解释。章节标题格式为 `## 第{chapter['target_chapter']:02d}章 {chapter['title']}`。

## 故事圣经

{story_bible}

## 本章详细章卡

```json
{json.dumps(chapter, ensure_ascii=False, indent=2)}
```

## 对应的原稿文本（供参考事实与数值，禁止直接大段复制）

{source_text}
"""


def main() -> None:
    args = parse_args()
    task_dir = Path(args.task_dir)
    catalog = json.loads((task_dir / "metadata" / "model_catalog.json").read_text(encoding="utf-8"))
    model_ids = {item["id"] for item in catalog.get("data", [])}
    if args.model not in model_ids:
        raise SystemExit(f"实时模型目录中不存在模型：{args.model}")

    outline_data = json.loads((task_dir / "outline" / "chapter_cards.json").read_text(encoding="utf-8"))
    packs = outline_data["packs"]
    
    drafts_dir = task_dir / "drafts" / "chapters"
    drafts_dir.mkdir(parents=True, exist_ok=True)
    prompt_dir = task_dir / "drafts" / "prompts"
    prompt_dir.mkdir(parents=True, exist_ok=True)

    tasks = []
    for pack in packs:
        for idx in range(2):
            tasks.append((pack, idx))

    def one(task: tuple[dict, int]) -> dict:
        pack, chapter_idx = task
        chapter = pack["chapters"][chapter_idx]
        num = chapter["target_chapter"]
        prompt = make_prompt(task_dir, pack, chapter_idx)
        (prompt_dir / f"chapter_{num:02d}.md").write_text(prompt, encoding="utf-8")
        
        # Determine max_tokens and thinking parameters based on model
        max_tokens = 8000
        extra_body = None
        if "claude" in args.model:
            max_tokens = 8192
            extra_body = {"thinking": {"type": "enabled", "budget_tokens": 2048}}
        elif "gpt" in args.model:
            max_tokens = 8000
            extra_body = {"reasoning": {"effort": "low"}}
            
        response = get_client().chat.completions.create(
            model=args.model,
            messages=[
                {
                    "role": "system",
                    "content": "你是顶尖网文主笔。请严格按照章卡和故事圣经，撰写高密度、高爽感、黑色幽默的赛博高武小说正文。直接输出Markdown文本。",
                },
                {"role": "user", "content": prompt},
            ],
            max_tokens=max_tokens,
            extra_body=extra_body,
        )
        content = response.choices[0].message.content or ""
        (drafts_dir / f"chapter_{num:02d}.md").write_text(content, encoding="utf-8")
        
        return {
            "chapter": num,
            "length": len(content),
            "usage": {
                "model": response.model,
                "finish_reason": response.choices[0].finish_reason,
                "prompt_tokens": getattr(response.usage, "prompt_tokens", None),
                "completion_tokens": getattr(response.usage, "completion_tokens", None),
                "total_tokens": getattr(response.usage, "total_tokens", None),
            }
        }

    results = []
    failures = []
    with cf.ThreadPoolExecutor(max_workers=args.workers) as executor:
        future_map = {executor.submit(one, task): task for task in tasks}
        for future in cf.as_completed(future_map):
            task = future_map[future]
            num = task[0]["chapters"][task[1]]["target_chapter"]
            try:
                res = future.result()
                results.append(res)
                print(f"OK chapter={num:02d} length={res['length']}", flush=True)
            except Exception as exc:
                failures.append(f"chapter={num:02d}: {exc}")
                print(f"FAIL chapter={num:02d}: {exc}", flush=True)

    if failures:
        raise RuntimeError("正文生成失败：\n" + "\n".join(failures))

    usage_summary = {
        "calls": len(results),
        "model": args.model,
        "total_characters": sum(r["length"] for r in results),
        "prompt_tokens": sum(r["usage"].get("prompt_tokens") or 0 for r in results),
        "completion_tokens": sum(r["usage"].get("completion_tokens") or 0 for r in results),
        "total_tokens": sum(r["usage"].get("total_tokens") or 0 for r in results),
    }
    (task_dir / "logs" / "draft_generation_usage.json").write_text(
        json.dumps(usage_summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(usage_summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
