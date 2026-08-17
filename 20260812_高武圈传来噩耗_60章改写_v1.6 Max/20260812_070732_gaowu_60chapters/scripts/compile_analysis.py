#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="汇编并行原稿分析结果。")
    parser.add_argument("--input", required=True)
    parser.add_argument("--task-dir", required=True)
    return parser.parse_args()


def section(title: str, body: str) -> str:
    return f"## {title}\n\n{body.strip()}\n\n"


def main() -> None:
    args = parse_args()
    task_dir = Path(args.task_dir)
    data = json.loads(Path(args.input).read_text(encoding="utf-8"))
    rows = sorted(
        (row for row in data["results"] if not row.get("error")),
        key=lambda row: row["output"]["pack_id"],
    )
    analysis_dir = task_dir / "analysis"

    master_parts = [
        "# 原稿全量分包分析汇编\n\n",
        "> 原稿共270章，按每9章一组拆成30个连续分包；每个分包对应目标改写稿的2章，因此形成严格的60章映射。\n\n",
    ]
    plot_parts = ["# 全书连续剧情链（30段）\n\n"]
    continuity_parts = ["# 全书连续性事实与风险库\n\n"]
    character_parts = ["# 分包人物状态记录\n\n"]
    world_parts = ["# 分包世界观与设定记录\n\n"]
    style_parts = ["# 分包叙事风格特征记录\n\n"]
    mapping_parts = [
        "# 60章映射底稿\n\n",
        "> 每个原稿9章分包重组为2个目标章节。下列内容是逐包策划稿，后续还需进行全局标题统一、人物弧线校准与跨包衔接。\n\n",
    ]

    for row in rows:
        out = row["output"]
        pid = int(out["pack_id"])
        start_target = pid * 2 - 1
        end_target = pid * 2
        header = f"# 分包{pid:02d}｜{out['source_range']}｜目标第{start_target:02d}-{end_target:02d}章\n\n"
        master_parts.append(header)
        master_parts.append(section("完整剧情链", out["chronological_plot"]))
        master_parts.append(section("逐章摘要", out["chapter_digest"]))
        master_parts.append(section("人物状态", out["characters"]))
        master_parts.append(section("世界观与设定", out["worldbuilding"]))
        master_parts.append(section("连续性事实", out["continuity_facts"]))
        master_parts.append(section("文风特征", out["style_features"]))
        master_parts.append(section("两章重组方案", out["target_two_chapter_plan"]))
        master_parts.append(section("衔接风险", out["continuity_risks"]))
        master_parts.append(f"**分析置信度：** {out['confidence']:.2f}\n\n---\n\n")

        plot_parts.append(f"## 分包{pid:02d}｜{out['source_range']}｜目标第{start_target:02d}-{end_target:02d}章\n\n{out['chronological_plot'].strip()}\n\n")
        continuity_parts.append(f"## 分包{pid:02d}｜目标第{start_target:02d}-{end_target:02d}章\n\n### 必须延续\n\n{out['continuity_facts'].strip()}\n\n### 衔接风险\n\n{out['continuity_risks'].strip()}\n\n")
        character_parts.append(f"## 分包{pid:02d}｜{out['source_range']}\n\n{out['characters'].strip()}\n\n")
        world_parts.append(f"## 分包{pid:02d}｜{out['source_range']}\n\n{out['worldbuilding'].strip()}\n\n")
        style_parts.append(f"## 分包{pid:02d}｜{out['source_range']}\n\n{out['style_features'].strip()}\n\n")
        mapping_parts.append(f"## 目标第{start_target:02d}-{end_target:02d}章｜来自{out['source_range']}\n\n{out['target_two_chapter_plan'].strip()}\n\n### 跨包约束\n\n{out['continuity_facts'].strip()}\n\n")

    outputs = {
        "pack_analysis_master.md": master_parts,
        "plot_chain_30_segments.md": plot_parts,
        "continuity_register.md": continuity_parts,
        "character_state_by_pack.md": character_parts,
        "worldbuilding_by_pack.md": world_parts,
        "style_features_by_pack.md": style_parts,
    }
    for name, parts in outputs.items():
        (analysis_dir / name).write_text("".join(parts), encoding="utf-8")
    (task_dir / "outline" / "mapping_draft_60_chapters.md").write_text(
        "".join(mapping_parts), encoding="utf-8"
    )

    print(f"compiled_packs={len(rows)}")
    for name in list(outputs) + ["../outline/mapping_draft_60_chapters.md"]:
        target = analysis_dir / name if not name.startswith("../") else task_dir / "outline" / "mapping_draft_60_chapters.md"
        print(f"{target.name}\t{target.stat().st_size}")


if __name__ == "__main__":
    main()
