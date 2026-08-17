#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from openai import OpenAI


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="使用长上下文模型综合原稿分析，生成改写圣经。")
    parser.add_argument("--task-dir", required=True)
    parser.add_argument("--model", default="gemini-3.1-pro-preview")
    return parser.parse_args()


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def main() -> None:
    args = parse_args()
    task_dir = Path(args.task_dir)
    catalog = json.loads(read(task_dir / "metadata" / "model_catalog.json"))
    model_ids = {item["id"] for item in catalog.get("data", [])}
    if args.model not in model_ids:
        raise SystemExit(f"实时模型目录中不存在模型：{args.model}")

    source_stats = read(task_dir / "analysis" / "source_statistics.json")
    plot_chain = read(task_dir / "analysis" / "plot_chain_30_segments.md")
    characters = read(task_dir / "analysis" / "character_state_by_pack.md")
    worldbuilding = read(task_dir / "analysis" / "worldbuilding_by_pack.md")
    continuity = read(task_dir / "analysis" / "continuity_register.md")
    style_features = read(task_dir / "analysis" / "style_features_by_pack.md")
    style_samples = read(task_dir / "analysis" / "style_sample_corpus.md")

    system = (
        "你是负责长篇中文网文改编的总编辑、设定编辑和连续性编辑。"
        "你只能使用用户原稿及其分析材料中的事实，不得添加外部事实，不得自行补完原稿未完结的主线。"
        "你的任务不是写正文，而是建立一份能约束60章改写全过程的权威故事圣经。"
        "请用专业、清晰、信息密集的简体中文Markdown输出。"
    )
    prompt = f"""# 任务目标

把用户提供的270章原稿严格重组为60章。原稿每9章对应目标2章，共30个连续分包。需要保留剧情事实、人物动机、世界规则、黑色幽默机制、升级反馈与章末钩子，同时避免机械复制长段原句。请综合以下全量材料，输出一份**权威改写圣经**。

# 必须输出的章节

1. **改写边界与总原则**：说明只覆盖所给270章、结尾必须停在原稿现有悬念，不得擅自补完。
2. **作品定位与核心承诺**：题材、主角欲望、读者爽点、荒诞讽刺对象、主线驱动力。
3. **叙事指纹矩阵**：至少12项，每项包括“特征、原稿表现、叙事作用、60章改写执行规则、禁忌”。重点分析短句、对白、反问、递进、重复、数值面板、社会制度反讽、章末钩子、配角侧写、冲突升级等。
4. **量化文风基线**：依据统计与样本给出每目标章推荐字数、场景数、对白占比、面板出现频率、反转数、钩子强度；明确这些是改写基线而非原稿绝对值。
5. **世界观与制度总表**：星界、人族联盟、教育、就业、贷款、药厂、试药、比赛、院校、执法、黑市等，逐项写清规则与荒诞逻辑。
6. **力量体系与数值纪律**：境界、三项数值、功法、武技、药物、食补、天赋、副作用、突破条件；对不确定数值标注“需回查原章”，不得臆造。
7. **人物圣经**：王哲、王猛、赵美玲、喻宇飞、雷老师及后续重要人物和组织。写明身份、目标、缺陷、能力、关系、关键转折、当前状态、不可写错事项。
8. **全书30段剧情时间线**：按分包01至30列出原章节范围、目标章节范围、核心事件、角色状态变化、必须带入下一段的事实。
9. **伏笔、债务、资源、伤势与敌友关系总账**：按首次出现、变化节点、在原稿第270章时的状态组织。
10. **60章改写的连续性规则**：每章开头承接、数值报账、资金流、功法进度、时间流逝、人物知情边界、组织态度等。
11. **语言与场景写作手册**：开场模板、对话节奏、信息植入、动作描写、笑点构造、面板展示、章末钩子；给出抽象示例，禁止长段复刻样本文字。
12. **风险清单与终审核对表**：至少20项，覆盖人物、数值、财务、时间、设定、风格、压缩失真与未完结边界。

# 原稿统计

{source_stats}

# 全书30段剧情链

{plot_chain}

# 分包人物状态

{characters}

# 分包世界观设定

{worldbuilding}

# 连续性事实与风险

{continuity}

# 分包文风特征

{style_features}

# 等距抽样文风语料

{style_samples}
"""

    prompt_path = task_dir / "logs" / "synthesize_story_bible_prompt.md"
    prompt_path.write_text(prompt, encoding="utf-8")

    client = OpenAI(timeout=900.0, max_retries=2)
    response = client.chat.completions.create(
        model=args.model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        max_tokens=16000,
    )
    content = response.choices[0].message.content or ""
    if len(content) < 5000:
        raise RuntimeError(f"故事圣经输出异常偏短：{len(content)}字符")

    output = task_dir / "analysis" / "story_bible.md"
    output.write_text(content.strip() + "\n", encoding="utf-8")
    (task_dir / "logs" / "synthesize_story_bible_response.json").write_text(
        response.model_dump_json(indent=2), encoding="utf-8"
    )
    usage = {
        "model_requested": args.model,
        "model_returned": response.model,
        "finish_reason": response.choices[0].finish_reason,
        "prompt_tokens": getattr(response.usage, "prompt_tokens", None),
        "completion_tokens": getattr(response.usage, "completion_tokens", None),
        "total_tokens": getattr(response.usage, "total_tokens", None),
        "output_characters": len(content),
    }
    (task_dir / "logs" / "synthesize_story_bible_usage.json").write_text(
        json.dumps(usage, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(usage, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
