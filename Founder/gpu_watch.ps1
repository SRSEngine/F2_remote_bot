# gpu_watch.ps1 — کدام برنامه GPU و CPU مصرف می‌کند (فقط شمارنده‌های ویندوز را می‌خواند، به ریموت دست نمی‌زند)
#   powershell -ExecutionPolicy Bypass -File gpu_watch.ps1            (۳۰ ثانیه)
#   powershell -ExecutionPolicy Bypass -File gpu_watch.ps1 -Seconds 60
# وقتی ربات در حال کار است اجرا کنید. خروجی در gpu_watch.txt کنار همین فایل هم ذخیره می‌شود.
param([int]$Seconds = 30)

$n = [math]::Max(1, [int]($Seconds / 2))
$cores = [Environment]::ProcessorCount
Write-Host "اندازه‌گیری $Seconds ثانیه..."

$cpu0 = @{}; Get-Process | ForEach-Object { $cpu0[$_.Id] = $_.TotalProcessorTime.TotalMilliseconds }
$t0 = Get-Date
$s = Get-Counter '\GPU Engine(*)\Utilization Percentage' -SampleInterval 2 -MaxSamples $n
$wall = ((Get-Date) - $t0).TotalMilliseconds

$gpu = @{}
foreach ($set in $s) {
    foreach ($c in $set.CounterSamples) {
        if ($c.InstanceName -match 'pid_(\d+).*engtype_(.+)$') {
            $k = "$($matches[1])|$($matches[2])"
            $gpu[$k] = [double]$gpu[$k] + $c.CookedValue / $n
        }
    }
}

$rows = foreach ($kv in $gpu.GetEnumerator()) {
    if ($kv.Value -lt 0.05) { continue }
    $procId, $eng = $kv.Key.Split('|')
    $p = Get-Process -Id $procId -ErrorAction SilentlyContinue
    $cpu = 0
    if ($p -and $cpu0.ContainsKey([int]$procId)) {
        $cpu = ($p.TotalProcessorTime.TotalMilliseconds - $cpu0[[int]$procId]) / $wall / $cores * 100
    }
    [pscustomobject]@{ Process = $(if ($p) { $p.ProcessName } else { '?' }); Pid = $procId; Engine = $eng
                       'GPU %' = [math]::Round($kv.Value, 2); 'CPU %' = [math]::Round($cpu, 2) }
}

# برنامه‌های پرمصرف CPU که GPU ندارند هم
$cpuRows = Get-Process | ForEach-Object {
    if ($cpu0.ContainsKey($_.Id)) {
        $c = ($_.TotalProcessorTime.TotalMilliseconds - $cpu0[$_.Id]) / $wall / $cores * 100
        if ($c -ge 0.5) { [pscustomobject]@{ Process = $_.ProcessName; Pid = $_.Id; 'CPU %' = [math]::Round($c, 2) } }
    }
}

$out = @()
$out += "==== GPU (میانگین $Seconds ثانیه) ===="
$out += ($rows | Sort-Object 'GPU %' -Descending | Format-Table -AutoSize | Out-String).TrimEnd()
$out += ""
$out += "==== CPU (بیشتر از ۰٫۵٪) ===="
$out += ($cpuRows | Sort-Object 'CPU %' -Descending | Format-Table -AutoSize | Out-String).TrimEnd()
$out | Tee-Object -FilePath (Join-Path $PSScriptRoot 'gpu_watch.txt')
