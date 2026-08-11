# 更新誤裝訂：掃描 OneDrive\誤裝誤訂 的新 xlsx → 解析 → 上傳 Supabase
# 用法： powershell -File update_misload.ps1
$ErrorActionPreference = "Stop"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$py = "C:\Users\26516\AppData\Local\Programs\Python\Python312\python.exe"
$src = "C:\Users\26516\OneDrive\誤裝誤訂"
$out = Join-Path $src ".payloads"
$api = "https://hmqnlovyzlvvnkqmfwtt.supabase.co/functions/v1/misload"

if (Test-Path $out) { Remove-Item "$out\*" -Force }
& $py (Join-Path $PSScriptRoot "parse_misload.py") $src $out
if ($LASTEXITCODE -ne 0) { throw "解析失敗" }

$manifest = Join-Path $out "manifest.txt"
$files = @()
if ((Test-Path $manifest) -and (Get-Item $manifest).Length -gt 0) { $files = Get-Content $manifest -Encoding UTF8 }
if (-not $files) { Write-Output "沒有新檔案需要入庫。"; exit 0 }

$i = 0
foreach ($f in $files) {
    $i++
    $body = [System.IO.File]::ReadAllBytes($f)
    $r = Invoke-RestMethod -Uri $api -Method Post -ContentType "application/json" -Body $body
    Write-Output ("[{0}/{1}] {2} => {3}" -f $i, $files.Count, (Split-Path $f -Leaf), ($r | ConvertTo-Json -Compress))
}

# 全部成功才寫入狀態檔（下次跳過這些檔案）
$pending = Get-Content (Join-Path $out "pending_state.json") -Raw -Encoding UTF8 | ConvertFrom-Json
$state = @{}
foreach ($p in $pending.old.PSObject.Properties) { $state[$p.Name] = $p.Value }
foreach ($p in $pending.new.PSObject.Properties) { $state[$p.Name] = $p.Value }
$state | ConvertTo-Json | Out-File -FilePath $pending.state_file -Encoding utf8
Write-Output "完成：$($files.Count) 個批次已入庫，狀態已更新。"
