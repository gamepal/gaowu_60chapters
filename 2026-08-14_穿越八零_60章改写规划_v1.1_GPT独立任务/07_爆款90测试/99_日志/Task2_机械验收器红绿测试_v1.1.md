# Task 2：第一章爆款90机械验收器 v1.1 红绿测试

日期：2026-08-17  
运行环境：Windows PowerShell 5.1.26100.9168

## 工件与冻结校验

| 工件 | SHA256 | 结果 |
|---|---|---|
| `98_工具/validate_boom90_ch1_v1.1.ps1` | `1EC7EA3D67F418A0CF680DA9DBF86E1E4A026D11A4912666D1A37791997A8266` | 新增，UTF-8 BOM |
| `98_工具/validate_boom90_ch1.ps1` | `05DE5791176088C04EB0A87FE725D70F4B787777FB8F3DF2ADA6CDC4D930B247` | 修改前后相同 |
| `99_日志/Task2_机械验收器红绿测试.md` | `CF2A56FCDDA0895C6355DE94B6A8420567FCB83369C03356838E25B05CA91344` | 修改前后相同 |

旧脚本和旧日志未被覆盖或编辑。

## 测试命令

公共变量：

```powershell
$Root = 'C:\Users\zhaoming\WorkBuddy\2026-08-11-15-27-31\output\2026-08-14_穿越八零_60章改写规划_v1.1_GPT独立任务\07_爆款90测试'
$OldScript = Join-Path $Root '98_工具\validate_boom90_ch1.ps1'
$NewScript = Join-Path $Root '98_工具\validate_boom90_ch1_v1.1.ps1'
$CaseDir = Join-Path $Root '03_分析'
```

单例运行形式：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File $NewScript -BodyPath <sample-path>
```

矩阵运行形式：枚举 `03_分析/v11_*.md`，文件名以 `_positive` 结尾者期望 `PASS/exit 0`，其余期望 `FAIL/exit 1`；每次输出均经 `ConvertFrom-Json` 解析。负例另断言目标错误码。

## RED：旧版规格差异

先用 `apply_patch` 创建24个独立样本，再对旧版运行完整矩阵：

- 命令 exit：1（存在预期差异）
- 样本数：24
- 旧版结果与 v1.1 规格不符：18
- 差异样本：
  - 正例误报：永久牌／跨上动作链、早段裸“拆穿”、“不能拆穿”、“仍未证实／无法拆穿”、短快照标题。
  - 负例漏报：否定姜父保管、否定回柳河、否定骑车、前置快照、三种第二章标题、六个前300单锚缺失。

`尚未证实／尚未拆穿` 样本在旧版已通过，因此只作为 v1.1 守护正例，不计入18个旧缺陷。

## GREEN：v1.1 完整矩阵

- 综合命令 exit：0
- 样本数：24
- 正例：9/9 PASS，全部 exit 0、ErrorCount 0、WarningCount 0
- 负例：15/15 FAIL，全部 exit 1
- 状态差异数：0
- 目标错误码差异数：0

| 样本 | 期望 | 旧版 | v1.1 | v1.1 关键证据 |
|---|---:|---:|---:|---|
| `v11_action_alias_positive.md` | PASS | FAIL | PASS | 跨上／蹬／永久牌／赶往柳河 |
| `v11_arrived_dao_negative.md` | FAIL | FAIL | FAIL | `E_NUCLEAR_LIE_COMPLETED` |
| `v11_arrived_liuhe_negative.md` | FAIL | FAIL | FAIL | `E_NUCLEAR_LIE_COMPLETED` |
| `v11_baseline_positive.md` | PASS | PASS | PASS | 标准正向链 |
| `v11_cannot_completion_positive.md` | PASS | FAIL | PASS | 不能证实／不能拆穿不误报 |
| `v11_early_dismantle_positive.md` | PASS | FAIL | PASS | 早段裸“拆穿”不扫描为章末完成态 |
| `v11_father_negated_negative.md` | FAIL | PASS | FAIL | `E_ANCHOR_FATHER_CUSTODY_LIE` |
| `v11_first300_missing_account_negative.md` | FAIL | PASS | FAIL | `E_FIRST300_ACCOUNT_NAME` |
| `v11_first300_missing_carried_negative.md` | FAIL | PASS | FAIL | `E_FIRST300_CARRIED` |
| `v11_first300_missing_compensation_negative.md` | FAIL | PASS | FAIL | `E_FIRST300_COMPENSATION_SOURCE` |
| `v11_first300_missing_gift_negative.md` | FAIL | PASS | FAIL | `E_FIRST300_PREMARITAL_GIFT` |
| `v11_first300_missing_rebuttal_negative.md` | FAIL | PASS | FAIL | `E_FIRST300_VISIBLE_REBUTTAL` |
| `v11_first300_missing_trade_negative.md` | FAIL | PASS | FAIL | `E_FIRST300_FORCED_TRADE` |
| `v11_household_variants_positive.md` | PASS | PASS | PASS | 我爸替我收着；赶回柳河问清手续 |
| `v11_liuhe_negated_negative.md` | FAIL | PASS | FAIL | `E_ANCHOR_LIUHE_PROCEDURE` |
| `v11_negated_completion_positive.md` | PASS | FAIL | PASS | 仍未证实／无法当面拆穿不误报 |
| `v11_notyet_completion_positive.md` | PASS | PASS | PASS | 尚未证实／尚未拆穿不误报 |
| `v11_ride_negated_negative.md` | FAIL | PASS | FAIL | `E_LAST_ACTION_CHAIN` |
| `v11_second_002_book_negative.md` | FAIL | PASS | FAIL | `E_SECOND_CHAPTER` |
| `v11_second_02_dot_negative.md` | FAIL | PASS | FAIL | `E_SECOND_CHAPTER` |
| `v11_second_2_colon_negative.md` | FAIL | PASS | FAIL | `E_SECOND_CHAPTER` |
| `v11_snapshot_before_separator_negative.md` | FAIL | PASS | FAIL | `E_SNAPSHOT_HEADING_AFTER_SEPARATOR` |
| `v11_snapshot_long_positive.md` | PASS | PASS | PASS | `## 第一章章末状态快照` |
| `v11_snapshot_short_positive.md` | PASS | FAIL | PASS | `## 章末状态快照` |

所有正文测试样本的 CJK 计数均在 2100—2300；除前置快照专测为2203外，其余均为2200。

## GREEN 中间回归：否定回柳河漏报

v1.1 首轮为20/21，唯一差异：`v11_liuhe_negated_negative.md` 错误 PASS。

诊断命令列出柳河正则的全部匹配，证实：

- `不回柳河核手续` 本身已被前缀“我不”正确排除；
- 误通过来自章末 `往柳河，核谎`，宽泛裸 `核` 被误当成核手续。

最小修复：裸 `核` 改为 `核(?!谎)`。单例重跑：

- exit：1
- Status：FAIL
- 错误：`E_ANCHOR_LIUHE_PROCEDURE`

随后完整矩阵24/24通过。

## 不存在文件与 JSON 契约

```powershell
$Missing = Join-Path $CaseDir 'v11_file_does_not_exist.md'
powershell.exe -NoProfile -ExecutionPolicy Bypass -File $NewScript -BodyPath $Missing
```

- 子进程 exit：1
- JSON 可由 `ConvertFrom-Json` 解析
- `Status=FAIL`
- `ErrorCount=1`
- 错误：`E_FILE_NOT_FOUND`
- `SHA256=null`

输出字段保持：

```text
Status, HanCount, Paragraphs, First300Han, LastParagraph,
ErrorCount, Errors, WarningCount, Warnings, SHA256
```

## 最终静态与冻结验证

```powershell
[System.Management.Automation.Language.Parser]::ParseFile($NewScript, [ref]$tokens, [ref]$parseErrors)
(Get-FileHash -LiteralPath $NewScript -Algorithm SHA256).Hash
(Get-FileHash -LiteralPath $OldScript -Algorithm SHA256).Hash
```

- AST `ParseErrorCount=0`
- UTF-8 BOM 文件头：`EF BB BF`
- 新脚本 SHA256：`1EC7EA3D67F418A0CF680DA9DBF86E1E4A026D11A4912666D1A37791997A8266`
- 旧脚本 SHA256 仍为：`05DE5791176088C04EB0A87FE725D70F4B787777FB8F3DF2ADA6CDC4D930B247`
- 旧日志 SHA256 仍为：`CF2A56FCDDA0895C6355DE94B6A8420567FCB83369C03356838E25B05CA91344`

## 临时样本清理

24个 `03_分析/v11_*.md` 样本均已用 `apply_patch` 删除。清理后：

```powershell
Get-ChildItem -LiteralPath $CaseDir -File -Filter 'v11_*.md'
```

- exit：0
- RemainingCount：0

不存在文件用例从未创建。

## 适用边界

本脚本执行机械锚词、否定上下文、章节边界、章末风险段和快照字段检查，不替代视角、人物动机、攻防质量及叙事自然度的语义审校。
