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

function Test-PositiveRegex {
    param(
        [string]$Text,
        [string[]]$Patterns,
        [int]$PrefixLength = 8
    )

    $negativePattern = '(?:尚未|仍未|并未|还没有|还没|没有|未曾|未能|不曾|不能|无法|无需|不用|不必|不会|别|不|没|未)'
    foreach ($pattern in $Patterns) {
        foreach ($match in [regex]::Matches($Text, $pattern)) {
            $take = [Math]::Min($PrefixLength, $match.Index)
            $prefix = $Text.Substring($match.Index - $take, $take)
            if ($prefix -match ($negativePattern + '.{0,4}$')) {
                continue
            }
            if ($match.Value -match $negativePattern) {
                continue
            }
            return $true
        }
    }
    return $false
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
    Add-ValidationError ('E_FILE_NOT_FOUND: 文件不存在：{0}' -f $BodyPath)
}
else {
    try {
        $sha256 = (Get-FileHash -LiteralPath $BodyPath -Algorithm SHA256).Hash
        $content = [System.IO.File]::ReadAllText($BodyPath, [System.Text.Encoding]::UTF8)
        $normalized = $content -replace "`r`n", "`n"
        $normalized = $normalized -replace "`r", "`n"

        $bodyMatch = [regex]::Match(
            $normalized,
            '(?ms)^[\uFEFF]?[ \t]*##[ \t]+第一章[ \t]*\n(?<body>.*?)(?<separator>^[ \t]*---[ \t]*$)'
        )

        $separatorEndIndex = -1
        if (-not $bodyMatch.Success) {
            Add-ValidationError 'E_BODY_BOUNDARY: 未找到“## 第一章”后至独立“---”行的正文。'
        }
        else {
            $body = $bodyMatch.Groups['body'].Value.Trim()
            $separatorEndIndex = $bodyMatch.Groups['separator'].Index + $bodyMatch.Groups['separator'].Length
        }

        $hanMatches = [regex]::Matches($body, '[\u4e00-\u9fff]')
        $hanCount = $hanMatches.Count
        $first300Han = (($hanMatches | Select-Object -First 300 | ForEach-Object { $_.Value }) -join '')
        $first300Window = Get-FirstHanWindow -Text $body -Limit 300
        $first300Flat = $first300Window -replace '\s+', ''

        $paragraphList = @(($body -split '\n[ \t]*\n+') | ForEach-Object { $_.Trim() } | Where-Object { $_.Length -gt 0 })
        $paragraphCount = $paragraphList.Count
        if ($paragraphCount -gt 0) {
            $lastParagraph = $paragraphList[-1]
        }

        if ($hanCount -lt 2100 -or $hanCount -gt 2300) {
            Add-ValidationError ('E_HAN_COUNT: 正文 CJK 统一汉字数为 {0}，要求 2100—2300。' -f $hanCount)
        }

        $forcedTradePatterns = @(
            '(?:自行车(?:钥匙)?|车钥匙|钥匙).{0,18}(?:换|交换|扣|押|交).{0,12}(?:存折|折子)',
            '(?:存折|折子).{0,12}(?:换|交换|扣|押|交).{0,18}(?:自行车(?:钥匙)?|车钥匙|钥匙)',
            '(?:交出|交|拿出|拿来|给出)(?:整本|这本|她的|你的|我的)?(?:存折|折子).{0,10}(?:才|方|否则|不然|就).{0,10}(?:准|让|许|能|可以)?(?:她|你|姜瑶)?(?:回|去).{0,4}柳河'
        )
        if (-not (Test-PositiveRegex -Text $first300Flat -Patterns $forcedTradePatterns)) {
            Add-ValidationError 'E_FIRST300_FORCED_TRADE: 前300个CJK窗口未建立存折与自行车／钥匙绑定的强制交易。'
        }

        if ($first300Han -notmatch '抚恤' -or $first300Han -notmatch '(?:姜远|亡兄|哥哥)') {
            Add-ValidationError 'E_FIRST300_COMPENSATION_SOURCE: 前300个CJK统一汉字缺少抚恤来源及姜远／亡兄／哥哥锚。'
        }

        if (
            $first300Han -notmatch '(?:婚前|成亲前|出嫁前)' -or
            $first300Han -notmatch '(?:父母|爸妈|爹娘|姜父母|父亲母亲)' -or
            $first300Han -notmatch '(?:给|划|赠|留)'
        ) {
            Add-ValidationError 'E_FIRST300_PREMARITAL_GIFT: 前300个CJK统一汉字缺少婚前父母赠与锚。'
        }

        if ($first300Han -notmatch '(?:本人名下|姜瑶名下|她名下|户名(?:是|写|为)?姜瑶?|以姜瑶(?:本人)?名义开户|姜瑶本人名义)') {
            Add-ValidationError 'E_FIRST300_ACCOUNT_NAME: 前300个CJK统一汉字缺少姜瑶本人户名锚。'
        }

        $carriedPatterns = @(
            '(?:存折|折子).{0,18}(?:身上|随身|棉袄|暗袋|内衬)',
            '(?:身上|随身|棉袄|暗袋|内衬).{0,18}(?:存折|折子)'
        )
        if (-not (Test-PositiveRegex -Text $first300Flat -Patterns $carriedPatterns)) {
            Add-ValidationError 'E_FIRST300_CARRIED: 前300个CJK窗口缺少存折随身／棉袄／暗袋锚。'
        }

        $visibleRebuttal = $false
        $quotedPattern = '[“「『"](?<speech>[^”」』"\r\n]{1,200})[”」』"]'
        foreach ($quotedMatch in [regex]::Matches($first300Window, $quotedPattern)) {
            $speech = $quotedMatch.Groups['speech'].Value
            $take = [Math]::Min(10, $quotedMatch.Index)
            $quotePrefix = $first300Window.Substring($quotedMatch.Index - $take, $take)
            $hasKeyword = $speech -match '(?:换|拿|商量|钥匙|存折)'
            $hasCounterCue = $speech -match '[？?]|(?:凭什么|怎么|也叫|算什么|倒要|谁说|先说)' -or $quotePrefix -match '(?:反问|反扣|追问|质问|问)[：:]?\s*$'
            if ($hasKeyword -and $hasCounterCue) {
                $visibleRebuttal = $true
                break
            }
        }
        if (-not $visibleRebuttal) {
            Add-ValidationError 'E_FIRST300_VISIBLE_REBUTTAL: 前300个CJK窗口缺少带引号的明面反问／反扣及换、拿、商量、钥匙、存折关键词。'
        }

        foreach ($name in @('姜瑶', '沈桂兰', '沈建勋', '陈丽')) {
            if ($body -notmatch [regex]::Escape($name)) {
                Add-ValidationError ('E_CHARACTER_{0}: 正文缺少人物“{0}”。' -f $name)
            }
        }

        if ($normalized -match '(?m)^[ \t]*#{1,6}[ \t]*第[ \t]*(?:二|2|02|002)[ \t]*章') {
            Add-ValidationError 'E_SECOND_CHAPTER: 文件不得包含第二章。'
        }
        if ($normalized -match '沈笑笑') {
            Add-ValidationError 'E_FORBIDDEN_CHARACTER_沈笑笑: 文件不得出现“沈笑笑”。'
        }

        $bodyFlat = $body -replace '\s+', ''
        $fatherCustodyPatterns = @(
            '(?:存折|折子)(?:由|在|交给|放在)(?:我爸|父亲|姜父|爸爸|爸|爹)(?:替我|给我)?(?:保管|收着|管着|拿着|放着|手里|手上|那儿|那里)?',
            '(?:我爸|父亲|姜父|爸爸|爸|爹)(?:替我|给我)?(?:保管|收着|管着|拿着|放着)(?:这本|我的)?(?:存折|折子)'
        )
        if (-not (Test-PositiveRegex -Text $bodyFlat -Patterns $fatherCustodyPatterns)) {
            Add-ValidationError 'E_ANCHOR_FATHER_CUSTODY_LIE: 正文未检出未被否定的“姜父保管存折”语义锚。'
        }

        $liuheProcedurePatterns = @(
            '(?:赶回|赶去|回|去|往|到)柳河.{0,10}(?:问清|问明白|核实|核对|核(?!谎)|查清|查|办手续|核手续|对手续|问手续)',
            '(?:赶回|赶去|回|去|往|到)柳河.{0,8}(?:把)?(?:手续|户名|存折).{0,6}(?:问清|核清|核实|核对|查清|办|核|查|对)'
        )
        if (-not (Test-PositiveRegex -Text $bodyFlat -Patterns $liuheProcedurePatterns)) {
            Add-ValidationError 'E_ANCHOR_LIUHE_PROCEDURE: 正文未检出未被否定的“回／去柳河问清或核手续”语义锚。'
        }

        $lastFlat = $lastParagraph -replace '\s+', ''
        $actionChainPatterns = @(
            '沈建勋.{0,12}(?:骑(?:上|走)?|跨上|蹬(?:上|着)?).{0,12}(?:自行车|永久牌).{0,18}(?:赶往|赶去|前往|往|去).{0,6}柳河'
        )
        if (-not (Test-PositiveRegex -Text $lastFlat -Patterns $actionChainPatterns -PrefixLength 10)) {
            Add-ValidationError 'E_LAST_ACTION_CHAIN: 章末最后一个自然段缺少未被否定的“沈建勋骑／跨上／蹬自行车或永久牌并往柳河”行动链。'
        }

        $riskParagraphs = @()
        if ($paragraphCount -gt 0) {
            $riskStart = [Math]::Max(0, $paragraphCount - 2)
            $riskParagraphs = @($paragraphList[$riskStart..($paragraphCount - 1)])
        }
        $riskFlat = ($riskParagraphs -join '') -replace '\s+', ''

        $completionPatterns = @(
            '(?:已经|已|终于)?(?:到了|抵达(?:了)?|到达(?:了)?|赶到(?:了)?)柳河',
            '(?:见到|见着|找到)(?:了)?(?:姜父|父亲)',
            '(?:证实|查明|查清|拆穿)(?:了)?(?:姜瑶(?:的)?(?:谎|谎言)|她(?:的)?(?:谎|谎言))',
            '(?:核谎|核验|查证)(?:已经|已|终于)?(?:完成|结束)'
        )
        if (Test-PositiveRegex -Text $riskFlat -Patterns $completionPatterns -PrefixLength 10) {
            Add-ValidationError 'E_NUCLEAR_LIE_COMPLETED: 章末风险段出现明确正向核谎完成态。'
        }

        $unfinishedPatterns = @(
            '(?:核谎|核验|核实|查证|查清).{0,10}(?:尚未|仍未|还没|没有|未曾|未)(?:完成|结束|证实|查清|有结果|出结果)?',
            '(?:尚未|仍未|并未|还没有|还没|没有|未能|无法|不能|未曾|未).{0,10}(?:证实|查明|查清|核实|核验|完成|拆穿|见到(?:姜父|父亲)|到(?:达)?柳河)',
            '(?:答案|结果|真假|真伪).{0,10}(?:未出|没出|未明|不明|没有|尚无|未定)'
        )
        $hasUnfinished = $false
        foreach ($unfinishedPattern in $unfinishedPatterns) {
            if ($riskFlat -match $unfinishedPattern) {
                $hasUnfinished = $true
                break
            }
        }
        if (-not $hasUnfinished) {
            Add-ValidationError 'E_LAST_RISK_UNFINISHED: 章末风险段未明确提示核谎尚未完成。'
        }

        $snapshotMatch = $null
        if ($separatorEndIndex -ge 0) {
            $afterSeparator = $normalized.Substring($separatorEndIndex)
            $snapshotMatch = [regex]::Match(
                $afterSeparator,
                '(?m)^[ \t]*##[ \t]+(?:第一章)?章末状态快照[ \t]*$'
            )
        }

        if ($null -eq $snapshotMatch -or -not $snapshotMatch.Success) {
            Add-ValidationError 'E_SNAPSHOT_HEADING_AFTER_SEPARATOR: 正文分隔线后缺少“## 章末状态快照”或“## 第一章章末状态快照”。'
        }
        else {
            $snapshot = $afterSeparator.Substring($snapshotMatch.Index + $snapshotMatch.Length).Trim()
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
        Add-ValidationError ('E_READ_OR_PARSE: 读取或解析失败：{0}' -f $_.Exception.Message)
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
