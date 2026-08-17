#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="修复最终文档的章节标题格式。")
    parser.add_argument("--task-dir", required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    task_dir = Path(args.task_dir)
    final_file = task_dir / "final" / "高武圈传来噩耗_60章重构版.md"
    text = final_file.read_text(encoding="utf-8")
    
    # 修复可能的标题格式问题，例如：
    # "## 第1章" -> "## 第01章"
    # "## 第 01 章" -> "## 第01章"
    # "# 第01章" -> "## 第01章"
    
    def replace_heading(match):
        level = match.group(1)
        num_str = match.group(2).strip()
        title = match.group(3).strip()
        
        try:
            num = int(num_str)
            return f"## 第{num:02d}章 {title}"
        except ValueError:
            return match.group(0)

    # 匹配各种可能的章节标题变体
    pattern = re.compile(r"(?m)^(#{1,3})\s*第\s*(\d{1,2})\s*章\s*(.+)$")
    fixed_text = pattern.sub(replace_heading, text)
    
    final_file.write_text(fixed_text, encoding="utf-8")
    print(f"Fixed headings in {final_file.name}")


if __name__ == "__main__":
    main()
