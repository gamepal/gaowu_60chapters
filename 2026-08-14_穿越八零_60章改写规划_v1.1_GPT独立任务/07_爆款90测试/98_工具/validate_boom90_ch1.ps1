[CmdletBinding()]
param(
    [Parameter(Mandatory = $true, Position = 0)]
    [string]$BodyPath
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[Console]::OutputEncoding = $utf8NoBom
$OutputEncoding = $utf8NoBom

$errors = New-Object 'System.Collections.Generic.List[string]'
$warnings = New-Object 'System.Collections.Generic.List[string]'
$hanCount = 0
$paragraphCount = 0
$first300Han = ''
$lastParagraph = ''
$sha256 = $null
$body = ''
$content = ''
$snapshot = ''

function Add-ValidationError {
    param([string]$Message)
    [void]$script:errors.Add($Message)
}

function Add-ValidationWarning {
    param([string]$Message)
    [void]$script:warnings.Add($Message)
}

function Test-AnyPattern {
    param(
        [string]$Text,
        [string[]]$Patterns
    )

    foreach ($pattern in $Patterns) {
        if ($Text -match $pattern) {
            return $true
        }
    }
    return $false
}

function Get-FirstHanWindow {
    param(
        [string]$Text,
        [int]$Limit
    )

    $builder = New-Object System.Text.StringBuilder
    $seen = 0
    foreach ($character in $Text.ToCharArray()) {
        [void]$builder.Append($character)
        if ([regex]::IsMatch([string]$character, '[\u4e00-\u9fff]')) {
            $seen++
            if ($seen -ge $Limit) {
                break
            }
        }
    }
    return $builder.ToString()
}

function Test-SnapshotField {
    param(
        [string]$SnapshotText,
        [string]$FieldName
    )

    $fieldCompact = $FieldName -replace '\s', ''
    foreach ($line in ($SnapshotText -split "`n")) {
        $candidate = $line.Trim() -replace '\s', ''
        $candidate = $candidate -replace '\*\*', ''
        $candidate = $candidate -replace '`', ''
        $candidate = $candidate.TrimStart([char[]]'|-*+')
        if ($candidate -match ('^' + [regex]::Escape($fieldCompact) + '(?:\||:|：)')) {
            return $true
        }
    }
    return $false
}

if (-not (Test-Path -LiteralPath $BodyPath -PathType Leaf)) {
    Add-ValidationError "E_FILE_NOT_FOUND: 文件不存在：$BodyPath"
}
else {
    try {
        $sha256 = (Get-FileHash -LiteralPath $BodyPath -Algorithm SHA256).Hash
        $content = [System.IO.File]::ReadAllText($BodyPath, [System.Text.Encoding]::UTF8)
        $normalized = $content -replace "`r`n", "`n"
        $normalized = $normalized -replace "`r", "`n"

        $bodyMatch = [regex]::Match(
            $normalized,
            '(?ms)^[\uFEFF]?[ \t]*##[ \t]+第一章[ \t]*\n(?<body>.*?)(?=^[ \t]*---[ \t]*$)'
        )

        if (-not $bodyMatch.Success) {
            Add-ValidationError 'E_BODY_BOUNDARY: 未找到“## 第一章”后至独立“---”行的正文。'
        }
        else {
            $body = $bodyMatch.Groups['body'].Value.Trim()
        }

        $hanMatches = [regex]::Matches($body, '[\u4e00-\u9fff]')
        $hanCount = $hanMatches.Count
        $first300Han = (($hanMatches | Select-Object -First 300 | ForEach-Object { $_.Value }) -join '')
        $first300Window = Get-FirstHanWindow -Text $body -Limit 300

        $paragraphList = @(($body -split '\n[ \t]*\n+') | ForEach-Object { $_.Trim() } | Where-Object { $_.Length -gt 0 })
        $paragraphCount = $paragraphList.Count
        if ($paragraphCount -gt 0) {
            $lastParagraph = $paragraphList[-1]
        }

        if ($hanCount -lt 2100 -or $hanCount -gt 2300) {
            Add-ValidationError "E_HAN_COUNT: 正文 CJK 统一汉字数为 $hanCount，要求 2100—2300。"
        }

        if ($first300Han -notmatch '存折') {
            Add-ValidationError 'E_FIRST300_ANCHOR_存折: 前300个CJK统一汉字缺少“存折”。'
        }
        if ($first300Han -notmatch '自行车') {
            Add-ValidationError 'E_FIRST300_ANCHOR_自行车: 前300个CJK统一汉字缺少“自行车”。'
        }
        if ($first300Han -notmatch '(?:姜远|亡兄)') {
            Add-ValidationError 'E_FIRST300_ANCHOR_亡兄: 前300个CJK统一汉字缺少“姜远”或“亡兄”。'
        }
        if ($first300Window -notmatch '[“「『"][^”」』"\r\n]{1,160}[”」』"]|[？?]') {
            Add-ValidationWarning 'W_FIRST300_REBUTTAL_PROMPT: 前300个CJK窗口未检出成对对话引号或问号；这只是明面回击提示报警，不能替代语义审校。'
        }

        foreach ($name in @('姜瑶', '沈桂兰', '沈建勋', '陈丽')) {
            if ($body -notmatch [regex]::Escape($name)) {
                Add-ValidationError ('E_CHARACTER_{0}: 正文缺少人物“{0}”。' -f $name)
            }
        }

        if ($normalized -match '(?m)^[ \t]*#{1,6}[ \t]*第[ \t]*(?:二|2|02|002)[ \t]*章(?:[ \t]|$)') {
            Add-ValidationError 'E_SECOND_CHAPTER: 文件不得包含第二章。'
        }
        if ($normalized -match '沈笑笑') {
            Add-ValidationError 'E_FORBIDDEN_CHARACTER_沈笑笑: 文件不得出现“沈笑笑”。'
        }

        $bodyFlat = $body -replace '\s+', ''
        $fatherCustodyPatterns = @(
            '(?:存折|折子).{0,12}(?:姜父|我爸|父亲|爸爸|爹|爸).{0,8}(?:保管|收着|拿着|放着|手里|手上|那儿|那里)',
            '(?:姜父|我爸|父亲|爸爸|爹|爸).{0,10}(?:保管|收着|拿着|放着).{0,8}(?:存折|折子)'
        )
        if (-not (Test-AnyPattern -Text $bodyFlat -Patterns $fatherCustodyPatterns)) {
            Add-ValidationError 'E_ANCHOR_FATHER_CUSTODY_LIE: 正文未检出“存折由姜父保管”的可接受语义锚。'
        }

        $liuheProcedurePatterns = @(
            '(?:回|去|往|到|赶回|赶去)柳河.{0,18}(?:核|查|对|问|验|手续|开户|户名)',
            '(?:核|查|对|问|验).{0,12}(?:手续|开户|户名|存折).{0,18}(?:回|去|往|到)柳河'
        )
        if (-not (Test-AnyPattern -Text $bodyFlat -Patterns $liuheProcedurePatterns)) {
            Add-ValidationError 'E_ANCHOR_LIUHE_PROCEDURE: 正文未检出“回柳河核手续”的可接受语义锚。'
        }

        foreach ($lastRequired in @('沈建勋', '自行车', '柳河')) {
            if ($lastParagraph -notmatch [regex]::Escape($lastRequired)) {
                Add-ValidationError ('E_LAST_PARAGRAPH_{0}: 章末最后一个自然段缺少“{0}”。' -f $lastRequired)
            }
        }
        if ($lastParagraph -notmatch '骑') {
            Add-ValidationError 'E_LAST_PARAGRAPH_RIDE: 章末最后一个自然段缺少“骑/骑走”。'
        }

        $unfinishedPatterns = @(
            '(?:核谎|核验|核实|查证|查清).{0,10}(?:尚未|还没|仍未|没有|未曾|未)(?:完成|结束|查清|证实|有结果|出结果)?',
            '(?:尚未|还没|仍未|没有|未曾|未).{0,10}(?:完成|核谎|核验|核实|查证|查清|证实|见分晓|出结果|有结果|到柳河|见到姜父)',
            '(?:答案|结果|真假|真伪).{0,10}(?:尚未|还没|仍未|没有|未曾|未|不明|未明|没出|未出|未定)',
            '(?:真假|真伪).{0,6}(?:未明|不明|没见分晓|尚无定论)'
        )
        if (-not (Test-AnyPattern -Text ($lastParagraph -replace '\s+', '') -Patterns $unfinishedPatterns)) {
            Add-ValidationError 'E_LAST_PARAGRAPH_UNFINISHED: 章末最后一个自然段未明确提示核谎尚未完成。'
        }

        $completionPatterns = @(
            '(?:到了|到达|抵达|赶到)柳河',
            '见到(?:了)?姜父',
            '找到(?:了)?姜父',
            '拆穿',
            '证实(?:了)?(?:姜瑶)?撒谎',
            '(?:核谎|核验|查证)(?:完成|结束|查清)',
            '(?:核谎|核验|查证).{0,6}(?:已经|已|终于).{0,3}(?:完成|结束|查清)',
            '(?:查清|查明)(?:了)?(?:真相|谎言)'
        )
        $completionFound = $false
        foreach ($completionPattern in $completionPatterns) {
            foreach ($completionMatch in [regex]::Matches($bodyFlat, $completionPattern)) {
                $prefixLength = [Math]::Min(6, $completionMatch.Index)
                $prefix = $bodyFlat.Substring($completionMatch.Index - $prefixLength, $prefixLength)
                if ($prefix -match '(?:尚未|还没|还没有|没有|仍未|未曾|未能|并未|不曾|未|没|不)$') {
                    continue
                }
                Add-ValidationError "E_NUCLEAR_LIE_COMPLETED: 正文出现核谎完成词组（匹配：$completionPattern）。"
                $completionFound = $true
                break
            }
            if ($completionFound) {
                break
            }
        }

        $snapshotMatch = [regex]::Match($normalized, '(?m)^[ \t]*##[ \t]+第一章章末状态快照[ \t]*$')
        if (-not $snapshotMatch.Success) {
            Add-ValidationError 'E_SNAPSHOT_HEADING: 缺少“## 第一章章末状态快照”。'
        }
        else {
            $snapshot = $normalized.Substring($snapshotMatch.Index + $snapshotMatch.Length).Trim()
            $nextHeading = [regex]::Match($snapshot, '(?m)^[ \t]*##[ \t]+')
            if ($nextHeading.Success) {
                $snapshot = $snapshot.Substring(0, $nextHeading.Index).Trim()
            }

            $requiredSnapshotFields = @(
                '时间',
                '视角',
                '姜瑶身份与身体',
                '记忆与能力',
                '姜瑶位置',
                '沈建业',
                'M-01 来源与户名',
                'M-01 余额与位置',
                'M-01 交付与支取',
                '沈家对 M-01 的认知',
                '姜瑶对外口径',
                '第二击结果',
                '索折状态',
                '院门与离院',
                '核谎进度',
                'A-01 所有权',
                'A-01 钥匙与控制',
                '人物位置',
                '现金、经营、库存',
                '唯一未决威胁'
            )

            foreach ($fieldName in $requiredSnapshotFields) {
                if (-not (Test-SnapshotField -SnapshotText $snapshot -FieldName $fieldName)) {
                    Add-ValidationError ('E_SNAPSHOT_FIELD_{0}: 章末状态快照缺少字段“{0}”。' -f $fieldName)
                }
            }
        }
    }
    catch {
        Add-ValidationError "E_READ_OR_PARSE: 读取或解析失败：$($_.Exception.Message)"
    }
}

$status = if ($errors.Count -eq 0) { 'PASS' } else { 'FAIL' }
$result = [ordered]@{
    Status        = $status
    HanCount      = $hanCount
    Paragraphs    = $paragraphCount
    First300Han   = $first300Han
    LastParagraph = $lastParagraph
    ErrorCount    = $errors.Count
    Errors        = [string[]]$errors.ToArray()
    WarningCount  = $warnings.Count
    Warnings      = [string[]]$warnings.ToArray()
    SHA256        = $sha256
}

$result | ConvertTo-Json -Depth 6

if ($errors.Count -gt 0) {
    exit 1
}
exit 0
