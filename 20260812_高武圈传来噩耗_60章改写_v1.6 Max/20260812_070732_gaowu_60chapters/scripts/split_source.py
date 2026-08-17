#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from pathlib import Path

CHAPTER_RE = re.compile(r"(?m)^第(?P<number>\d+)章\s+(?P<title>[^\n\r]+)\s*$")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="拆分中文网文原稿并生成分析分包。")
    parser.add_argument("--source", required=True, help="原稿文本路径")
    parser.add_argument("--task-dir", required=True, help="任务根目录")
    parser.add_argument("--chapters-per-pack", type=int, default=9)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    source_path = Path(args.source)
    task_dir = Path(args.task_dir)
    chapter_dir = task_dir / "analysis" / "source_chapters"
    pack_dir = task_dir / "analysis" / "source_packs"
    chapter_dir.mkdir(parents=True, exist_ok=True)
    pack_dir.mkdir(parents=True, exist_ok=True)

    text = source_path.read_text(encoding="utf-8-sig")
    matches = list(CHAPTER_RE.finditer(text))
    if not matches:
        raise SystemExit("未识别到章节标题。")

    chapters: list[dict] = []
    for idx, match in enumerate(matches):
        start = match.start()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        body = text[start:end].strip() + "\n"
        number = int(match.group("number"))
        title = match.group("title").strip()
        start_line = text.count("\n", 0, start) + 1
        end_line = text.count("\n", 0, end) + 1
        paragraphs = [line.strip() for line in body.splitlines() if line.strip()]
        dialogue_lines = sum(1 for line in paragraphs if "“" in line or '"' in line)
        sha256 = hashlib.sha256(body.encode("utf-8")).hexdigest()
        chapter_file = chapter_dir / f"{number:03d}.md"
        chapter_file.write_text(body, encoding="utf-8")
        chapters.append(
            {
                "source_order": idx + 1,
                "chapter_number": number,
                "title": title,
                "start_line": start_line,
                "end_line": end_line,
                "characters": len(body),
                "paragraphs": len(paragraphs),
                "dialogue_lines": dialogue_lines,
                "dialogue_line_ratio": round(dialogue_lines / max(len(paragraphs), 1), 4),
                "sha256": sha256,
                "file": str(chapter_file),
            }
        )

    json_path = task_dir / "analysis" / "source_chapter_index.json"
    json_path.write_text(json.dumps(chapters, ensure_ascii=False, indent=2), encoding="utf-8")

    csv_path = task_dir / "analysis" / "source_chapter_metrics.csv"
    with csv_path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(chapters[0].keys()))
        writer.writeheader()
        writer.writerows(chapters)

    packs: list[dict] = []
    pack_size = args.chapters_per_pack
    for pack_idx, offset in enumerate(range(0, len(chapters), pack_size), start=1):
        members = chapters[offset : offset + pack_size]
        first_num = members[0]["chapter_number"]
        last_num = members[-1]["chapter_number"]
        pack_file = pack_dir / f"pack_{pack_idx:02d}_ch{first_num:03d}-{last_num:03d}.md"
        pieces = [
            f"# 原稿分析分包 {pack_idx:02d}\n\n",
            f"> 覆盖原稿第{first_num:03d}章至第{last_num:03d}章，共{len(members)}章。\n\n",
        ]
        for member in members:
            chapter_text = Path(member["file"]).read_text(encoding="utf-8")
            pieces.append(chapter_text)
            pieces.append("\n")
        pack_file.write_text("".join(pieces), encoding="utf-8")
        packs.append(
            {
                "pack_id": pack_idx,
                "first_chapter": first_num,
                "last_chapter": last_num,
                "chapter_count": len(members),
                "characters": sum(item["characters"] for item in members),
                "file": str(pack_file),
            }
        )

    (task_dir / "analysis" / "source_pack_index.json").write_text(
        json.dumps(packs, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    summary = {
        "source": str(source_path),
        "chapter_count": len(chapters),
        "pack_count": len(packs),
        "chapters_per_pack": pack_size,
        "first_heading": f"第{chapters[0]['chapter_number']:03d}章 {chapters[0]['title']}",
        "last_heading": f"第{chapters[-1]['chapter_number']:03d}章 {chapters[-1]['title']}",
        "total_characters": sum(item["characters"] for item in chapters),
        "mean_characters_per_chapter": round(
            sum(item["characters"] for item in chapters) / len(chapters), 2
        ),
        "mean_dialogue_line_ratio": round(
            sum(item["dialogue_line_ratio"] for item in chapters) / len(chapters), 4
        ),
    }
    (task_dir / "analysis" / "source_statistics.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
