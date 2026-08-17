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
    parser = argparse.ArgumentParser(description="对初稿进行全局一致性修订。")
    parser.add_argument("--task-dir", required=True)
    parser.add_argument("--model", default="claude-sonnet-4-6")
    parser.add_argument("--workers", type=int, default=5)
    return parser.parse_args()


def get_client() -> OpenAI:
    if not hasattr(THREAD_LOCAL, "client"):
        THREAD_LOCAL.client = OpenAI(timeout=900.0, max_retries=3)
    return THREAD_LOCAL.client


def make_prompt(task_dir: Path, chapter_num: int, draft_text: str, prev_draft: str | None, next_draft: str | None) -> str:
    story_bible = (task_dir / "analysis" / "story_bible.md").read_text(encoding="utf-8")
    
    context = ""
    if prev_draft:
        # Extract last 1000 chars of previous chapter
        context += f"## 上一章结尾（供衔接参考）\n\n{prev_draft[-1000:]}\n\n"
    if next_draft:
        # Extract first 1000 chars of next chapter
        context += f"## 下一章开头（供铺垫参考）\n\n{next_draft[:1000]}\n\n"

    return f"""# 修订任务

你是《高武圈传来噩耗》的最终审稿与修订编辑。请基于故事圣经，对第{chapter_num:02d}章的初稿进行全面润色和一致性修复。

## 故事圣经与纪律要求

{story_bible}

{context}

## 第{chapter_num:02d}章初稿

{draft_text}

## 修订要求

1. **前后衔接**：确保本章开头与上一章结尾无缝衔接，本章结尾的钩子能自然引出下一章开头。
2. **人物一致性**：检查人物称呼、性格表现是否符合故事圣经，修正任何OOC（崩人设）的表现。
3. **数值纪律**：检查境界、肉身强度、血气浓度、金钱、药容量等数值，确保没有突变或前后矛盾。
4. **文风强化**：增强黑色幽默、反讽和阶级对立的描写。遇到冗长的解说段落，改为对话或心理活动。
5. **格式规范**：输出纯Markdown正文，无需解释，直接以 `## 第{chapter_num:02d}章 [章节名]` 开头。
"""


def main() -> None:
    args = parse_args()
    task_dir = Path(args.task_dir)
    drafts_dir = task_dir / "drafts" / "chapters"
    final_dir = task_dir / "final" / "chapters"
    final_dir.mkdir(parents=True, exist_ok=True)
    
    drafts = []
    for i in range(1, 61):
        path = drafts_dir / f"chapter_{i:02d}.md"
        if not path.exists():
            raise FileNotFoundError(f"缺失初稿文件：{path}")
        drafts.append(path.read_text(encoding="utf-8"))

    tasks = []
    for i in range(60):
        prev_draft = drafts[i - 1] if i > 0 else None
        next_draft = drafts[i + 1] if i < 59 else None
        tasks.append((i + 1, drafts[i], prev_draft, next_draft))

    def one(task: tuple[int, str, str | None, str | None]) -> dict:
        num, draft_text, prev_draft, next_draft = task
        prompt = make_prompt(task_dir, num, draft_text, prev_draft, next_draft)
        
        # We use a cheaper model for revision to save time and cost, since the draft is already good
        model = "gpt-5-mini" if "claude" not in args.model else "claude-haiku-4-5"
        
        max_tokens = 8000
        extra_body = None
        if "claude" in model:
            max_tokens = 8192
            extra_body = {"thinking": {"type": "enabled", "budget_tokens": 1024}}
        elif "gpt" in model:
            extra_body = {"reasoning": {"effort": "low"}}
            
        response = get_client().chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": "你是资深网文修订编辑。请修正初稿中的连贯性错误，强化文风，直接输出修改后的Markdown正文。",
                },
                {"role": "user", "content": prompt},
            ],
            max_tokens=max_tokens,
            extra_body=extra_body,
        )
        content = response.choices[0].message.content or ""
        (final_dir / f"chapter_{num:02d}.md").write_text(content, encoding="utf-8")
        
        return {
            "chapter": num,
            "length": len(content),
            "usage": {
                "model": response.model,
                "prompt_tokens": getattr(response.usage, "prompt_tokens", None),
                "completion_tokens": getattr(response.usage, "completion_tokens", None),
            }
        }

    results = []
    failures = []
    with cf.ThreadPoolExecutor(max_workers=args.workers) as executor:
        future_map = {executor.submit(one, task): task for task in tasks}
        for future in cf.as_completed(future_map):
            task = future_map[future]
            num = task[0]
            try:
                res = future.result()
                results.append(res)
                print(f"Revised chapter={num:02d} length={res['length']}", flush=True)
            except Exception as exc:
                failures.append(f"chapter={num:02d}: {exc}")
                print(f"FAIL chapter={num:02d}: {exc}", flush=True)

    if failures:
        raise RuntimeError("正文修订失败：\n" + "\n".join(failures))

    usage_summary = {
        "calls": len(results),
        "total_characters": sum(r["length"] for r in results),
        "prompt_tokens": sum(r["usage"].get("prompt_tokens") or 0 for r in results),
        "completion_tokens": sum(r["usage"].get("completion_tokens") or 0 for r in results),
    }
    (task_dir / "logs" / "revision_usage.json").write_text(
        json.dumps(usage_summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(usage_summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
