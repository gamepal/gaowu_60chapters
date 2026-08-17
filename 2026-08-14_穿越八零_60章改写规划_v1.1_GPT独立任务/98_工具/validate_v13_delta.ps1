param(
    [Parameter(Mandatory = $true)][string]$BasePath,
    [Parameter(Mandatory = $true)][string]$NewPath
)

$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)

function Decode-Utf8([string]$Base64) {
    return [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($Base64))
}

foreach ($path in @($BasePath, $NewPath)) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "File not found: $path"
    }
}

function Get-FrozenText([string]$Path) {
    $lines = @(Get-Content -LiteralPath $Path -Encoding UTF8)
    $out = New-Object System.Collections.Generic.List[string]
    $started = $false
    $section = ''
    $chapter = ''
    $execChapter = ''
    $jiangYuan = Decode-Utf8 '5aec6L+c77ya'
    $noSrc = Decode-Utf8 '5LiN5o+Q5L6bU1JDLTAwMQ=='
    $directRecognition = Decode-Utf8 '5Y+v55u05o6l6K+G5Yir'

    foreach ($line in $lines) {
        if (-not $started) {
            if ($line -match '^## 1\.') {
                $started = $true
                [void]$out.Add($line)
            }
            continue
        }

        if ($line -match '^### ([0-9]+\.[0-9]+) ') {
            $section = $Matches[1]
        }
        if ($line -match '^#### .(\d{3}).') {
            $chapter = $Matches[1]
            $execChapter = ''
            if ($chapter -notin @('001', '002')) { [void]$out.Add($line) }
            continue
        }
        if ($line -match '^### 9\.\d+ .(\d{3}).') {
            $execChapter = $Matches[1]
            $chapter = ''
            if ($execChapter -notin @('001', '002')) { [void]$out.Add($line) }
            continue
        }
        if ($line -match '^## ') {
            $chapter = ''
            $execChapter = ''
        }

        if ($chapter -in @('001', '002')) { continue }
        if ($execChapter -in @('001', '002')) { continue }
        if ($section -in @('9.1', '9.13', '12.1', '12.3', '13.1', '13.2', '14.5', '16.2', '16.3')) { continue }
        if ($chapter -eq '060' -and $line -match '179') { continue }
        if ($section -eq '4.4' -and $line.StartsWith('- ' + $jiangYuan)) { continue }
        if ($line.Contains($directRecognition)) { continue }
        if ($line -match '^\| M-01') { continue }
        if ($line -match '^\| M-02') { continue }
        if ($line -match '^\| .{0,10}10.{0,10}\|.*M-01') { continue }
        if ($section -eq '13.3' -and $line -match 'v1\.[234]_GPT') { continue }
        if ($section -eq '16.1' -and $line.StartsWith('9. ' + $noSrc)) { continue }

        [void]$out.Add($line)
    }

    $joined = [string]::Join("`n", $out)
    return [regex]::Replace($joined, "(`n\s*){2,}", "`n`n")
}

$baseRaw = Get-Content -LiteralPath $BasePath -Raw -Encoding UTF8
$newRaw = Get-Content -LiteralPath $NewPath -Raw -Encoding UTF8
$baseFrozen = Get-FrozenText -Path $BasePath
$newFrozen = Get-FrozenText -Path $NewPath
$errors = New-Object System.Collections.Generic.List[string]

if ($baseFrozen -cne $newFrozen) {
    [void]$errors.Add('Frozen regions differ outside the v1.3 authorized ranges')
}

$chapterCards = [regex]::Matches($newRaw, '(?m)^#### .(\d{3}).').Count
$execCards = [regex]::Matches($newRaw, '(?m)^### 9\.\d+ .\d{3}.').Count
if ($chapterCards -ne 60) { [void]$errors.Add("Expected 60 chapter cards; found $chapterCards") }
if ($execCards -ne 10) { [void]$errors.Add("Expected 10 execution cards; found $execCards") }
if ($newRaw -notmatch 'v1\.3 GPT') { [void]$errors.Add('v1.3 title marker missing') }
if ($newRaw -match 'v1\.2') { [void]$errors.Add('v1.2 residue found in standalone v1.3 plan') }
if ($newRaw -match '[A-Z]:\\') { [void]$errors.Add('Absolute local path found') }

$anchors = [ordered]@{
    AdultExam = '1986.{0,40}5.{0,10}10.{0,5}11'
    Flow240 = '60\+137\+43=240'
    Disposal240 = '215[\s\S]{0,250}?8[\s\S]{0,500}?17'
    Receivable198 = '198\.00.{0,80}=0'
    Refund6020 = '60\.20'
    Crisis411 = '411'
    ClosingCash179 = '179'
    ClosingDebt80 = '80'
    LetterAsset = '\| A-07 \|[\s\S]{0,180}?25'
    KeyHandoff = 'M-01[^\r\n]*A-01'
    PreIssueStop = 'L-840611[^\r\n]*L-840615[^\r\n]*6.{0,5}20'
    IndependentFive = 'L-840622.L-840629.L-840705.L-840711.L-840718'
    EmptyDrumHook = 'Z-03'
    M02Balance = '\| M-02[^\r\n]*180'
    FinalAssetState = '#### .060.[\s\S]{0,3000}?M-01[\s\S]{0,250}?M-02'
}

$anchorResults = [ordered]@{}
foreach ($key in $anchors.Keys) {
    $ok = [regex]::IsMatch($newRaw, $anchors[$key])
    $anchorResults[$key] = $ok
    if (-not $ok) { [void]$errors.Add("Required anchor missing: $key") }
}

$phraseChecks = [ordered]@{
    M01GiftA = '5ama5YmN5piO56Gu6LWg5LiO'
    M01GiftB = '5oi35ZCN5Li65aec55G2'
    EarlyEmotionA = '5YmNMzAw5rGJ5a2X'
    EarlyEmotionB = '5Lqh5YWE5oqa5oGk5qy+'
    FourPersonA = '5Li75Yay56qB5pyA5aSa'
    FourPersonB = '5Zub5Lq6'
    OverDescription = '6Kem5oSf77yL5q+U5Za777yL5b+D55CG5oC757uT'
    PublicConcession = '5rKI5a625LiN5ou/6L+Z56yU5oqa5oGk6ZKx'
    WitnessA = '5rKI56yR56yR5Y+r5Yiw5aCC5bGL6Zeo5Y+j'
    WitnessB = '6KeB6K+B'
    PureHook = '5Y+q6JC95Lik5Liq5aSW6YOo5Yqo5L2c'
}

$decoded = [ordered]@{}
foreach ($key in $phraseChecks.Keys) {
    $value = Decode-Utf8 $phraseChecks[$key]
    $ok = $newRaw.Contains($value)
    $decoded[$key] = $ok
    if (-not $ok) { [void]$errors.Add("Required UTF-8 phrase missing: $key") }
}
$anchorResults['Utf8Phrases'] = [pscustomobject]$decoded

$sha = [System.Security.Cryptography.SHA256]::Create()
try {
    $baseFrozenHash = ([BitConverter]::ToString($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($baseFrozen)))).Replace('-', '')
    $newFrozenHash = ([BitConverter]::ToString($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($newFrozen)))).Replace('-', '')
} finally {
    $sha.Dispose()
}

$result = [pscustomobject]@{
    Status = if ($errors.Count -eq 0) { 'PASS' } else { 'FAIL' }
    ErrorCount = $errors.Count
    Errors = @($errors)
    ChapterCards = $chapterCards
    FirstTenExecutionCards = $execCards
    FrozenRegionsEqual = ($baseFrozen -ceq $newFrozen)
    BaseFrozenSHA256 = $baseFrozenHash
    NewFrozenSHA256 = $newFrozenHash
    Anchors = [pscustomobject]$anchorResults
    BaseSHA256 = (Get-FileHash -LiteralPath $BasePath -Algorithm SHA256).Hash
    NewSHA256 = (Get-FileHash -LiteralPath $NewPath -Algorithm SHA256).Hash
}

$result | ConvertTo-Json -Depth 6
if ($errors.Count -gt 0) { exit 1 }
