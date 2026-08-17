#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="将初稿按卷或批次组装。")
    parser.add_argument("--task-dir", required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    task_dir = Path(args.task_dir)
    drafts_dir = task_dir / "drafts" / "chapters"
    batches_dir = task_dir / "drafts" / "batches"
    batches_dir.mkdir(parents=True, exist_ok=True)

    chapters = []
    for i in range(1, 61):
        path = drafts_dir / f"chapter_{i:02d}.md"
        if not path.exists():
            raise FileNotFoundError(f"缺失初稿文件：{path}")
        chapters.append((i, path.read_text(encoding="utf-8").strip()))

    batch_size = 15
    for batch_idx in range(4):
        start = batch_idx * batch_size + 1
        end = start + batch_size - 1
        batch_chapters = chapters[start - 1 : end]
        
        parts = [
            f"# 《高武圈传来噩耗》60章改写版 - 第{batch_idx+1}卷（第{start:02d}-{end:02d}章）\n\n",
            "> 内部初稿，待全局修订与质检。\n\n"
        ]
        
        for num, text in batch_chapters:
            parts.append(text)
            parts.append("\n\n---\n\n")
            
        out_path = batches_dir / f"batch_{batch_idx+1}_ch{start:02d}_{end:02d}.md"
        out_path.write_text("".join(parts), encoding="utf-8")
        print(f"Written {out_path.name}: {len(batch_chapters)} chapters, {len(out_path.read_text(encoding='utf-8'))} chars")

    all_parts = [
        "# 《高武圈传来噩耗》60章改写版（完整初稿）\n\n",
        "> 本文档包含第01至60章的全部初稿内容。\n\n"
    ]
    for num, text in chapters:
        all_parts.append(text)
        all_parts.append("\n\n---\n\n")
        
    full_path = task_dir / "drafts" / "full_draft_60_chapters.md"
    full_path.write_text("".join(all_parts), encoding="utf-8")
    print(f"Written {full_path.name}: 60 chapters, {len(full_path.read_text(encoding='utf-8'))} chars")


if __name__ == "__main__":
    main()
