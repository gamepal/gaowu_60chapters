"""输出护栏：毫秒级正则拦截（防翻译腔 / 防憋屈）+ 局部重写 + 字数校准工具。"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .config import Role
from .llm import LLMClient
from .prompts import LOCAL_REWRITE_PROMPT, PROMPT_STYLE_BIBLE_COLLOQUIAL, dumps
from .schemas import LocalRewriteResult

# (规则名, 正则)。命中任意一条即触发局部重写。
TRANSLATIONESE_RULES: list[tuple[str, str]] = [
    ("嘴角勾起", r"嘴角(?:微微|轻轻)?(?:勾起|上扬|扬起)(?:一抹|一丝|一个)?"),
    ("耸肩", r"耸了?耸(?:肩|肩膀)"),
    ("眼神闪过一丝", r"(?:眼神|眼中|眼底|眸中|眼里)(?:中)?(?:闪过|划过|掠过)一(?:丝|抹)"),
    ("噢老天", r"(?:噢|哦|喔)[，,、！!\s]*(?:我的)?(?:老天|天哪|上帝)"),
    ("我的上帝", r"我的上帝"),
    ("一抹弧度", r"一抹(?:玩味|意味深长|若有若无)?的?(?:弧度|笑意)"),
    ("该死的", r"该死的[^，。！？\n]{0,6}(?:家伙|东西)"),
    ("不由得倒吸", r"不由得?倒吸一口(?:凉|冷)气"),
]

GRIEVANCE_RULES: list[tuple[str, str]] = [
    ("赔笑低头", r"(?:陪|赔)着?笑脸?(?:说|道|解释)"),
    ("低头认错", r"(?:低头认错|低声下气|点头哈腰地?(?:道歉|认错))"),
    ("主角求饶", r"求求(?:您|你)(?:了)?[，,]?(?:再)?(?:给|宽限|通融)"),
]

_COMPILED = [(name, re.compile(pat)) for name, pat in TRANSLATIONESE_RULES + GRIEVANCE_RULES]
_CJK_RE = re.compile(r"[一-鿿]")


@dataclass
class GuardrailHit:
    paragraph_index: int
    rule: str
    match: str


def count_cjk(text: str) -> int:
    return len(_CJK_RE.findall(text))


def split_paragraphs(text: str) -> list[str]:
    return [p for p in text.split("\n")]


def scan(text: str) -> list[GuardrailHit]:
    hits: list[GuardrailHit] = []
    for idx, para in enumerate(split_paragraphs(text)):
        for name, rx in _COMPILED:
            m = rx.search(para)
            if m:
                hits.append(GuardrailHit(idx, name, m.group(0)))
    return hits


def describe_hits(hits: list[GuardrailHit]) -> list[str]:
    return [f"{h.rule}:{h.match}" for h in hits]


async def enforce(
    llm: LLMClient,
    text: str,
    *,
    max_rounds: int = 2,
    task: str = "local_rewrite",
    meta: dict | None = None,
) -> tuple[str, int, list[GuardrailHit]]:
    """扫描 → 只把命中的段落发给主笔模型局部重写 → 再扫描，最多 max_rounds 轮。

    返回 (修正后的文本, 实际重写轮数, 残留命中)。
    """
    rounds = 0
    hits = scan(text)
    while hits and rounds < max_rounds:
        rounds += 1
        paragraphs = split_paragraphs(text)
        bad_idx = sorted({h.paragraph_index for h in hits})
        items = dumps(
            [
                {
                    "paragraph_index": i,
                    "text": paragraphs[i],
                    "violations": [h.match for h in hits if h.paragraph_index == i],
                }
                for i in bad_idx
            ]
        )
        result = await llm.structured(
            Role.WRITER,
            [
                {"role": "system", "content": PROMPT_STYLE_BIBLE_COLLOQUIAL},
                {"role": "user", "content": LOCAL_REWRITE_PROMPT.format(items=items)},
            ],
            LocalRewriteResult,
            task=task,
            meta={**(meta or {}), "paragraph_indexes": ",".join(map(str, bad_idx))},
        )
        allowed = set(bad_idx)
        for rw in result.rewrites:
            if rw.paragraph_index in allowed:
                paragraphs[rw.paragraph_index] = rw.text.replace("\n\n", "\n").strip("\n")
        text = "\n".join(paragraphs)
        hits = scan(text)
    return text, rounds, hits


_HEADING_RE = re.compile(r"^\s*#{0,4}\s*第\s*([0-9０-９一二三四五六七八九十百零〇两]+)\s*章[\s:：·、-]*(.*)$")
_CN_DIGITS = {"零": 0, "〇": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}


def parse_cn_number(s: str) -> int:
    s = s.translate(str.maketrans("０１２３４５６７８９", "0123456789"))
    if s.isdigit():
        return int(s)
    total, section = 0, 0
    for ch in s:
        if ch in _CN_DIGITS:
            section = _CN_DIGITS[ch]
        elif ch == "十":
            total += (section or 1) * 10
            section = 0
        elif ch == "百":
            total += (section or 1) * 100
            section = 0
    return total + section


def split_chapters(text: str) -> tuple[str, dict[str, str], dict[str, str]]:
    """按“### 第N章 标题”切分。返回 (首个章节标题前的前言, 正文{章号:正文}, 标题{章号:标题})。"""
    preamble: list[str] = []
    bodies: dict[str, list[str]] = {}
    titles: dict[str, str] = {}
    current: str | None = None
    for line in text.splitlines():
        m = _HEADING_RE.match(line)
        if m and len(line) < 60:
            current = str(parse_cn_number(m.group(1)))
            titles[current] = m.group(2).strip().strip("#*《》 ")
            bodies[current] = []
            continue
        (bodies[current] if current else preamble).append(line)
    return (
        "\n".join(preamble).strip(),
        {k: "\n".join(v).strip() for k, v in bodies.items()},
        titles,
    )


def strip_leading_heading(text: str) -> str:
    lines = text.strip().splitlines()
    while lines and (_HEADING_RE.match(lines[0]) and len(lines[0]) < 60 or not lines[0].strip()):
        lines.pop(0)
    return "\n".join(lines).strip()
