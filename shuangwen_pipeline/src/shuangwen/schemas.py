"""强类型数据契约：锁定各模型之间的数据交接格式。

图状态中只存放 ``model_dump()`` 后的 dict（便于 checkpoint 序列化），
节点在读取时再用这些 Schema 校验还原。
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

BranchCode = Literal["2A", "2B", "2C"]
BRANCH_CODES: tuple[str, ...] = ("2A", "2B", "2C")
BRANCH_FULL_NAMES: dict[str, str] = {
    "2A": "2A_Conservative",
    "2B": "2B_Reconstructed",
    "2C": "2C_Radical",
}
BRANCH_LABELS: dict[str, str] = {
    "2A": "策略1：保核改写",
    "2B": "策略2：保值重建",
    "2C": "策略3：种子重创",
}
SceneTag = Literal["normal_shuang", "dense_banter", "intimate_tension"]


def normalize_branch(value: str) -> str:
    """把 '2B' / '2B_Reconstructed' / 'B' / '方案B' 统一为 '2B'。"""
    v = str(value).strip().upper()
    for code in BRANCH_CODES:
        if v.startswith(code.upper()):
            return code
    for code in BRANCH_CODES:
        letter = code[1]
        if v in {letter, f"方案{letter}", f"策略{letter}"}:
            return code
    raise ValueError(f"无法识别的分支标识：{value!r}")


# ---------------------------------------------------------------------------
# Node 1：语义剥离与爽文药检
# ---------------------------------------------------------------------------


class GenreSeed(BaseModel):
    background: str = Field(description="时代背景与行业领域")
    core_trope: str = Field(description="核心爽文母题")
    protagonist_hook: str = Field(description="主角金手指或核心底牌")


class CharacterAsset(BaseModel):
    name: str
    role: str = Field(description="定位")
    core_trait: str = Field(description="最具魅力的反差感或高光点")


class StoryValueAssets(BaseModel):
    characters: list[CharacterAsset]
    key_relationships: str = Field(description="不可破坏的核心人物张力与互动模式")
    emotional_highlights: str = Field(description="原稿中最值得保留的情绪瞬间")


class OriginalEvent(BaseModel):
    chapter: int
    events: str


class AntiShuangwenDiagnosis(BaseModel):
    grievance_points: list[str] = Field(description="原稿憋屈点诊断")
    missing_elements: list[str] = Field(description="缺失的爽点要素")


class StoryAssetsSchema(BaseModel):
    genre_seed: GenreSeed
    story_value_assets: StoryValueAssets
    original_event_chain: list[OriginalEvent] = Field(
        description="原Ch1-3事件链，在策略2/3中将被物理隔离"
    )
    anti_shuangwen_diagnosis: AntiShuangwenDiagnosis


# ---------------------------------------------------------------------------
# Node 2：三路赛马
# ---------------------------------------------------------------------------


class ChapterScenePlan(BaseModel):
    chapter_num: int
    title: str
    scenes: list[str] = Field(description="分场骨架，每条一个场景：谁、在哪、冲突、怎么打脸")
    chapter_hook: str = Field(description="章末钩子")


class BranchSkeleton(BaseModel):
    mainline_preview: str = Field(description="60章主线三幕高潮预览（约300字）")
    chapters: list[ChapterScenePlan]


class BranchCandidate(BaseModel):
    branch: BranchCode
    label: str
    story_card: str = ""
    mainline_preview: str = ""
    skeleton: BranchSkeleton | None = None
    chapters: dict[str, str] = Field(default_factory=dict, description="章号(str) -> 正文")
    titles: dict[str, str] = Field(default_factory=dict)
    guardrail_hits: list[str] = Field(default_factory=list)

    def full_text(self) -> str:
        parts = []
        for key in sorted(self.chapters, key=int):
            title = self.titles.get(key, "")
            parts.append(f"### 第{key}章 {title}".rstrip() + "\n\n" + self.chapters[key])
        return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# Node 3：量化评审
# ---------------------------------------------------------------------------


class BranchEvaluation(BaseModel):
    branch_id: Literal["2A_Conservative", "2B_Reconstructed", "2C_Radical"]
    zero_grievance_score: int = Field(ge=0, le=20, description="零憋屈度得分，有低头认错直接扣15分")
    villain_punchability: int = Field(ge=0, le=20, description="反派欠揍度与拉仇恨速度")
    payoff_velocity: int = Field(ge=0, le=25, description="爽点当量与前三章兑现速度")
    colloquial_humor_density: int = Field(ge=0, le=20, description="市井大白话与神比喻密度")
    cliffhanger_pull: int = Field(ge=0, le=15, description="第3章章末钩子拉力")
    total_score: int = 0
    highlight_snippet: str = Field(description="该版本最炸裂的一段原味切片")
    fatal_flaw_warning: str = Field(description="潜在劝退毒点预警")

    @field_validator("branch_id", mode="before")
    @classmethod
    def _normalize_branch_id(cls, v: str) -> str:
        return BRANCH_FULL_NAMES[normalize_branch(v)]

    @model_validator(mode="after")
    def _recompute_total(self) -> "BranchEvaluation":
        # 总分永远由五维分数重新计算，不信任模型自报的加法
        self.total_score = (
            self.zero_grievance_score
            + self.villain_punchability
            + self.payoff_velocity
            + self.colloquial_humor_density
            + self.cliffhanger_pull
        )
        return self

    @property
    def code(self) -> str:
        return normalize_branch(self.branch_id)


class JudgeReport(BaseModel):
    evaluations: list[BranchEvaluation]
    comparison_markdown: str = Field(description="五维评分对比表 + 诊断（Markdown）")
    recommended_branch: Literal["2A_Conservative", "2B_Reconstructed", "2C_Radical"]
    recommendation: str = Field(description="主编最终选品建议，可含缝合建议")

    @field_validator("recommended_branch", mode="before")
    @classmethod
    def _normalize_recommended(cls, v: str) -> str:
        return BRANCH_FULL_NAMES[normalize_branch(v)]

    def by_code(self) -> dict[str, BranchEvaluation]:
        return {e.code: e for e in self.evaluations}


# ---------------------------------------------------------------------------
# 人工定标
# ---------------------------------------------------------------------------


class HumanSelection(BaseModel):
    winning_branch: BranchCode
    notes: str = Field(default="", description="人工批注，会传给节拍器作为额外指令")
    override_chapters: dict[str, str] = Field(
        default_factory=dict, description="人工直接改过的 Ch1-3 正文（章号 -> 正文）"
    )

    @field_validator("winning_branch", mode="before")
    @classmethod
    def _normalize(cls, v: str) -> str:
        return normalize_branch(v)


# ---------------------------------------------------------------------------
# Node 4：60章节拍细纲
# ---------------------------------------------------------------------------


class ChapterBeat(BaseModel):
    chapter_num: int
    title: str
    scene_tags: list[SceneTag] = Field(default_factory=lambda: ["normal_shuang"])
    core_conflict: str = Field(description="本章具体挑衅者或奇葩阻碍")
    comic_shuang_action: str = Field(description="主角不讲武德的骚操作或专业降维打击")
    payoff_and_hook: str = Field(description="即时震惊反馈与章末悬念")
    hard_stop_boundary: str = Field(description="【防越界红线】本章绝对禁止写到的后续剧情点")

    @field_validator("scene_tags", mode="before")
    @classmethod
    def _filter_tags(cls, v):
        allowed = {"normal_shuang", "dense_banter", "intimate_tension"}
        tags = [t for t in (v or []) if t in allowed]
        return tags or ["normal_shuang"]


class ArcOutline(BaseModel):
    arc_index: int
    arc_theme: str
    arc_summary: str = Field(description="本卷立靶子→蓄力整活→小高潮→掀桌大高潮→开宝箱换地图 的概述")
    chapters: list[ChapterBeat]


# ---------------------------------------------------------------------------
# Node 5：滚动连载
# ---------------------------------------------------------------------------


class GlobalStateCard(BaseModel):
    current_chapter: int
    protagonist_assets: str = Field(description="当前资金池、持有剧本/道具、行业声望")
    character_status: dict[str, str] = Field(description="核心配角当前状态与关系进展")
    active_villains: list[str] = Field(description="仇恨账本：已出场待打脸或持续迫害的反派")
    used_tropes_blacklist: list[str] = Field(description="近5章已使用的夸张比喻/热梗黑名单，严禁重复")


class InitialContext(BaseModel):
    state_card: GlobalStateCard
    style_anchors: list[str] = Field(description="黄金三章中最好笑的3个原文段落，作为语感锚点")


class ChapterStateUpdate(BaseModel):
    state_card: GlobalStateCard
    new_tropes: list[str] = Field(description="本章新使用的夸张比喻/热梗（3个）")


class ParagraphRewrite(BaseModel):
    paragraph_index: int
    text: str


class LocalRewriteResult(BaseModel):
    rewrites: list[ParagraphRewrite]


class ChapterReport(BaseModel):
    chapter_num: int
    char_count: int
    expanded: bool = False
    guardrail_rounds: int = 0
    residual_hits: list[str] = Field(default_factory=list)
    slices_used: list[str] = Field(default_factory=list)
    slice_errors: list[str] = Field(default_factory=list)
