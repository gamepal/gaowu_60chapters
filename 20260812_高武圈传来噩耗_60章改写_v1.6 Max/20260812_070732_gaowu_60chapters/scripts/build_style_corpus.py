#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="构建跨全书文风样本语料。")
    parser.add_argument("--task-dir", required=True)
    parser.add_argument("--samples", type=int, default=24)
    parser.add_argument("--opening-chars", type=int, default=900)
    parser.add_argument("--ending-chars", type=int, default=650)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    task_dir = Path(args.task_dir)
    chapter_dir = task_dir / "analysis" / "source_chapters"
    files = sorted(chapter_dir.glob("*.md"))
    if len(files) < args.samples:
        raise SystemExit("章节数量少于抽样数量。")

    positions = sorted({round(i * (len(files) - 1) / (args.samples - 1)) for i in range(args.samples)})
    parts = [
        "# 原稿文风代表性样本语料\n\n",
        "> 采用等距抽样覆盖全书，只截取各样本章的开头与章末，用于提炼节奏、句式、对白密度、讽刺机制和钩子结构。该文件是分析语料，不作为最终改写正文。\n\n",
    ]
    manifest: list[dict] = []
    for position in positions:
        path = files[position]
        text = path.read_text(encoding="utf-8").strip()
        opening = text[: args.opening_chars]
        ending = text[-args.ending_chars :]
        parts.append(f"## 样本：{path.stem}章\n\n### 开头截取\n\n{opening}\n\n### 章末截取\n\n{ending}\n\n---\n\n")
        manifest.append(
            {
                "chapter_file": str(path),
                "chapter_number": int(path.stem),
                "opening_characters": len(opening),
                "ending_characters": len(ending),
            }
        )

    output = task_dir / "analysis" / "style_sample_corpus.md"
    output.write_text("".join(parts), encoding="utf-8")
    (task_dir / "analysis" / "style_sample_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"sample_count={len(manifest)}")
    print(f"output_characters={len(output.read_text(encoding='utf-8'))}")
    print("chapters=" + ",".join(f"{item['chapter_number']:03d}" for item in manifest))


if __name__ == "__main__":
    main()
