# Task 2：第一章爆款90机械验收器 v1.2 红绿测试

日期：2026-08-17  
运行环境：Windows PowerShell 5.1.26100.9168

## 工件与冻结 SHA

| 工件 | SHA256 | 状态 |
|---|---|---|
| `98_工具/validate_boom90_ch1_v1.2.ps1` | `E98B069DF6E463FE5BA70E1521620E137DA4BDB535140178D059EF39AAAF7FA3` | 新增，UTF-8 BOM |
| `98_工具/validate_boom90_ch1_v1.1.ps1` | `1EC7EA3D67F418A0CF680DA9DBF86E1E4A026D11A4912666D1A37791997A8266` | 修改前后相同 |
| `99_日志/Task2_机械验收器红绿测试_v1.1.md` | `D376B5738CF0DB3C3D8E219F0277483A73EAD09048EF1961FE55723F9527F439` | 修改前后相同 |
| `98_工具/validate_boom90_ch1.ps1` | `05DE5791176088C04EB0A87FE725D70F4B787777FB8F3DF2ADA6CDC4D930B247` | 修改前后相同 |
| `99_日志/Task2_机械验收器红绿测试.md` | `CF2A56FCDDA0895C6355DE94B6A8420567FCB83369C03356838E25B05CA91344` | 修改前后相同 |

v1.0、v1.1 脚本及日志均未被覆盖或编辑。

## 测试命令

```powershell
$Root = 'C:\Users\zhaoming\WorkBuddy\2026-08-11-15-27-31\output\2026-08-14_穿越八零_60章改写规划_v1.1_GPT独立任务\07_爆款90测试'
$V11 = Join-Path $Root '98_工具\validate_boom90_ch1_v1.1.ps1'
$V12 = Join-Path $Root '98_工具\validate_boom90_ch1_v1.2.ps1'
$CaseDir = Join-Path $Root '03_分析'

powershell.exe -NoProfile -ExecutionPolicy Bypass -File $V12 -BodyPath <sample-path>
```

矩阵命令枚举 `03_分析/v12case_*.md`，`_positive` 期望 `PASS/exit 0`，其余期望 `FAIL/exit 1`；每次输出均以 `ConvertFrom-Json` 解析。负例还断言对应错误码。

## RED：v1.1 对新规格的漏报

先用 `apply_patch` 创建24个 v1.1 回归样本和8个 v1.2 定向样本，再对 v1.1 运行：

- 命令 exit：1
- 样本数：32
- v1.1 原24例回归差异：0
- 新规格差异：5

五个错误 PASS 的负例：

- 明确否定抚恤来源；
- 明确否定婚前父母赠与；
- 明确否定姜瑶本人户名；
- 三锚否定连写；
- 回击台词实际归属沈桂兰。

随后补充“绝非＋没有”三锚负例：v1.1 仍为 PASS。最终 v1.1 对34例的规格差异为6，旧24例始终零差异。

## GREEN：v1.2 完整矩阵

- 综合命令 exit：0
- 样本总数：34
- 正例：13/13 PASS，全部 exit 0、ErrorCount 0、WarningCount 0
- 负例：21/21 FAIL，全部 exit 1
- 状态差异：0
- 目标错误码差异：0
- 原 v1.1 24例回归差异：0

### v1.2 定向证据

| 样本 | 结果 | exit | 错误码／验证点 |
|---|---:|---:|---|
| `v12case_negated_compensation_negative.md` | FAIL | 1 | `E_FIRST300_COMPENSATION_SOURCE` |
| `v12case_negated_gift_negative.md` | FAIL | 1 | `E_FIRST300_PREMARITAL_GIFT` |
| `v12case_negated_account_negative.md` | FAIL | 1 | `E_FIRST300_ACCOUNT_NAME` |
| `v12case_negated_three_anchors_negative.md` | FAIL | 1 | 同时命中上述三个错误 |
| `v12case_negated_absolute_none_negative.md` | FAIL | 1 | “绝非／没有”同时命中上述三个错误 |
| `v12case_wrong_speaker_negative.md` | FAIL | 1 | `E_FIRST300_VISIBLE_REBUTTAL` |
| `v12case_speaker_prefix_positive.md` | PASS | 0 | `姜瑶反问：“……。”`，无问号的陈述式反扣 |
| `v12case_speaker_suffix_positive.md` | PASS | 0 | `“……。”姜瑶反问`，后置归属 |
| `v12case_reverse_anchors_positive.md` | PASS | 0 | 抚恤、赠与、户名的反向词序均通过 |
| `v12case_local_contrast_positive.md` | PASS | 0 | 否定沈家／婚后／沈家名下后，独立短句的正锚不被误伤 |

所有定向样本正文均为2200个 CJK 统一汉字。

## 实现范围审查

执行：

```powershell
git --no-pager diff --no-index --unified=2 -- $V11 $V12
```

只存在以下差异：

1. 新增 `Test-AffirmedTokenClause`，在逗号、句号、问叹号、分号等短句边界内执行正向词组共现，并拒绝 `不是／并非／绝非／不在／没有／无关` 等明确否定。
2. 新增 `Test-RebuttalSpeech`，判断台词是否包含规定关键词与质疑／反扣语义，不强制问号。
3. 将抚恤来源、婚前赠与、本人户名三项改为顺序无关的正向短句近邻检查。
4. 将首次回击改为仅接受姜瑶前置或后置说话归属。

章末风险、正向骑车链、姜父保管谎、柳河手续、快照、第二章、人物、字数及 JSON 输出逻辑与 v1.1 相同。

## 不存在文件与 JSON 契约

```powershell
$Missing = Join-Path $CaseDir 'v12case_file_does_not_exist.md'
powershell.exe -NoProfile -ExecutionPolicy Bypass -File $V12 -BodyPath $Missing
```

- exit：1
- JSON 可正常解析
- `Status=FAIL`
- `ErrorCount=1`
- 错误：`E_FILE_NOT_FOUND`
- `SHA256=null`

输出字段保持：

```text
Status, HanCount, Paragraphs, First300Han, LastParagraph,
ErrorCount, Errors, WarningCount, Warnings, SHA256
```

## 静态检查

- PowerShell AST `ParseErrorCount=0`
- UTF-8 BOM 文件头：`EF BB BF`
- 新脚本 SHA256：`E98B069DF6E463FE5BA70E1521620E137DA4BDB535140178D059EF39AAAF7FA3`

## 临时样本清理

34个 `03_分析/v12case_*.md` 均已用 `apply_patch` 删除。

```powershell
Get-ChildItem -LiteralPath $CaseDir -File -Filter 'v12case_*.md'
```

- exit：0
- RemainingCount：0

不存在文件用例从未创建。

## 适用边界

本工具进行机械短句近邻和说话归属检查，不替代人工语义审校；复杂省略主语、跨句倒装或隐含反讽仍须人工确认。
