#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="核验最终交付文档的质量。")
    parser.add_argument("--task-dir", required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    task_dir = Path(args.task_dir)
    qa_dir = task_dir / "qa"
    qa_dir.mkdir(parents=True, exist_ok=True)
    
    final_file = task_dir / "final" / "高武圈传来噩耗_60章重构版.md"
    text = final_file.read_text(encoding="utf-8")
    
    # Check chapter headings
    heading_re = re.compile(r"(?m)^## 第(\d{2})章\s+(.+)$")
    matches = list(heading_re.finditer(text))
    
    report = {
        "total_characters": len(text),
        "chapter_headings_found": len(matches),
        "chapters_sequential": True,
        "missing_chapters": [],
        "duplicate_chapters": [],
        "format_issues": []
    }
    
    found_nums = []
    for match in matches:
        num = int(match.group(1))
        found_nums.append(num)
        
    expected_nums = list(range(1, 61))
    
    if found_nums != expected_nums:
        report["chapters_sequential"] = False
        report["missing_chapters"] = sorted(list(set(expected_nums) - set(found_nums)))
        
        from collections import Counter
        counts = Counter(found_nums)
        report["duplicate_chapters"] = [num for num, count in counts.items() if count > 1]
        
    # Check formatting issues
    if "\n# " not in text and not text.startswith("# "):
        report["format_issues"].append("Missing main title H1 heading")
        
    if "## 目录" not in text:
        report["format_issues"].append("Missing Table of Contents")
        
    report["passed"] = (
        report["chapter_headings_found"] == 60 and
        report["chapters_sequential"] and
        len(report["format_issues"]) == 0
    )
    
    (qa_dir / "final_qa_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
