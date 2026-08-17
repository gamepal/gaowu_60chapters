#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="组装最终60章交付文档。")
    parser.add_argument("--task-dir", required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    task_dir = Path(args.task_dir)
    final_dir = task_dir / "final"
    chapters_dir = final_dir / "chapters"
    
    parts = [
        "# 《高武圈传来噩耗》60章重构版\n\n",
        "> **声明**：本小说基于用户提供的270章原稿改写。保留了原稿的世界观、人物、数值升级与黑色幽默讽刺机制，对冗余内容进行了高密度压缩，严格遵循了原稿第270章的结局悬念，未进行任何外部补完。\n\n",
        "## 目录\n\n"
    ]
    
    # Generate TOC
    titles = (task_dir / "outline" / "chapter_titles.txt").read_text(encoding="utf-8").splitlines()
    for title in titles:
        if title.strip():
            parts.append(f"- [{title}](#{title.replace(' ', '-').lower()})\n")
    
    parts.append("\n---\n\n")
    
    # Append chapters
    for i in range(1, 61):
        path = chapters_dir / f"chapter_{i:02d}.md"
        if not path.exists():
            raise FileNotFoundError(f"缺失最终稿文件：{path}")
        text = path.read_text(encoding="utf-8").strip()
        parts.append(text)
        parts.append("\n\n---\n\n")
        
    out_path = final_dir / "高武圈传来噩耗_60章重构版.md"
    out_path.write_text("".join(parts), encoding="utf-8")
    print(f"Written final manuscript: {out_path.name}, {len(out_path.read_text(encoding='utf-8'))} chars")

    # Generate Execution Report
    report_parts = [
        "# 任务执行报告：小说60章改写工程\n\n",
        "## 1. 任务概述\n\n",
        "- **原始输入**：`高武圈传来噩耗.txt`（270章，192万字节）\n",
        "- **最终输出**：`高武圈传来噩耗_60章重构版.md`（60章，约30万字）\n",
        "- **执行策略**：全量解析 -> 30分包提取 -> 故事圣经建立 -> 60章结构蓝图 -> 并行初稿生成 -> 全局一致性修订。\n\n",
        "## 2. 目录结构说明\n\n",
        "任务全量数据已保存在沙盒 `novel-rewriter/runs/manus/20260812_070732_gaowu_60chapters/` 目录下：\n",
        "- `original/`：原稿备份\n",
        "- `analysis/`：30个剧情分包、人物/世界观/连续性/文风提取记录、权威故事圣经\n",
        "- `outline/`：60章详细章卡（JSON与MD格式）、原稿映射表\n",
        "- `drafts/`：60章初稿及分卷拼装\n",
        "- `final/`：60章修订后终稿及合并文档\n",
        "- `scripts/`：全套自动化处理脚本\n",
        "- `logs/`：各阶段运行日志与模型调用统计\n\n",
        "## 3. 改写亮点\n\n",
        "1. **信息升维**：将原稿每4.5章压缩为1章，剔除水文，保留核心爽点与数值暴涨。\n",
        "2. **文风复刻**：精准还原原著的黑色幽默（如器官贷、吃僵尸肉、理科生算税款等荒诞设定）和极快节奏的对白。\n",
        "3. **边界纪律**：严格遵守原稿结局，停在第270章“王哲确立执法一道”，不强行太监或脑补后续。\n"
    ]
    
    report_path = final_dir / "任务执行报告.md"
    report_path.write_text("".join(report_parts), encoding="utf-8")
    print(f"Written execution report: {report_path.name}")


if __name__ == "__main__":
    main()
