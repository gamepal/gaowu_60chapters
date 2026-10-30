"""把运行结果落盘为 Markdown / JSON。"""

from __future__ import annotations

import json
from pathlib import Path

from .schemas import BRANCH_LABELS, JudgeReport


def render_book(state: dict) -> str:
    titles = state.get("chapter_titles", {})
    chapters = state.get("chapters_text", {})
    parts = [f"# {state.get('title') or '未命名'}\n"]
    for key in sorted(chapters, key=int):
        parts.append(f"## 第{key}章 {titles.get(key, '')}".rstrip() + "\n\n" + chapters[key].strip() + "\n")
    return "\n".join(parts)


def render_judge_report(state: dict) -> str:
    if not state.get("judge_report"):
        return ""
    report = JudgeReport.model_validate(state["judge_report"])
    lines = ["# 三路赛马评审报告\n", report.comparison_markdown.strip(), "\n## 分项得分\n"]
    lines.append("| 方案 | 零憋屈 | 反派欠揍 | 爽点兑现 | 大白话密度 | 章末钩子 | 总分 |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|")
    for e in report.evaluations:
        lines.append(
            f"| {BRANCH_LABELS[e.code]} | {e.zero_grievance_score} | {e.villain_punchability} | {e.payoff_velocity} "
            f"| {e.colloquial_humor_density} | {e.cliffhanger_pull} | **{e.total_score}** |"
        )
    for e in report.evaluations:
        lines += [f"\n### {BRANCH_LABELS[e.code]}", f"**高光切片**：\n\n> {e.highlight_snippet}", f"\n**毒点预警**：{e.fatal_flaw_warning}"]
    lines += ["\n## 主编选品建议\n", f"推荐：{report.recommended_branch}\n", report.recommendation]
    if state.get("winning_branch"):
        lines.append(f"\n**人工钦定**：{BRANCH_LABELS[state['winning_branch']]}")
    return "\n".join(lines) + "\n"


def export_run(state: dict, output_dir: str) -> Path:
    root = Path(output_dir) / state["run_id"]
    chapters_dir = root / "chapters"
    chapters_dir.mkdir(parents=True, exist_ok=True)
    titles = state.get("chapter_titles", {})
    for key, text in state.get("chapters_text", {}).items():
        (chapters_dir / f"chapter_{int(key):02d}.md").write_text(
            f"# 第{key}章 {titles.get(key, '')}".rstrip() + "\n\n" + text.strip() + "\n", encoding="utf-8"
        )
    (root / "book.md").write_text(render_book(state), encoding="utf-8")
    (root / "judge_report.md").write_text(render_judge_report(state), encoding="utf-8")

    def dump(name: str, obj) -> None:
        (root / name).write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")

    dump("assets.json", state.get("extracted_assets"))
    dump("outline.json", state.get("outline_arcs"))
    dump("state_card.json", state.get("global_state_card"))
    dump("chapter_reports.json", state.get("chapter_reports"))
    candidates_dir = root / "candidates"
    candidates_dir.mkdir(exist_ok=True)
    for code, cand in state.get("candidates", {}).items():
        dump(f"candidates/{code}.json", cand)
    return root
