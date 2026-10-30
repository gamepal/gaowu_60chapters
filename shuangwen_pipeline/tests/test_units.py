import pytest
from pydantic import BaseModel

from shuangwen.config import PipelineSettings, Role, arc_theme
from shuangwen.guardrails import count_cjk, enforce, parse_cn_number, scan, split_chapters, strip_leading_heading
from shuangwen.llm import LLMClient, StructuredOutputError, extract_json
from shuangwen.nodes.stage3 import merge_blacklist
from shuangwen.schemas import BranchEvaluation, HumanSelection, normalize_branch
from shuangwen.config import default_routes
from conftest import SpyBackend


def test_scan_detects_translationese_and_grievance():
    text = "他嘴角勾起一抹弧度。\n正常的一句。\n她耸了耸肩。\n眼神中闪过一丝复杂\n噢，老天！\n主角陪着笑脸说：好的好的"
    rules = {h.rule for h in scan(text)}
    assert {"嘴角勾起", "耸肩", "眼神闪过一丝", "噢老天", "赔笑低头"} <= rules
    assert all(h.paragraph_index != 1 for h in scan(text))


def test_split_chapters_and_numbers():
    pre, ch, titles = split_chapters("【人设卡】x\n### 第一章 开局\n正文1\n## 第2章：打脸\n正文2\n第十二章 尾声\n正文12")
    assert pre == "【人设卡】x"
    assert ch == {"1": "正文1", "2": "正文2", "12": "正文12"}
    assert titles["2"] == "打脸"
    assert parse_cn_number("二十三") == 23 and parse_cn_number("十") == 10 and parse_cn_number("６０") == 60
    assert strip_leading_heading("### 第4章 标题\n\n正文") == "正文"


def test_count_cjk():
    assert count_cjk("你好，world！再见") == 4


def test_branch_evaluation_recomputes_total_and_normalizes():
    e = BranchEvaluation(
        branch_id="B", zero_grievance_score=19, villain_punchability=20, payoff_velocity=24,
        colloquial_humor_density=18, cliffhanger_pull=15, total_score=1, highlight_snippet="x", fatal_flaw_warning="y",
    )
    assert e.total_score == 96 and e.branch_id == "2B_Reconstructed" and e.code == "2B"
    with pytest.raises(ValueError):
        BranchEvaluation(branch_id="2A", zero_grievance_score=21, villain_punchability=0, payoff_velocity=0,
                         colloquial_humor_density=0, cliffhanger_pull=0, highlight_snippet="", fatal_flaw_warning="")
    assert HumanSelection.model_validate({"winning_branch": "方案C"}).winning_branch == "2C"
    with pytest.raises(ValueError):
        normalize_branch("2D")


def test_settings_validation_and_arc_theme():
    assert PipelineSettings.from_dict({}).n_arcs == 5
    with pytest.raises(ValueError):
        PipelineSettings.from_dict({"total_chapters": 50, "arc_size": 12})
    assert "终极决战" in arc_theme(1, 2)
    assert "新手村" in arc_theme(0, 2)


def test_merge_blacklist_dedupes_and_truncates():
    out = merge_blacklist(["a", "b", "c"], ["b", "d", ""], keep=3)
    assert out == ["c", "b", "d"]


def test_extract_json():
    assert extract_json('好的：\n```json\n{"a": 1}\n```') == '{"a": 1}'
    assert extract_json('前缀 {"a": {"b": 2}} 后缀') == '{"a": {"b": 2}}'
    with pytest.raises(StructuredOutputError):
        extract_json("没有 JSON")


class _Tiny(BaseModel):
    n: int


async def test_structured_repairs_invalid_output():
    outputs = iter(['{"n": "not int"}', '{"n": 3}'])
    spy = SpyBackend(overrides={"t": lambda meta: next(outputs)})
    llm = LLMClient(spy, default_routes())
    assert (await llm.structured(Role.LIGHT, [{"role": "user", "content": "x"}], _Tiny, task="t")).n == 3
    second = spy.messages["t"][1]["messages"]
    assert second[-1]["role"] == "user" and "校验" in second[-1]["content"]
    assert "JSON Schema" in second[0]["content"]


async def test_structured_gives_up():
    llm = LLMClient(SpyBackend(overrides={"t": "nope"}), default_routes(), max_repair_attempts=1)
    with pytest.raises(StructuredOutputError):
        await llm.structured(Role.LIGHT, [{"role": "user", "content": "x"}], _Tiny, task="t")


async def test_enforce_rewrites_only_bad_paragraphs(llm, spy):
    text = "第一段正常。\n他耸了耸肩。\n第三段正常。"
    fixed, rounds, residual = await enforce(llm, text)
    assert rounds == 1 and residual == []
    assert fixed.split("\n")[0] == "第一段正常。" and "耸" not in fixed
    assert spy.messages["local_rewrite"][0]["meta"]["paragraph_indexes"] == "1"


def test_cache_control_only_when_route_enables_it(llm):
    writer = llm.route(Role.WRITER)
    msg = llm.system_message("bundle", route=writer, cache=True)
    assert msg["content"][0]["cache_control"]["type"] == "ephemeral"
    assert llm.system_message("x", route=llm.route(Role.ARCHITECT), cache=True) == {"role": "system", "content": "x"}
