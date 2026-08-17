# Task 2：第一章爆款90机械验收器红绿测试

日期：2026-08-17  
运行环境：Windows PowerShell 5.1.26100.9168

## 工件

- 验证器：`98_工具/validate_boom90_ch1.ps1`
- SHA256：`05DE5791176088C04EB0A87FE725D70F4B787777FB8F3DF2ADA6CDC4D930B247`
- 文件长度：10979 bytes
- 编码：UTF-8 BOM（兼容 Windows PowerShell 5.1）

测试公共变量：

```powershell
$Root = 'C:\Users\zhaoming\WorkBuddy\2026-08-11-15-27-31\output\2026-08-14_穿越八零_60章改写规划_v1.1_GPT独立任务\07_爆款90测试'
$Script = Join-Path $Root '98_工具\validate_boom90_ch1.ps1'
$Invalid = Join-Path $Root '03_分析\validator_invalid_sample.md'
$Valid = Join-Path $Root '03_分析\validator_valid_structure_sample.md'
$Missing = Join-Path $Root '03_分析\validator_file_does_not_exist.md'
```

## RED 1：实现前功能不存在

先用 `apply_patch` 创建最小无效样本，再运行：

```powershell
& $Script -BodyPath $Invalid
```

- exit：1
- 结果：`CommandNotFoundException`，目标验证器尚不存在；RED 命中待实现功能，而非样本误通过。

## 兼容性红测：Windows PowerShell 5.1 脚本编码

首次实现为无 BOM UTF-8，运行同一无效样本：

```powershell
& $Script -BodyPath $Invalid
```

- exit：1
- 结果：解析阶段中文乱码并报 `ParserError`。
- 根因证据：文件头为 `5B 43 6D...`，宿主为 PowerShell 5.1；补 UTF-8 BOM 后文件头为 `EF BB BF`，解析恢复。

## RED 2：无效样本必须按类别失败

命令：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File $Script -BodyPath $Invalid
```

- 子进程 exit：1
- `Status=FAIL`
- `HanCount=6`
- `ErrorCount=34`
- `WarningCount=1`
- 分类断言全部为 true：
  - `E_HAN_COUNT`
  - `E_FIRST300_ANCHOR_*`
  - `E_CHARACTER_姜瑶／沈桂兰／沈建勋／陈丽`
  - `E_ANCHOR_FATHER_CUSTODY_LIE`
  - `E_ANCHOR_LIUHE_PROCEDURE`
  - `E_LAST_PARAGRAPH_*`
  - 快照缺失字段错误

## GREEN 1：机械结构有效样本

该样本只验证机械层，正文填充不具备语义审校价值。

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File $Script -BodyPath $Valid
```

- 子进程 exit：0
- `Status=PASS`
- `HanCount=2199`
- `Paragraphs=3`
- `First300Han` 的 CJK 长度：300
- `LastParagraph=沈建勋骑走自行车，正往柳河抢先核谎，核谎尚未完成。`
- `ErrorCount=0`
- `WarningCount=0`
- 20 个权威快照字段名全部通过。

## 回归红绿：否定完成态不得误报

将绿样本末段设为权威原句“核谎尚未完成”。修正前：

- 子进程 exit：1
- `Status=FAIL`
- 唯一错误：`E_NUCLEAR_LIE_COMPLETED`
- 根因：宽泛正则把“尚未完成”中的“完成”误判为完成态。

收紧完成态词组并跳过否定前缀后重跑：

- 子进程 exit：0
- `Status=PASS`
- `HanCount=2199`
- `ErrorCount=0`

## 机械告警不升级为硬错误

去掉前300窗口内的成对对话引号和问号，同时保留全部硬锚：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File $Script -BodyPath $Valid
```

- 子进程 exit：0
- `Status=PASS`
- `ErrorCount=0`
- `WarningCount=1`
- warning：`W_FIRST300_REBUTTAL_PROMPT`，文案明确提示仍需语义审校。

## 禁止项负测

临时把结构样本改为完成态末段，并追加 `## 第二章` 与“沈笑笑”：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File $Script -BodyPath $Valid
```

- 子进程 exit：1
- `Status=FAIL`
- `ErrorCount=4`
- 命中：`E_SECOND_CHAPTER`、`E_FORBIDDEN_CHARACTER_沈笑笑`、`E_LAST_PARAGRAPH_UNFINISHED`、`E_NUCLEAR_LIE_COMPLETED`。

## 不存在文件

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File $Script -BodyPath $Missing
```

- 子进程 exit：1
- `Status=FAIL`
- `ErrorCount=1`
- 错误：`E_FILE_NOT_FOUND`
- `SHA256=null`

## 最终综合复验

执行 PowerShell AST 解析，并分别运行恢复后的有效样本、最小无效样本和不存在文件用例；同时断言 JSON 字段集合：

```text
ParseErrorCount=0
Utf8Bom=true
Valid:  exit=0, Status=PASS, HanCount=2199, First300HanLength=300, ErrorCount=0
Invalid: exit=1, Status=FAIL, HanCount=6, ErrorCount=34, WarningCount=1
Missing: exit=1, Status=FAIL, ErrorCount=1
JSON keys: Status, HanCount, Paragraphs, First300Han, LastParagraph,
           ErrorCount, Errors, WarningCount, Warnings, SHA256
综合断言命令 exit=0
```

最终 SHA 命令与结果：

```powershell
(Get-FileHash -LiteralPath $Script -Algorithm SHA256).Hash
# 05DE5791176088C04EB0A87FE725D70F4B787777FB8F3DF2ADA6CDC4D930B247
```

## 临时文件清理

已用 `apply_patch` 删除：

- `03_分析/validator_invalid_sample.md`
- `03_分析/validator_valid_structure_sample.md`

不存在文件用例从未创建。清理后执行：

```powershell
Get-ChildItem -LiteralPath (Join-Path $Root '03_分析') -File -Filter 'validator_*sample.md'
```

- exit：0
- 结果：空集合；没有遗留机械验收临时样本。

## 适用边界

本工具只做字符、锚词、结构和禁止词机械验收。人物动机、明面回击是否真正成立、谎言是否自然、视角和攻防质量仍须语义审校。
