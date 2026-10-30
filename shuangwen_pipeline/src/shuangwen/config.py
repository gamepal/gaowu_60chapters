"""模型路由矩阵与运行配置。

每个算子角色（Role）绑定一个精确的模型版本与采样参数。所有值都可通过
环境变量覆盖，例如 ``SW_MODEL_ARCHITECT=anthropic/claude-opus-5-5``。
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field, replace
from enum import Enum


class Role(str, Enum):
    """算子角色。"""

    ARCHITECT = "architect"  # 结构总控 / 语义药检 / 毒舌裁判 / 节拍细纲
    WRITER = "writer"  # 正文主笔 / 本土化洗稿 / 长线防崩
    BANTER = "banter"  # 高密度嘴炮 / 群像对白切片
    INTIMATE = "intimate"  # 高张力亲密戏 / 修罗场切片
    LIGHT = "light"  # 热梗去重 / 状态卡提取


@dataclass(frozen=True)
class ModelRoute:
    model: str
    temperature: float
    top_p: float | None = None
    presence_penalty: float | None = None
    max_tokens: int | None = None
    # 为 True 时请求原生 JSON 输出（Gemini 映射为 response_mime_type=application/json）
    native_json: bool = False
    # 为 True 时对 system 前缀启用上下文缓存（Gemini CachedContent / Anthropic prompt cache）
    context_cache: bool = False

    def with_temperature(self, temperature: float | None) -> "ModelRoute":
        return self if temperature is None else replace(self, temperature=temperature)


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default)


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    return int(raw) if raw else default


# 采样温度：同一个 ARCHITECT 模型在不同节点使用不同温度
TEMP_EXTRACT = 0.1
TEMP_JUDGE = 0.1
TEMP_SKELETON_2A = 0.3
TEMP_SKELETON_2B = 0.5
TEMP_BEAT_PLANNER = 0.4
TEMP_RADICAL_2C = 0.9


def default_routes() -> dict[Role, ModelRoute]:
    cache = _env_bool("SW_GEMINI_CONTEXT_CACHE", True)
    return {
        # Claude 新版本不允许同时指定 temperature 与 top_p，因此此处只设 temperature
        Role.ARCHITECT: ModelRoute(
            model=_env("SW_MODEL_ARCHITECT", "anthropic/claude-opus-4-6"),
            temperature=0.1,
            max_tokens=_env_int("SW_ARCHITECT_MAX_TOKENS", 16000),
        ),
        Role.WRITER: ModelRoute(
            model=_env("SW_MODEL_WRITER", "gemini/gemini-2.5-pro"),
            temperature=0.85,
            top_p=0.95,
            max_tokens=_env_int("SW_WRITER_MAX_TOKENS", 32000),
            context_cache=cache,
        ),
        Role.BANTER: ModelRoute(
            model=_env("SW_MODEL_BANTER", "openai/gpt-4o-2024-11-20"),
            temperature=0.8,
            presence_penalty=0.3,
            max_tokens=4096,
        ),
        Role.INTIMATE: ModelRoute(
            model=_env("SW_MODEL_INTIMATE", "xai/grok-3-latest"),
            temperature=0.9,
            top_p=0.95,
            max_tokens=4096,
        ),
        Role.LIGHT: ModelRoute(
            model=_env("SW_MODEL_LIGHT", "gemini/gemini-2.5-flash"),
            temperature=0.1,
            native_json=True,
            max_tokens=8192,
        ),
    }


@dataclass
class PipelineSettings:
    """单次运行的业务参数（会写入图状态，随 checkpoint 持久化）。"""

    total_chapters: int = 60
    arc_size: int = 12
    golden_chapters: int = 3
    min_chars: int = 2200
    max_chars: int = 3200
    golden_min_chars: int = 1200
    tail_window_chars: int = 1500
    blacklist_size: int = 15
    max_guardrail_rewrites: int = 2

    def to_dict(self) -> dict:
        return dict(self.__dict__)

    @classmethod
    def from_dict(cls, data: dict | None) -> "PipelineSettings":
        data = data or {}
        known = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
        settings = cls(**known)
        if settings.total_chapters % settings.arc_size:
            raise ValueError("total_chapters 必须是 arc_size 的整数倍")
        if settings.total_chapters <= settings.golden_chapters:
            raise ValueError("total_chapters 必须大于黄金章节数")
        return settings

    @property
    def n_arcs(self) -> int:
        return self.total_chapters // self.arc_size


@dataclass
class AppSettings:
    """进程级配置：持久化、事件总线、输出目录等。"""

    routes: dict[Role, ModelRoute] = field(default_factory=default_routes)
    postgres_dsn: str | None = None
    sqlite_path: str | None = None
    redis_url: str | None = None
    output_dir: str | None = None
    cache_ttl_seconds: int = 7200
    request_timeout: float = 600.0
    num_retries: int = 3
    mock_llm: bool = False

    @classmethod
    def from_env(cls) -> "AppSettings":
        return cls(
            routes=default_routes(),
            postgres_dsn=os.environ.get("SW_POSTGRES_DSN") or None,
            sqlite_path=os.environ.get("SW_SQLITE_PATH") or None,
            redis_url=os.environ.get("SW_REDIS_URL") or None,
            output_dir=os.environ.get("SW_OUTPUT_DIR", "./output"),
            cache_ttl_seconds=_env_int("SW_CACHE_TTL_SECONDS", 7200),
            request_timeout=float(os.environ.get("SW_REQUEST_TIMEOUT", "600")),
            num_retries=_env_int("SW_NUM_RETRIES", 3),
            mock_llm=_env_bool("SW_MOCK_LLM", False),
        )


# 60章五幕微循环（每 12 章一个 Mini-Arc）
DEFAULT_ARC_THEMES: list[str] = [
    "新手村立威与草台班子逆袭（打脸贴身小人，赚取第一桶金与初始声望）",
    "作品/产品初次面世引爆局部圈层（打脸行业守门人/势利眼平台，身价暴涨十倍）",
    "同行大佬联合围剿与神级骚操作反杀（打脸省城/业内权威，配角团集体跟着鸡犬升天）",
    "跨界降维打击与名场面封神（国家级/全网级曝光，昔日高不可攀的巨鳄主动跪舔）",
    "终极决战、万众仰望与完美收官（清算终极BOSS，全员圆满，留下传说级番外钩子）",
]


def arc_theme(index: int, n_arcs: int) -> str:
    """返回第 index 卷（0 起）的主题。卷数不是 5 时按比例映射到五幕。"""
    if n_arcs == len(DEFAULT_ARC_THEMES):
        return DEFAULT_ARC_THEMES[index]
    if index == n_arcs - 1:
        return DEFAULT_ARC_THEMES[-1]
    mapped = min(int(index * len(DEFAULT_ARC_THEMES) / n_arcs), len(DEFAULT_ARC_THEMES) - 2)
    return DEFAULT_ARC_THEMES[mapped]
