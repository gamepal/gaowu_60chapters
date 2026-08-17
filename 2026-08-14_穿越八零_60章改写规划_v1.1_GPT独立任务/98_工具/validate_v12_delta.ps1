param(
    [Parameter(Mandatory = $true)][string]$BasePath,
    [Parameter(Mandatory = $true)][string]$NewPath
)

$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)

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
    $chapterBullet = 0
    $execChapter = ''
    $execBullet = 0

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
            $chapterBullet = 0
            $execChapter = ''
            [void]$out.Add($line)
            continue
        }
        if ($line -match '^### 9\.\d+ .(\d{3}).') {
            $execChapter = $Matches[1]
            $execBullet = 0
            $chapter = ''
            [void]$out.Add($line)
            continue
        }
        if ($line -match '^## ') {
            $chapter = ''
            $execChapter = ''
        }

        if ($line -match '^- ') {
            if ($chapter) { $chapterBullet++ }
            if ($execChapter) { $execBullet++ }
        }

        if ($chapter -in @('018', '019')) { continue }
        if ($section -eq '4.4' -and $line -match '^- .*49.*') { continue }
        if ($line -match '^\| M-04 \|') { continue }
        if ($line -match '^\| A-07 \|') { continue }
        if ($line -match '^L-840611.*L-840615.*L-840622') { continue }
        if ($line -match 'L-840611.*L-840615.*L-840622.*L-840629.*L-840705.*L-840711.*L-840718') { continue }
        if ($line -match 'v1\.[23]_GPT') { continue }
        if ($chapter -eq '001' -and $chapterBullet -in @(1, 5)) { continue }
        if ($chapter -eq '003' -and $chapterBullet -eq 3) { continue }
        if ($chapter -eq '053' -and $chapterBullet -eq 6) { continue }
        if ($execChapter -eq '001' -and $execBullet -eq 9) { continue }
        if ($execChapter -eq '002' -and $execBullet -eq 4) { continue }
        if ($execChapter -eq '003' -and $execBullet -in @(1, 4, 5)) { continue }

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
    [void]$errors.Add('Frozen regions differ outside the v1.2 authorized repair ranges')
}

$chapterCards = [regex]::Matches($newRaw, '(?m)^#### .(\d{3}).').Count
$execCards = [regex]::Matches($newRaw, '(?m)^### 9\.\d+ .\d{3}.').Count
if ($chapterCards -ne 60) { [void]$errors.Add("Expected 60 chapter cards; found $chapterCards") }
if ($execCards -ne 10) { [void]$errors.Add("Expected 10 execution cards; found $execCards") }
if ($newRaw -notmatch 'v1\.2 GPT') { [void]$errors.Add('v1.2 title marker missing') }
if ($newRaw -match 'v1\.1') { [void]$errors.Add('v1.1 residue found in standalone v1.2 plan') }
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
}

$anchorResults = [ordered]@{}
foreach ($key in $anchors.Keys) {
    $ok = [regex]::IsMatch($newRaw, $anchors[$key])
    $anchorResults[$key] = $ok
    if (-not $ok) { [void]$errors.Add("Required anchor missing: $key") }
}

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

$result | ConvertTo-Json -Depth 5
if ($errors.Count -gt 0) { exit 1 }
