param(
    [Parameter(Mandatory = $true)]
    [string]$PlanPath
)

$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)

if (-not (Test-Path -LiteralPath $PlanPath -PathType Leaf)) {
    throw "Plan file not found: $PlanPath"
}

$lines = @(Get-Content -LiteralPath $PlanPath -Encoding UTF8)
$raw = [string]::Join("`n", $lines)
$errors = New-Object System.Collections.Generic.List[string]

$chapterIndexes = New-Object System.Collections.Generic.List[int]
$chapterNumbers = New-Object System.Collections.Generic.List[int]
for ($i = 0; $i -lt $lines.Count; $i++) {
    if ($lines[$i] -match '^#### .(\d{3}).') {
        $chapterIndexes.Add($i)
        $chapterNumbers.Add([int]$Matches[1])
    }
}

if ($chapterNumbers.Count -ne 60) {
    $errors.Add("Expected 60 chapter cards; found $($chapterNumbers.Count)")
}

$expected = @(1..60)
for ($i = 0; $i -lt [Math]::Min($chapterNumbers.Count, 60); $i++) {
    if ($chapterNumbers[$i] -ne $expected[$i]) {
        $errors.Add("Chapter sequence mismatch at index ${i}: $($chapterNumbers[$i])")
    }
}

$duplicates = @($chapterNumbers | Group-Object | Where-Object { $_.Count -gt 1 })
if ($duplicates.Count -gt 0) {
    $errors.Add("Duplicate chapter numbers: " + (($duplicates | ForEach-Object Name) -join ','))
}

for ($i = 0; $i -lt $chapterIndexes.Count; $i++) {
    $start = $chapterIndexes[$i] + 1
    if ($i + 1 -lt $chapterIndexes.Count) {
        $end = $chapterIndexes[$i + 1] - 1
    } else {
        $section9 = -1
        for ($j = $start; $j -lt $lines.Count; $j++) {
            if ($lines[$j] -match '^## 9\.') { $section9 = $j; break }
        }
        if ($section9 -ge 0) { $end = $section9 - 1 } else { $end = $lines.Count - 1 }
    }
    $bulletCount = 0
    for ($j = $start; $j -le $end; $j++) {
        if ($lines[$j] -match '^- ') { $bulletCount++ }
    }
    if ($bulletCount -lt 6) {
        $errors.Add("Chapter $($chapterNumbers[$i]) has fewer than six card fields: $bulletCount")
    }
}

$execCards = @($lines | Where-Object { $_ -match '^### 9\.\d+ .\d{3}.' }).Count
if ($execCards -ne 10) {
    $errors.Add("Expected 10 first-ten execution cards; found $execCards")
}

$absolutePaths = @($lines | Where-Object { $_ -match '[A-Z]:\\' })
if ($absolutePaths.Count -gt 0) {
    $errors.Add("Final plan contains absolute local paths: $($absolutePaths.Count)")
}

if ($raw -notmatch '1986.{0,40}5.{0,10}10.{0,5}11') {
    $errors.Add('Adult-exam date anchor was not found')
}
if ($raw -notmatch '240.{0,80}60.{0,30}137.{0,30}43') {
    $errors.Add('Problem-batch 240=60+137+43 anchor was not found')
}

$result = [pscustomobject]@{
    PlanPath = (Resolve-Path -LiteralPath $PlanPath).Path
    Lines = $lines.Count
    Bytes = (Get-Item -LiteralPath $PlanPath).Length
    ChapterCards = $chapterNumbers.Count
    FirstTenExecutionCards = $execCards
    ErrorCount = $errors.Count
    Errors = @($errors)
    SHA256 = (Get-FileHash -LiteralPath $PlanPath -Algorithm SHA256).Hash
}

$result | ConvertTo-Json -Depth 4
if ($errors.Count -gt 0) { exit 1 }
