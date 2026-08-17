param(
    [Parameter(Mandatory = $true)][string]$BodyPath
)

$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)

function D([string]$b64) {
    return [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($b64))
}

if (-not (Test-Path -LiteralPath $BodyPath -PathType Leaf)) {
    throw "File not found: $BodyPath"
}

$raw = Get-Content -LiteralPath $BodyPath -Raw -Encoding UTF8
$lines = @(Get-Content -LiteralPath $BodyPath -Encoding UTF8)
$errors = New-Object System.Collections.Generic.List[string]
$warnings = New-Object System.Collections.Generic.List[string]

$title = D '56ys5LiA56ugIOWtmOaKmOS4jeiDveS6pA=='
$headingIndex = -1
for ($i = 0; $i -lt $lines.Count; $i++) {
    if ($lines[$i] -match ('^#{1,3}\s+' + [regex]::Escape($title) + '\s*$')) {
        $headingIndex = $i
        break
    }
}
if ($headingIndex -lt 0) {
    [void]$errors.Add('Chapter heading missing')
    $body = $raw
} else {
    $bodyLines = @($lines[($headingIndex + 1)..($lines.Count - 1)])
    $stop = $bodyLines.Count
    for ($i = 0; $i -lt $bodyLines.Count; $i++) {
        if ($bodyLines[$i] -eq '---' -or $bodyLines[$i] -match '^##\s') {
            $stop = $i
            break
        }
    }
    if ($stop -eq 0) { $body = '' }
    elseif ($stop -lt $bodyLines.Count) { $body = [string]::Join("`n", $bodyLines[0..($stop - 1)]) }
    else { $body = [string]::Join("`n", $bodyLines) }
}

$han = [regex]::Matches($body, '[\u4e00-\u9fff]')
$hanCount = $han.Count
if ($hanCount -lt 2100 -or $hanCount -gt 2300) {
    [void]$errors.Add("Han count outside 2100-2300: $hanCount")
}

$firstCount = [Math]::Min(300, $han.Count)
$firstHan = ''
if ($firstCount -gt 0) {
    $firstHan = [string]::Join('', @($han | Select-Object -First $firstCount | ForEach-Object { $_.Value }))
}

$firstAnchors = [ordered]@{
    Passbook = D '5a2Y5oqY'
    Pension = D '5oqa5oGk'
    Turnover = D '5ZGo6L2s'
    ShenGuilan = D '5rKI5qGC5YWw'
    JiangYao = D '5aec55G2'
}
foreach ($key in $firstAnchors.Keys) {
    if (-not $firstHan.Contains($firstAnchors[$key])) {
        [void]$errors.Add("First-300 anchor missing: $key")
    }
}
$ownershipOk = $firstHan.Contains((D '5ZCN5LiL')) -or $firstHan.Contains((D '5pys5Lq6'))
if (-not $ownershipOk) { [void]$errors.Add('First-300 ownership anchor missing') }

$requiredFull = [ordered]@{
    JiangYao = D '5aec55G2'
    ShenGuilan = D '5rKI5qGC5YWw'
    ShenJianxun = D '5rKI5bu65YuL'
    ChenLi = D '6ZmI5Li9'
    ShenXiaoxiao = D '5rKI56yR56yR'
}
foreach ($key in $requiredFull.Keys) {
    if (-not $body.Contains($requiredFull[$key])) {
        [void]$errors.Add("Required character missing: $key")
    }
}

foreach ($marker in @('M-01', 'A-01', 'v1.2', 'v0.4', '620')) {
    if ($body.Contains($marker)) { [void]$errors.Add("Internal or restricted marker found: $marker") }
}

$paragraphs = @($body -split '(?:\r?\n){2,}' | ForEach-Object { $_.Trim() } | Where-Object { $_ -ne '' })
if ($paragraphs.Count -lt 2) {
    [void]$errors.Add('Not enough prose paragraphs')
    $lastTwo = ''
} else {
    $lastTwo = [string]::Join("`n", $paragraphs[($paragraphs.Count - 2)..($paragraphs.Count - 1)])
    $firstLast = $paragraphs[$paragraphs.Count - 2]
    $secondLast = $paragraphs[$paragraphs.Count - 1]
    if (-not ($firstLast.Contains((D '6ZKl5YyZ')) -and $firstLast.Contains((D '6Zmi6Zeo5Y+j')))) {
        [void]$errors.Add('Penultimate paragraph lacks key-and-gate action')
    }
    $escortName = $secondLast.Contains((D '5rKI56yR56yR')) -or $secondLast.Contains((D '56yR56yR'))
    if (-not ($escortName -and $secondLast.Contains((D '6Lef')))) {
        [void]$errors.Add('Final paragraph lacks escort order')
    }
}

foreach ($b64 in @('5oSP6K+G5Yiw','5piO55m9','55+l6YGT','5b+D5oOz','6KeB6K+B')) {
    $term = D $b64
    if ($lastTwo.Contains($term)) { [void]$errors.Add("Mental explanation found in final hook: $term") }
}

$overTerms = [ordered]@{
    Chest = D '6IO45Y+j'
    Throat = D '5ZaJ5ZKZ'
    WetShoes = D '5rm/5biD6Z6L'
    Toes = D '6ISa6La+'
    HardCorner = D '56Gs6KeS'
    Chill = D '5YeJ5oSP'
    PorridgeMind = D '5Lmx5oiQ5LiA6ZSF57Kl'
    StepLike = D '5YOP6Lip'
}
foreach ($key in $overTerms.Keys) {
    if ($body.Contains($overTerms[$key])) { [void]$warnings.Add("Over-description term requires manual review: $key") }
}
if ($body.Contains((D '5YWt55m+5LqM5Y2B'))) {
    [void]$warnings.Add('Exact private balance appears in narration; verify that it helps the opening')
}

$result = [ordered]@{
    Status = $(if ($errors.Count -eq 0) { 'PASS' } else { 'FAIL' })
    Path = $BodyPath
    HanCount = $hanCount
    Paragraphs = $paragraphs.Count
    First300Han = $firstHan
    ErrorCount = $errors.Count
    Errors = @($errors)
    WarningCount = $warnings.Count
    Warnings = @($warnings)
    SHA256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $BodyPath).Hash
}

$result | ConvertTo-Json -Depth 5
if ($errors.Count -gt 0) { exit 1 }
