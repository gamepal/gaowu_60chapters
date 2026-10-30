# 多智能体爽文生产系统（Shuangwen Pipeline）

LangGraph + FastAPI + Pydantic v2 + LiteLLM 实现的有状态网文生产流水线：

```
[原始Ch1-3] → Node1 语义剥离/药检 (Opus)
            → Node2 三路赛马并发 2A 保核改写 / 2B 保值重建 / 2C 种子重创
            → 去翻译腔终审（正则拦截 + 局部重写）
            → Node3 五维量化裁判 (Opus)
            → 🛑 人工钦定（interrupt，checkpoint 落库）
            → 初始化状态卡 + 语感锚点 (Flash)
            → Node4 5×12 章 Mini-Arc 细纲（含防越界锁）↺
            → Node5 Ch4-60 滚动连载 ↺
                 ├ dense_banter → GPT-4o 对白切片
                 ├ intimate_tension → Grok 亲密张力切片
                 ├ Gemini Pro 统稿（设定包走 Context Cache）
                 ├ 字数校准（<2200 字触发一次细节放大扩写）
                 ├ 防翻译腔/防憋屈拦截器（命中段落局部重写）
                 └ Flash 更新状态卡 + 热梗黑名单（保留最近 15 个）
            → 导出 Markdown / JSON
```

## 模型路由矩阵

| 角色 | 默认模型 | 采样 | 环境变量 |
|---|---|---|---|
| 结构总控/药检/裁判/细纲 | `anthropic/claude-opus-4-6` | 提取/裁判 0.1，2A 骨架 0.3，2B 骨架 0.5，细纲 0.4 | `SW_MODEL_ARCHITECT` |
| 正文主笔/洗稿/连载 | `gemini/gemini-2.5-pro` | 0.85 / top_p 0.95，2C 0.9，Context Cache | `SW_MODEL_WRITER` |
| 高密嘴炮切片 | `openai/gpt-4o-2024-11-20` | 0.8 / presence 0.3 | `SW_MODEL_BANTER` |
| 亲密张力切片 | `xai/grok-3-latest` | 0.9 / top_p 0.95 | `SW_MODEL_INTIMATE` |
| 状态卡/热梗去重 | `gemini/gemini-2.5-flash` | 0.1，JSON 模式 | `SW_MODEL_LIGHT` |

Claude 新版本不允许同时传 `temperature` 和 `top_p`，所以 ARCHITECT 只设温度。切片模型（GPT-4o / Grok）调用失败时只记入章节报告，不阻塞主线。

## 快速开始

```bash
cd shuangwen_pipeline
pip install -e ".[dev,sqlite]"      # Postgres: .[postgres]  Redis: .[redis]
cp .env.example .env                # 填入各家 API Key
```

离线演示（Mock 模型，不消耗 API）：

```bash
shuangwen run --input ch1-3.md --mock --select auto --sqlite ./data/cp.sqlite
```

真实运行，命令行交互式钦定胜出分支：

```bash
shuangwen run --input ch1-3.md --title 六十个未接来电 --sqlite ./data/cp.sqlite
```

断点续跑（进程崩溃或 API 报错后，从最近一次 checkpoint 继续，已完成的章节不会重写）：

```bash
shuangwen resume --run-id <run_id> --sqlite ./data/cp.sqlite
```

Web Studio（提交原稿 → 三路赛马看板 → 一键钦定 → 实时连载进度）：

```bash
shuangwen serve --port 8000          # 浏览器打开 http://127.0.0.1:8000
```

结果输出到 `output/<run_id>/`：`book.md`、`chapters/chapter_XX.md`、`judge_report.md`、`outline.json`、`state_card.json`、`chapter_reports.json`、`candidates/*.json`。

## HTTP API

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/runs` | `{raw_ch1_3, title, settings}` 创建任务，后台跑到人工断点 |
| GET | `/api/runs/{id}` | 状态 / 阶段 / 进度 / 用量 |
| GET | `/api/runs/{id}/board` | 三路赛马看板（资产诊断 + 候选正文 + 裁判报告） |
| POST | `/api/runs/{id}/selection` | `{winning_branch, notes, override_chapters}` 钦定并继续 |
| POST | `/api/runs/{id}/resume` | 失败/中断后断点续跑 |
| GET | `/api/runs/{id}/outline` | 分卷细纲 + 当前状态卡 |
| GET | `/api/runs/{id}/chapters[/{n}]` | 章节列表 / 单章正文 |
| GET | `/api/runs/{id}/export?kind=book\|judge` | 导出全书或评审报告 Markdown |
| GET | `/api/runs/{id}/events` | SSE 实时事件流 |

`settings` 可覆盖 `total_chapters`（默认 60，必须是 `arc_size` 的整数倍）、`arc_size`（12）、`min_chars`/`max_chars`（2200/3200）、`tail_window_chars`（1500）、`blacklist_size`（15）等，见 `config.PipelineSettings`。

## 持久化

- `SW_POSTGRES_DSN`：生产环境使用 `AsyncPostgresSaver` 保存 LangGraph checkpoint
- `SW_SQLITE_PATH`：单机持久化
- 两者都不设时使用内存（重启即丢失）
- `SW_REDIS_URL`：多 worker 部署时 SSE 事件走 Redis（List 存历史 + Pub/Sub 广播）

## 关键工程护栏

1. **权限隔离**：2B 的输入里物理剔除 `original_event_chain` 与原文；2C 只拿到 `genre_seed`（有测试覆盖）。
2. **结构化输出**：所有 JSON 节点都用 Pydantic 校验，失败时把校验错误回灌给模型修复，最多重试 2 次。裁判总分由五维分数重算，不信任模型自己做的加法；细纲章号强制连续。
3. **上下文缓存**：文风圣经、语感锚点、人物设定、黄金三章、全书细纲组成的设定包，在 Stage 3 期间逐字节不变，作为带 `cache_control` 的 system 前缀，由 LiteLLM 转成 Gemini CachedContent（TTL 由 `SW_CACHE_TTL_SECONDS` 控制，默认 2 小时）。
4. **防越界锁**：每章 prompt 带上一章、本章、下一章三章细纲窗口，加上 `hard_stop_boundary` 红线。
5. **正则拦截**：规则表在 `guardrails.py`，命中后只把命中段落发给模型局部重写，最多 2 轮，残留命中记入章节报告。

## 测试

```bash
pytest -q
```

测试全部使用 Mock / Spy 后端，覆盖：全链路、人工断点、分支隔离、单分支失败与切片失败降级、正则局部重写、SQLite 崩溃后断点续跑、API + SSE 全流程。
