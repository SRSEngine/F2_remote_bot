# run_watchdog.ps1 - one watchdog cycle (Task Scheduler runs it every 10 minutes via run_hidden.vbs)
# 1) cheap check: python wd.py need   (no Claude call when every bot is fine)
# 2) something needs help -> headless Claude (claude -p) follows AGENT.md, output saved in logs\
$ErrorActionPreference = "Continue"
[Console]::OutputEncoding = [Text.Encoding]::UTF8   # claude.exe writes UTF-8 (Persian)
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $here
New-Item -ItemType Directory -Force "$here\logs" | Out-Null
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$log = "$here\logs\watchdog.log"

# one cycle at a time (a long agent run must not overlap the next tick)
# Windows notification (toast) so the user sees when the agent starts / ends
function Show-Toast([string]$title, [string]$text) {
    try {
        [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
        [Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] | Out-Null
        $esc = { param($t) [Security.SecurityElement]::Escape($t) }
        $xml = New-Object Windows.Data.Xml.Dom.XmlDocument
        $xml.LoadXml("<toast><visual><binding template='ToastGeneric'><text>$(& $esc $title)</text><text>$(& $esc $text)</text></binding></visual></toast>")
        $app = '{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe'
        [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($app).Show([Windows.UI.Notifications.ToastNotification]::new($xml))
    } catch { }
}

$lock = "$here\.lock"
if (Test-Path $lock) {
    $age = (Get-Date) - (Get-Item $lock).LastWriteTime
    if ($age.TotalMinutes -lt 30) { Add-Content $log "$stamp skip: previous cycle still running" -Encoding utf8; exit 0 }
}
Set-Content $lock $PID -Encoding ascii
try {
    $env:PYTHONIOENCODING = "utf-8"
    $need = & python wd.py need 2>&1 | Out-String
    if ($LASTEXITCODE -ne 0) { Add-Content $log "$stamp ok: nothing to do" -Encoding utf8; exit 0 }
    Add-Content $log "$stamp need: $($need.Trim() -replace "`r?`n", ' ; ')" -Encoding utf8
    $names = (($need.Trim() -split "`r?`n") | ForEach-Object { ($_ -split ':')[0] }) -join ', '
    Show-Toast "F2 Watchdog: agent started" "Fixing: $names"

    # newest Claude Code binary (VS Code extension), or 'claude' on PATH
    $claude = (Get-Command claude -ErrorAction SilentlyContinue).Source
    if (-not $claude) {
        $claude = Get-ChildItem "$env:USERPROFILE\.vscode\extensions\anthropic.claude-code-*\resources\native-binary\claude.exe" -ErrorAction SilentlyContinue |
            Sort-Object LastWriteTime -Descending | Select-Object -First 1 -ExpandProperty FullName
    }
    if (-not $claude) { Add-Content $log "$stamp ERROR: claude.exe not found" -Encoding utf8; exit 1 }

    $prompt = "Read AGENT.md in this folder and do ONE watchdog run now. Remotes that need help right now:`n$need"
    $out = "$here\logs\run_$stamp.md"
    & $claude -p $prompt `
        --model opus --allowedTools "Bash(python wd.py:*)" "PowerShell(python wd.py:*)" "Read" "Glob" "Grep" `
        --add-dir "$here\..\Report" "$here\..\Play" `
        --max-turns 80 2>&1 | Out-File $out -Encoding utf8
    $code = $LASTEXITCODE
    Add-Content $log "$stamp agent done -> logs\run_$stamp.md (exit $code)" -Encoding utf8
    $took = [int]((Get-Date) - [datetime]::ParseExact($stamp, "yyyyMMdd_HHmmss", $null)).TotalMinutes
    Show-Toast "F2 Watchdog: agent finished ($took min)" "$names - details in Watchdog\Fixes.md"
}
finally {
    Remove-Item $lock -Force -ErrorAction SilentlyContinue
}
