# Registers (or re-registers) the KalshiShadowLogger scheduled task, which runs
# the v16 record-only lead-lag shadow logger persistently via run_shadow_logger.ps1.
# Mirrors the KalshiLiveBot task config (AtLogOn, Interactive, RestartCount 99).
# Idempotent: unregisters any existing task of the same name first. Run once.

$ErrorActionPreference = "Stop"
$TaskName = "KalshiShadowLogger"
$ProjectRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$Supervisor = Join-Path $ProjectRoot "scripts\v16\run_shadow_logger.ps1"

if (-not (Test-Path $Supervisor)) { throw "Supervisor not found: $Supervisor" }

$existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($existing) {
    Write-Host "Removing existing $TaskName task..."
    Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
}

$Action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$Supervisor`"" `
    -WorkingDirectory $ProjectRoot

$Trigger = New-ScheduledTaskTrigger -AtLogOn -User "$env:USERDOMAIN\$env:USERNAME"

$Principal = New-ScheduledTaskPrincipal -UserId "$env:USERNAME" `
    -LogonType Interactive -RunLevel Limited

$Settings = New-ScheduledTaskSettingsSet `
    -MultipleInstances IgnoreNew `
    -RestartCount 99 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit (New-TimeSpan -Days 1825) `
    -StartWhenAvailable `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries

Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger `
    -Principal $Principal -Settings $Settings `
    -Description "v16 record-only lead-lag shadow logger (no orders placed)" | Out-Null

Write-Host "Registered $TaskName. Starting it now..."
Start-ScheduledTask -TaskName $TaskName
Start-Sleep -Seconds 4
$t = Get-ScheduledTask -TaskName $TaskName
"$TaskName state: $($t.State)"
