<# Register/start the local ITOM supervisor for the signed-in Windows user. #>
[CmdletBinding()]
param([switch]$Status, [switch]$Remove)
$ErrorActionPreference = 'Stop'

$taskName = 'ITOM Local Portal and Sync'
$root = Split-Path -Parent $PSScriptRoot

if ($Remove) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue
    Write-Host "Removed task: $taskName"
    exit 0
}
if ($Status) {
    try { $task = Get-ScheduledTask -TaskName $taskName -ErrorAction Stop }
    catch { Write-Error 'Task status is not readable in this shell. Run this status command from an elevated PowerShell window.'; exit 2 }
    if (-not $task) { Write-Host 'Task is not registered.'; exit 1 }
    $info = Get-ScheduledTaskInfo -TaskName $taskName
    [pscustomobject]@{ Name=$task.TaskName; State=$task.State; LastRun=$info.LastRunTime; LastResult=$info.LastTaskResult } | Format-List
    exit 0
}

$python = Join-Path $root '.venv\Scripts\python.exe'
if (-not (Test-Path $python)) {
    $python = (Get-Command python.exe -ErrorAction Stop).Source
}
$pythonw = Join-Path (Split-Path $python) 'pythonw.exe'
if (Test-Path $pythonw) { $python = $pythonw }
$script = Join-Path $root 'scripts\local_itom_supervisor.py'
$action = New-ScheduledTaskAction -Execute $python -Argument "`"$script`" --open-browser" -WorkingDirectory $root
$trigger = New-ScheduledTaskTrigger -AtLogOn -User "$env:USERDOMAIN\$env:USERNAME"
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -RestartCount 5 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Description 'Starts the local ITOM web portal and its SQLite-backed scheduled telemetry sync at user sign-in.' -Force | Out-Null
Start-ScheduledTask -TaskName $taskName
Start-Sleep -Seconds 3
$info = Get-ScheduledTaskInfo -TaskName $taskName
Write-Host "Registered and started '$taskName'. Task last result: $($info.LastTaskResult)"
Write-Host 'Portal and API: http://localhost:8080/'
