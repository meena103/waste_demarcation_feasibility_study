# Two-pass, collision-safe rename of images in data\raw per rename_mapping.csv
# Deletes nothing. Touches nothing outside this folder.
# Run:  powershell -ExecutionPolicy Bypass -File ".\apply_rename.ps1"
# Dry run: add  -WhatIfOnly

param([switch]$WhatIfOnly)

$ErrorActionPreference = 'Stop'
$dir = $PSScriptRoot
$csv = Join-Path $dir 'rename_mapping.csv'

if (-not (Test-Path -LiteralPath $csv)) { throw "Mapping CSV not found: $csv" }
$map = Import-Csv -LiteralPath $csv
Write-Host "Mapping rows: $($map.Count)"

# ---- Pre-flight validation (no changes made) ----
$missing = @()
foreach ($row in $map) {
    if (-not (Test-Path -LiteralPath (Join-Path $dir $row.old_name) -PathType Leaf)) {
        $missing += $row.old_name
    }
}
if ($missing.Count -gt 0) {
    throw "Aborting - these source files are missing:`n  " + ($missing -join "`n  ")
}

$dupOld = $map.old_name | Group-Object | Where-Object Count -gt 1
$dupNew = $map.new_name | Group-Object | Where-Object Count -gt 1
if ($dupOld) { throw "Duplicate old_name entries: $($dupOld.Name -join ', ')" }
if ($dupNew) { throw "Duplicate new_name entries: $($dupNew.Name -join ', ')" }

$imgExt  = @('.jpg','.jpeg','.png','.tif','.tiff','.bmp','.webp','.heic','.heif','.gif')
$before  = Get-ChildItem -LiteralPath $dir -File | Where-Object { $imgExt -contains $_.Extension.ToLower() }
Write-Host "Image files present before: $($before.Count)"
if ($before.Count -ne $map.Count) {
    throw "Aborting - folder has $($before.Count) image files but mapping has $($map.Count) rows."
}

if ($WhatIfOnly) {
    $map | ForEach-Object { Write-Host "  $($_.old_name)  ->  $($_.new_name)" }
    Write-Host "`nDry run only. Nothing changed."
    return
}

# ---- Pass 1: unique temp names ----
$stamp = [guid]::NewGuid().ToString('N').Substring(0,8)
$temps = @()
$i = 0
foreach ($row in $map) {
    $i++
    $tmp = "__tmp_${stamp}_$($i.ToString('000'))$([System.IO.Path]::GetExtension($row.old_name).ToLower())"
    Rename-Item -LiteralPath (Join-Path $dir $row.old_name) -NewName $tmp
    $temps += [pscustomobject]@{ Temp = $tmp; Final = $row.new_name }
}
Write-Host "Pass 1 complete: $($temps.Count) files moved to temp names."

# ---- Pass 2: temp -> final ----
foreach ($t in $temps) {
    Rename-Item -LiteralPath (Join-Path $dir $t.Temp) -NewName $t.Final
}
Write-Host "Pass 2 complete: $($temps.Count) files moved to final names."

# ---- Verification ----
$after = Get-ChildItem -LiteralPath $dir -File | Where-Object { $imgExt -contains $_.Extension.ToLower() }
$leftoverTemp = $after | Where-Object { $_.Name -like '__tmp_*' }
$n = $map.Count
$expected = 1..$n | ForEach-Object { "img_$($_.ToString('000')).jpg" }
$actual   = $after.Name | Sort-Object
$gaps     = $expected | Where-Object { $actual -notcontains $_ }
$extra    = $actual   | Where-Object { $expected -notcontains $_ }

Write-Host ""
Write-Host "=== VERIFICATION ==="
Write-Host "Image files after      : $($after.Count)  (before: $($before.Count))"
Write-Host "Leftover temp names    : $($leftoverTemp.Count)"
Write-Host "Expected range         : img_001.jpg .. img_$($n.ToString('000')).jpg"
Write-Host "Missing from sequence  : $(if ($gaps)  { $gaps  -join ', ' } else { 'none' })"
Write-Host "Unexpected extra files : $(if ($extra) { $extra -join ', ' } else { 'none' })"
if ($after.Count -eq $before.Count -and -not $gaps -and -not $extra -and $leftoverTemp.Count -eq 0) {
    Write-Host "RESULT: OK" -ForegroundColor Green
} else {
    Write-Host "RESULT: CHECK ABOVE" -ForegroundColor Yellow
}
