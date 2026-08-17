#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="汇编并校验60章结构化章卡。")
    parser.add_argument("--task-dir", required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    task_dir = Path(args.task_dir)
    outline_dir = task_dir / "outline"
    data = json.loads((outline_dir / "chapter_cards.json").read_text(encoding="utf-8"))
    chapters = sorted(data["chapters"], key=lambda item: item["target_chapter"])

    numbers = [item["target_chapter"] for item in chapters]
    titles = [item["title"].strip() for item in chapters]
    expected = list(range(1, 61))
    duplicate_titles = sorted(title for title, count in Counter(titles).items() if count > 1)
    coverage_pattern = re.compile(r"第?\d{1,3}.*?\d{1,3}章")

    report = {
        "chapter_count": len(chapters),
        "numbers_are_1_to_60": numbers == expected,
        "missing_numbers": sorted(set(expected) - set(numbers)),
        "duplicate_numbers": sorted(number for number, count in Counter(numbers).items() if count > 1),
        "duplicate_titles": duplicate_titles,
        "all_have_source_coverage": all(bool(item.get("source_coverage")) for item in chapters),
        "all_have_3_to_6_scenes": all(3 <= len(item.get("scenes", [])) <= 6 for item in chapters),
        "all_have_closing_hooks": all(len(item.get("closing_hook", "").strip()) >= 12 for item in chapters),
        "all_have_continuity_in_out": all(item.get("continuity_in") and item.get("continuity_out") for item in chapters),
        "target_length_min": min(item["target_length_chars"] for item in chapters),
        "target_length_max": max(item["target_length_chars"] for item in chapters),
        "target_length_total": sum(item["target_length_chars"] for item in chapters),
        "coverage_pattern_recognized": sum(bool(coverage_pattern.search(item["source_coverage"])) for item in chapters),
    }
    report["passed"] = all(
        [
            report["chapter_count"] == 60,
            report["numbers_are_1_to_60"],
            not report["duplicate_numbers"],
            not report["duplicate_titles"],
            report["all_have_source_coverage"],
            report["all_have_3_to_6_scenes"],
            report["all_have_closing_hooks"],
            report["all_have_continuity_in_out"],
        ]
    )
    (outline_dir / "outline_validation.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    md: list[str] = [
        "# 《高武圈传来噩耗》60章改写总纲\n\n",
        "> 本总纲由原稿270章按连续映射重组而成：每9个原章节对应2个目标章节，共30组、60章。正文必须严格依据本总纲和故事圣经写作，不得擅自补完原稿第270章之后的剧情。\n\n",
        "## 总体结构\n\n",
        "| 目标章节 | 原稿覆盖 | 章节标题 | 目标字数 | 场景数 |\n",
        "|---:|---|---|---:|---:|\n",
    ]
    for item in chapters:
        md.append(
            f"| 第{item['target_chapter']:02d}章 | {item['source_coverage']} | {item['title']} | {item['target_length_chars']} | {len(item['scenes'])} |\n"
        )
    md.append("\n---\n\n")

    for item in chapters:
        number = item["target_chapter"]
        md.append(f"## 第{number:02d}章 {item['title']}\n\n")
        md.append(f"**原稿覆盖：** {item['source_coverage']}  \n")
        md.append(f"**章节功能：** {item['purpose']}  \n")
        md.append(f"**目标长度：** 约{item['target_length_chars']}个中文字符\n\n")
        md.append(f"### 开场\n\n{item['opening']}\n\n")
        md.append("### 场景推进\n\n")
        md.append("| 顺序 | 场景 | 出场人物 | 行动 | 冲突 | 回报/结果 |\n")
        md.append("|---:|---|---|---|---|---|\n")
        for scene in sorted(item["scenes"], key=lambda row: row["sequence"]):
            values = [
                str(scene["sequence"]),
                scene["setting"],
                scene["cast"],
                scene["action"],
                scene["conflict"],
                scene["payoff"],
            ]
            values = [value.replace("|", "／").replace("\n", " ") for value in values]
            md.append("| " + " | ".join(values) + " |\n")
        md.append("\n### 必须保留的信息\n\n")
        md.extend(f"- {value}\n" for value in item["must_keep"])
        md.append("\n### 人物变化\n\n")
        md.extend(f"- {value}\n" for value in item["character_changes"])
        md.append("\n### 数值与资源账\n\n")
        md.extend(f"- {value}\n" for value in item["numeric_ledger"])
        md.append("\n### 连续性输入\n\n")
        md.extend(f"- {value}\n" for value in item["continuity_in"])
        md.append("\n### 连续性输出\n\n")
        md.extend(f"- {value}\n" for value in item["continuity_out"])
        md.append("\n### 文风节拍\n\n")
        md.extend(f"- {value}\n" for value in item["style_beats"])
        md.append(f"\n### 章末钩子\n\n> {item['closing_hook']}\n\n---\n\n")

    (outline_dir / "60_chapter_outline.md").write_text("".join(md), encoding="utf-8")
    (outline_dir / "chapter_titles.txt").write_text(
        "".join(f"第{item['target_chapter']:02d}章 {item['title']}\n" for item in chapters),
        encoding="utf-8",
    )

    with (outline_dir / "chapter_mapping.csv").open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["目标章节", "标题", "原稿覆盖", "目标字数", "场景数", "章末钩子"])
        for item in chapters:
            writer.writerow(
                [
                    item["target_chapter"],
                    item["title"],
                    item["source_coverage"],
                    item["target_length_chars"],
                    len(item["scenes"]),
                    item["closing_hook"],
                ]
            )

    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
