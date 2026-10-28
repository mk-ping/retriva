$root = "C:\Users\Mehak\OneDrive\Documents\retriva"
$utf8 = New-Object System.Text.UTF8Encoding($false)
function Patch-File($rel, $old, $new) {
    $p = Join-Path $root $rel
    $t = [System.IO.File]::ReadAllText($p)
    if ($t.Contains($new)) { Write-Host "ALREADY $rel" -ForegroundColor Yellow; return }
    if (-not $t.Contains($old)) { Write-Host "NOT FOUND in $rel : $old" -ForegroundColor Red; return }
    [System.IO.File]::WriteAllText($p, $t.Replace($old, $new), $utf8)
    Write-Host "patched $rel" -ForegroundColor Cyan
}
