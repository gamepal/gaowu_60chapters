"""离线 Mock 后端：不调用任何真实 API，按 task 返回格式合法的确定性输出。

用于本地跑通全链路、演示 Web Studio 与单元测试（SW_MOCK_LLM=1 或 --mock）。
"""

from __future__ import annotations

import asyncio
import json
import re

from .llm import Completion

_LINES = [
    "王胖子把烤串往桌上一拍，油点子溅了反派一脸。",
    "“你这剧本？我家楼下大爷拿脚写都比你强！”",
    "围观群众的下巴齐刷刷掉了一地，捡都捡不过来。",
    "主角眼皮都没抬：“行，赌就赌，输了你绕操场爬三圈，边爬边学鸭叫。”",
    "反派脸绿得跟刚腌好的黄瓜似的。",
    "兄弟在旁边憋笑憋得浑身发抖，跟开了震动模式一样。",
    "三分钟后，整个论坛炸了。",
    "评论区一水儿的“卧槽”，刷得服务器直冒烟。",
    "系主任推了推眼镜，手里的保温杯都拿不稳了。",
    "“这镜头……谁拍的？”",
]


def _prose(n_chars: int, seed: int = 0) -> str:
    out: list[str] = []
    i = seed
    while sum(len(x) for x in out) < n_chars:
        out.append(_LINES[i % len(_LINES)])
        i += 1
    return "\n".join(out)


def _user_text(messages) -> str:
    for m in reversed(messages):
        if m["role"] == "user":
            return m["content"] if isinstance(m["content"], str) else ""
    return ""


class MockBackend:
    def __init__(self, delay: float = 0.0):
        self.delay = delay
        self.calls: list[str] = []

    async def complete(self, *, task, route, messages, schema, meta) -> Completion:
        self.calls.append(task)
        if self.delay:
            await asyncio.sleep(self.delay)
        handler = getattr(self, f"_t_{re.sub(r'[^a-zA-Z0-9]', '_', task)}", None)
        if handler is None and task.startswith(("prose_", "skeleton_")):
            handler = getattr(self, f"_t_{task.split('_')[0]}")
        if handler is None:
            raise KeyError(f"MockBackend 未实现 task={task}")
        out = handler(messages=messages, meta=meta, task=task)
        text = out if isinstance(out, str) else json.dumps(out, ensure_ascii=False)
        return Completion(text=text, prompt_tokens=100, completion_tokens=len(text))

    # ---- Node 1 ----
    def _t_extract(self, **_):
        return {
            "genre_seed": {"background": "平行世界千禧年·影视学院导演系", "core_trope": "文抄公降维打击", "protagonist_hook": "脑子里装着未来二十年的爆款剧本"},
            "story_value_assets": {
                "characters": [
                    {"name": "陈默", "role": "主角", "core_trait": "嘴贱心黑、专业满级"},
                    {"name": "夏燃", "role": "兄弟", "core_trait": "嘴硬心软偷卖跑车支持兄弟的富二代"},
                    {"name": "艾小艾", "role": "青梅", "core_trait": "为主角退组力挺的女主"},
                ],
                "key_relationships": "铁三角护短",
                "emotional_highlights": "夏燃偷偷卖车凑钱",
            },
            "original_event_chain": [{"chapter": i, "events": f"原第{i}章：内部看剧本"} for i in (1, 2, 3)],
            "anti_shuangwen_diagnosis": {"grievance_points": ["向甲方低头改稿"], "missing_elements": ["无欠揍反派", "第3章无即时回馈"]},
        }

    # ---- Node 2 ----
    def _t_skeleton(self, task, **_):
        return {
            "mainline_preview": f"[{task}] 三幕：校园立威 → 全网爆火 → 封神收官。",
            "chapters": [
                {"chapter_num": i, "title": f"骨架第{i}章", "scenes": ["反派堵门", "当场反咬"], "chapter_hook": "论坛炸了"}
                for i in (1, 2, 3)
            ],
        }

    def _t_prose(self, task, **_):
        branch = task.split("_", 1)[1]
        head = ""
        if branch == "2C":
            head = "【新故事人设卡】\n主角：一心想亏钱的倒霉蛋\n【60章主线三幕高潮预览】\n越亏越赚，全员脑补。\n"
        body = "\n".join(f"### 第{i}章 {branch}的第{i}章\n{_prose(1300, i)}" for i in (1, 2, 3))
        return head + body

    # ---- Node 3 ----
    def _t_judge(self, messages, **_):
        user = _user_text(messages)
        present = [c for c in ("2A_Conservative", "2B_Reconstructed", "2C_Radical") if c in user]
        scores = {"2A_Conservative": (16, 15, 17, 18, 12), "2B_Reconstructed": (19, 20, 24, 18, 15), "2C_Radical": (20, 18, 22, 19, 14)}
        return {
            "evaluations": [
                {
                    "branch_id": b,
                    "zero_grievance_score": scores[b][0],
                    "villain_punchability": scores[b][1],
                    "payoff_velocity": scores[b][2],
                    "colloquial_humor_density": scores[b][3],
                    "cliffhanger_pull": scores[b][4],
                    "total_score": 0,
                    "highlight_snippet": _LINES[3],
                    "fatal_flaw_warning": "中段可能注水",
                }
                for b in present
            ],
            "comparison_markdown": "| 维度 | A | B | C |\n|---|---|---|---|\n| 总分 | 78 | 96 | 93 |",
            "recommended_branch": "2B_Reconstructed" if "2B_Reconstructed" in present else present[0],
            "recommendation": "推荐方案B进入60章量产。",
        }

    # ---- 状态卡 ----
    def _t_init_context(self, **_):
        return {
            "state_card": {
                "current_chapter": 3,
                "protagonist_assets": "账户余额4.2万，持有先导片",
                "character_status": {"夏燃": "跑车已卖", "艾小艾": "已退组力挺"},
                "active_villains": ["曾毅"],
                "used_tropes_blacklist": ["眼珠子捐角膜", "老年机震动"],
            },
            "style_anchors": [_LINES[1], _LINES[4], _LINES[5]],
        }

    def _t_state_update(self, messages, meta, **_):
        n = meta.get("chapter", 0)
        return {
            "state_card": {
                "current_chapter": n,
                "protagonist_assets": f"第{n}章后账户余额{n * 10}万",
                "character_status": {"夏燃": f"第{n}章状态"},
                "active_villains": ["曾毅"],
                "used_tropes_blacklist": [],
            },
            "new_tropes": [f"第{n}章梗{i}" for i in range(1, 4)],
        }

    # ---- Node 4 ----
    def _t_plan_arc(self, meta, **_):
        start, end = meta["start"], meta["end"]
        chapters = []
        for n in range(start, end + 1):
            tags = ["normal_shuang"]
            if n % 5 == 0:
                tags.append("dense_banter")
            if n % 7 == 0:
                tags.append("intimate_tension")
            chapters.append(
                {
                    "chapter_num": n,
                    "title": f"第{n}章：反派又双叒叕破防了",
                    "scene_tags": tags,
                    "core_conflict": f"第{n}章的势利眼挑衅",
                    "comic_shuang_action": f"第{n}章主角不讲武德的骚操作",
                    "payoff_and_hook": f"第{n}章全场石化，章末悬念",
                    "hard_stop_boundary": f"不得写到第{n + 1}章的核心事件",
                }
            )
        return {"arc_index": meta["arc_index"], "arc_theme": "", "arc_summary": "立靶子→整活→高潮→换地图", "chapters": chapters}

    # ---- Node 5 ----
    def _t_banter_slice(self, **_):
        return "\n".join(f"{'甲' if i % 2 else '乙'}：第{i}句互损" for i in range(30))

    def _t_intimate_slice(self, **_):
        return "两人隔着一张桌子较劲，谁都不肯先移开视线。"

    def _t_write_chapter(self, meta, **_):
        n = meta.get("chapter", 0)
        # 第 4 章故意写短，以覆盖“字数校准扩写”路径
        return _prose(1500 if n == 4 else 3200, n)

    def _t_expand_chapter(self, meta, **_):
        return _prose(3300, meta.get("chapter", 0))

    def _t_local_rewrite(self, meta, **_):
        idx = [int(i) for i in str(meta.get("paragraph_indexes", "")).split(",") if i]
        return {"rewrites": [{"paragraph_index": i, "text": "他乐得跟捡了钱包似的。"} for i in idx]}
