# Task 2：第一章爆款90机械验收器 v1.3 红绿测试

日期：2026-08-17  
运行环境：Windows PowerShell 5.1.26100.9168

## 工件与旧版冻结

| 工件 | SHA256 | 状态 |
|---|---|---|
| `98_工具/validate_boom90_ch1_v1.3.ps1` | `5A0551231CE94D2E8925B5BC2B70C9A7A2AF9F24918E64BA936E96CD242A90E8` | 新增，UTF-8 BOM |
| `98_工具/validate_boom90_ch1_v1.2.ps1` | `E98B069DF6E463FE5BA70E1521620E137DA4BDB535140178D059EF39AAAF7FA3` | 未变化 |
| `99_日志/Task2_机械验收器红绿测试_v1.2.md` | `109715F1B1654DEBCC7A702862FADAA62D7F0BBA4366D7E47C7BEEBDE00847D7` | 未变化 |
| `98_工具/validate_boom90_ch1_v1.1.ps1` | `1EC7EA3D67F418A0CF680DA9DBF86E1E4A026D11A4912666D1A37791997A8266` | 未变化 |
| `99_日志/Task2_机械验收器红绿测试_v1.1.md` | `D376B5738CF0DB3C3D8E219F0277483A73EAD09048EF1961FE55723F9527F439` | 未变化 |
| `98_工具/validate_boom90_ch1.ps1` | `05DE5791176088C04EB0A87FE725D70F4B787777FB8F3DF2ADA6CDC4D930B247` | 未变化 |
| `99_日志/Task2_机械验收器红绿测试.md` | `CF2A56FCDDA0895C6355DE94B6A8420567FCB83369C03356838E25B05CA91344` | 未变化 |

旧版脚本和日志均未覆盖或编辑。

## 测试方式

```powershell
$Root = 'C:\Users\zhaoming\WorkBuddy\2026-08-11-15-27-31\output\2026-08-14_穿越八零_60章改写规划_v1.1_GPT独立任务\07_爆款90测试'
$V12 = Join-Path $Root '98_工具\validate_boom90_ch1_v1.2.ps1'
$V13 = Join-Path $Root '98_工具\validate_boom90_ch1_v1.3.ps1'
$CaseDir = Join-Path $Root '03_分析'

powershell.exe -NoProfile -ExecutionPolicy Bypass -File $V13 -BodyPath <sample-path>
```

矩阵枚举 `03_分析/v13case_*.md`：`_positive` 期望 `PASS/exit 0`，其余期望 `FAIL/exit 1`；输出全部经 `ConvertFrom-Json` 解析，负例同时断言目标错误码。

## RED：v1.2 新规格差异

先用 `apply_patch` 创建34个 v1.2 原矩阵样本及11个 v1.3 定向样本，对 v1.2 运行：

- 命令 exit：1
- 样本数：45
- v1.2 原34例差异：0
- 新规格差异：5

五个差异为：

1. `并未` 否定赠与被错误放行；
2. `姜瑶看着沈桂兰，反问` 被错误拒绝；
3. `沈桂兰看着姜瑶，问` 被错误当成姜瑶说话；
4. `| 时间 | |` 被当成有效字段；
5. `时间：` 被当成有效字段。

另补“单字未／没不全局禁用”守护正例后，最终矩阵为46例，RED差异仍为上述5项。

## GREEN：v1.3 完整矩阵

- 综合命令 exit：0
- 总样本：46
- 正例：17/17 PASS，全部 exit 0、ErrorCount 0、WarningCount 0
- 负例：29/29 FAIL，全部 exit 1
- 状态及目标错误码差异：0
- v1.2 原34例回归差异：0

### v1.3 定向结果

| 样本 | 结果 | exit | 关键证据 |
|---|---:|---:|---|
| `v13case_negation_bingwei_negative.md` | FAIL | 1 | `E_FIRST300_PREMARITAL_GIFT` |
| `v13case_negation_congwei_negative.md` | FAIL | 1 | `E_FIRST300_COMPENSATION_SOURCE` |
| `v13case_negation_weiceng_negative.md` | FAIL | 1 | `E_FIRST300_PREMARITAL_GIFT` |
| `v13case_negation_bingbushi_negative.md` | FAIL | 1 | `E_FIRST300_ACCOUNT_NAME` |
| `v13case_negation_juebushi_negative.md` | FAIL | 1 | `E_FIRST300_COMPENSATION_SOURCE` |
| `v13case_contrast_gift_positive.md` | PASS | 0 | “不是婆家给的，是父母婚前赠的”正向后半句通过 |
| `v13case_single_wei_mei_positive.md` | PASS | 0 | “未登记为沈家钱／还没动过”不触发单字禁词 |
| `v13case_directed_speaker_positive.md` | PASS | 0 | `姜瑶看着沈桂兰，反问` |
| `v13case_inverse_speaker_negative.md` | FAIL | 1 | `E_FIRST300_VISIBLE_REBUTTAL` |
| `v13case_snapshot_empty_table_negative.md` | FAIL | 1 | `E_SNAPSHOT_FIELD_时间` |
| `v13case_snapshot_empty_colon_negative.md` | FAIL | 1 | `E_SNAPSHOT_FIELD_时间` |
| `v13case_snapshot_table_values_positive.md` | PASS | 0 | 20个表格字段均有值 |

所有定向正文样本均为2200个 CJK 统一汉字。

## 差异范围审查

```powershell
git --no-pager diff --no-index --unified=2 -- $V12 $V13
```

只存在三类改动：

1. 明确否定集合增加 `并未／并不是／绝不是`，保留 `从未／未曾` 等；没有加入单字 `未／没`。
2. 回击归属拆分为简单前置、姜瑶面向沈桂兰／沈建勋／陈丽的目标式前置、以及后置归属；移除“出现另一人物名即歧义”的粗前瞻。
3. 快照字段区分表格和冒号格式，并要求对应值非空；20个字段名列表及快照尾随边界未改变。

未传参数JSON和快照尾随边界按要求不修改。其余正文、章末、章节、人物与输出逻辑保持 v1.2。

## 不存在文件与 JSON 契约

```powershell
$Missing = Join-Path $CaseDir 'v13case_file_does_not_exist.md'
powershell.exe -NoProfile -ExecutionPolicy Bypass -File $V13 -BodyPath $Missing
```

- exit：1
- 合法 JSON
- `Status=FAIL`
- `ErrorCount=1`
- `E_FILE_NOT_FOUND`
- `SHA256=null`

输出字段仍为：

```text
Status, HanCount, Paragraphs, First300Han, LastParagraph,
ErrorCount, Errors, WarningCount, Warnings, SHA256
```

## 静态检查与清理

- PowerShell AST `ParseErrorCount=0`
- UTF-8 BOM：`EF BB BF`
- v1.3 SHA256：`5A0551231CE94D2E8925B5BC2B70C9A7A2AF9F24918E64BA936E96CD242A90E8`
- 46个 `03_分析/v13case_*.md` 已用 `apply_patch` 删除
- 清理后 `RemainingCount=0`
- 不存在文件用例从未创建

## 适用边界

本脚本只作机械短句、说话归属和字段非空检查；复杂跨句转折、省略归属及内容真实性仍须人工语义审校。
