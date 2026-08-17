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
    $mode = 'skip-top'
    $skipEntry93 = $false

    foreach ($line in $lines) {
        if ($mode -eq 'skip-top') {
            if ($line -match '^## 1\.') {
                $mode = 'normal'
                [void]$out.Add($line)
            }
            continue
        }

        if ($mode -eq 'skip-ch1') {
            if ($line -match '^#### .002.') {
                $mode = 'normal'
                [void]$out.Add($line)
            }
            continue
        }

        if ($mode -eq 'skip-91-92') {
            if ($line -match '^### 9\.3 ') {
                $mode = 'normal'
                $skipEntry93 = $true
                [void]$out.Add($line)
            }
            continue
        }

        if ($mode -eq 'skip-12-13') {
            if ($line -match '^## 14\.') {
                $mode = 'normal'
                [void]$out.Add($line)
            }
            continue
        }

        if ($line -match '^#### .001.') {
            $mode = 'skip-ch1'
            continue
        }
        if ($line -match '^### 9\.1 ') {
            $mode = 'skip-91-92'
            continue
        }
        if ($line -match '^## 12\.') {
            $mode = 'skip-12-13'
            continue
        }
        if ($line -match '^## 16\.') {
            break
        }

        if ($skipEntry93 -and $line -match '^- ') {
            $skipEntry93 = $false
            continue
        }

        [void]$out.Add($line)
    }

    return [string]::Join("`n", $out)
}

$baseRaw = Get-Content -LiteralPath $BasePath -Raw -Encoding UTF8
$newRaw = Get-Content -LiteralPath $NewPath -Raw -Encoding UTF8
$baseFrozen = Get-FrozenText -Path $BasePath
$newFrozen = Get-FrozenText -Path $NewPath
$errors = New-Object System.Collections.Generic.List[string]

if ($baseFrozen -cne $newFrozen) {
    [void]$errors.Add('Frozen regions differ outside the approved change ranges')
}

$chapterCards = [regex]::Matches($newRaw, '(?m)^#### .(\d{3}).').Count
$execCards = [regex]::Matches($newRaw, '(?m)^### 9\.\d+ .\d{3}.').Count
if ($chapterCards -ne 60) { [void]$errors.Add("Expected 60 chapter cards; found $chapterCards") }
if ($execCards -ne 10) { [void]$errors.Add("Expected 10 execution cards; found $execCards") }
if ($newRaw -notmatch 'v1\.1 GPT') { [void]$errors.Add('v1.1 title marker missing') }
if ($newRaw -match 'v1\.0') { [void]$errors.Add('v1.0 residue found in standalone v1.1 plan') }
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
}

$anchorResults = [ordered]@{}
foreach ($key in $anchors.Keys) {
    $ok = [regex]::IsMatch($newRaw, $anchors[$key])
    $anchorResults[$key] = $ok
    if (-not $ok) { [void]$errors.Add("Required hard anchor missing: $key") }
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
    HardAnchors = [pscustomobject]$anchorResults
    BaseSHA256 = (Get-FileHash -LiteralPath $BasePath -Algorithm SHA256).Hash
    NewSHA256 = (Get-FileHash -LiteralPath $NewPath -Algorithm SHA256).Hash
}

$result | ConvertTo-Json -Depth 5
if ($errors.Count -gt 0) { exit 1 }
