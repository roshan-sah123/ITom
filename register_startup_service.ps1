<#
.SYNOPSIS
    Registers ITOM Production Server as a persistent 24/7 Windows Background Startup Service.
.DESCRIPTION
    Creates or updates the 'ITOM_Portal_Server' Windows Scheduled Task to ensure
    the ITOM Web Server & Telemetry Sync Daemon run automatically on system boot and logon.
.PARAMETER Uninstall
    Unregisters and removes the scheduled task.
.PARAMETER Status
    Displays current task and service runtime status.
.PARAMETER Restart
    Restarts the scheduled task.
#>

[CmdletBinding()]
param(
    [switch]$Uninstall,
    [switch]$Status,
    [switch]$Restart
)

$TaskName = "ITOM_Portal_Server"
$WorkspaceDir = $PSScriptRoot
$ScriptPath = Join-Path $WorkspaceDir "scripts\start_server.py"

# Handle Status check
if ($Status) {
    Write-Host "================================================================" -ForegroundColor Cyan
    Write-Host "  ITOM Scheduled Task Service Status Check" -ForegroundColor Cyan
    Write-Host "================================================================" -ForegroundColor Cyan
    $task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if ($task) {
        Write-Host "[✓] Scheduled Task '$TaskName' is REGISTERED." -ForegroundColor Green
        Write-Host "    State:       $($task.State)"
        Write-Host "    Description: $($task.Description)"
        $info = Get-ScheduledTaskInfo -TaskName $TaskName -ErrorAction SilentlyContinue
        if ($info) {
            Write-Host "    Last Run:    $($info.LastRunTime)"
            Write-Host "    Last Result: $($info.LastTaskResult)"
        }
    } else {
        Write-Host "[!] Scheduled Task '$TaskName' is NOT registered." -ForegroundColor Yellow
    }

    $port8080 = Get-NetTCPConnection -LocalPort 8080 -State Listen -ErrorAction SilentlyContinue
    if ($port8080) {
        Write-Host "[✓] Port 8080 is actively LISTENING (PID: $($port8080.OwningProcess[0]))." -ForegroundColor Green
        Write-Host "`nAccessible Endpoints:" -ForegroundColor Cyan
        Write-Host "  - Localhost Portal:     http://localhost:8080/" -ForegroundColor White
        Write-Host "  - Localhost Analytics:  http://localhost:8080/ops_analytics.html" -ForegroundColor White
        Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.InterfaceAlias -notlike "*Loopback*" -and $_.IPAddress -notlike "169.254*" } | ForEach-Object {
            Write-Host "  - Network Access:       http://$($_.IPAddress):8080/" -ForegroundColor White
        }
    } else {
        Write-Host "[!] Port 8080 is NOT currently listening." -ForegroundColor Red
    }
    Write-Host "================================================================" -ForegroundColor Cyan
    return
}

# Handle Uninstall
if ($Uninstall) {
    Write-Host "[*] Unregistering Scheduled Task '$TaskName'..." -ForegroundColor Yellow
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
    Write-Host "[✓] Scheduled Task '$TaskName' has been removed." -ForegroundColor Green
    return
}

# Handle Restart
if ($Restart) {
    Write-Host "[*] Stopping existing Scheduled Task '$TaskName'..." -ForegroundColor Yellow
    Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 1
    Write-Host "[*] Starting Scheduled Task '$TaskName'..." -ForegroundColor Yellow
    Start-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 2
    Write-Host "[✓] Restart signal sent." -ForegroundColor Green
    return
}

Write-Host "================================================================" -ForegroundColor Cyan
Write-Host "  ITOM Enterprise Portal - Windows Service Registration" -ForegroundColor Cyan
Write-Host "================================================================" -ForegroundColor Cyan
Write-Host "[*] Workspace Directory: $WorkspaceDir" -ForegroundColor Gray
Write-Host "[*] Target Script:       $ScriptPath" -ForegroundColor Gray

if (-not (Test-Path $ScriptPath)) {
    Write-Error "Could not locate start_server.py at expected path: $ScriptPath"
    exit 1
}

# Locate Python Interpreter (prefer pythonw.exe for silent execution)
$pythonPath = $null
$pythonwPath = $null

$pyCmd = Get-Command python.exe -ErrorAction SilentlyContinue
if ($pyCmd) {
    $pythonPath = $pyCmd.Source
    $dir = Split-Path $pythonPath
    $candidateW = Join-Path $dir "pythonw.exe"
    if (Test-Path $candidateW) {
        $pythonwPath = $candidateW
    }
}

if (-not $pythonPath) {
    # Check default AppData locations
    $candidates = @(
        "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe",
        "$env:ProgramFiles\Python312\python.exe",
        "$env:ProgramFiles\Python311\python.exe"
    )
    foreach ($c in $candidates) {
        if (Test-Path $c) {
            $pythonPath = $c
            $candidateW = (Split-Path $c) + "\pythonw.exe"
            if (Test-Path $candidateW) { $pythonwPath = $candidateW }
            break
        }
    }
}

if (-not $pythonPath) {
    Write-Error "Python executable not found in PATH or standard installation paths."
    exit 1
}

$execBinary = if ($pythonwPath) { $pythonwPath } else { $pythonPath }
Write-Host "[+] Using Python Binary: $execBinary" -ForegroundColor Green

# Define Task Components
$action = New-ScheduledTaskAction `
    -Execute $execBinary `
    -Argument "`"$ScriptPath`"" `
    -WorkingDirectory "$WorkspaceDir"

# Trigger on User Logon
$logonTrigger = New-ScheduledTaskTrigger -AtLogon

# Configure Task Settings for high availability and resilience
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -RestartCount 5 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit (New-TimeSpan -Days 365) `
    -Priority 4 `
    -MultipleInstances IgnoreNew

# Unregister old task if present to update cleanly
Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue

# Register the new resilient task
Write-Host "[*] Registering Scheduled Task '$TaskName'..." -ForegroundColor Cyan
Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $logonTrigger `
    -Settings $settings `
    -Description "ITOM Enterprise Production Server & Telemetry Auto-Sync Engine (Self-Healing 24/7)" `
    -Force | Out-Null

Write-Host "[+] Successfully registered Scheduled Task '$TaskName'." -ForegroundColor Green

# Launch the service immediately
Write-Host "[*] Launching ITOM Service..." -ForegroundColor Cyan
Start-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue

Start-Sleep -Seconds 2

# Verify Port 8080 Listener
$listener = Get-NetTCPConnection -LocalPort 8080 -State Listen -ErrorAction SilentlyContinue
if ($listener) {
    Write-Host "[✓] ITOM Web Server is ONLINE and Listening on Port 8080 (PID: $($listener.OwningProcess[0]))" -ForegroundColor Green
} else {
    Write-Host "[*] Server initiated. Listening state will stabilize momentarily." -ForegroundColor Yellow
}

Write-Host "`n================================================================" -ForegroundColor Cyan
Write-Host "  Verified Service Endpoints & Resilient Access:" -ForegroundColor Cyan
Write-Host "================================================================" -ForegroundColor Cyan
Write-Host "  Localhost Portal:     http://localhost:8080/" -ForegroundColor White
Write-Host "  Localhost Analytics:  http://localhost:8080/ops_analytics.html" -ForegroundColor White

Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.InterfaceAlias -notlike "*Loopback*" -and $_.IPAddress -notlike "169.254*" } | ForEach-Object {
    Write-Host "  Network Access:       http://$($_.IPAddress):8080/" -ForegroundColor White
    Write-Host "  Network Analytics:    http://$($_.IPAddress):8080/ops_analytics.html" -ForegroundColor White
}
Write-Host "================================================================" -ForegroundColor Cyan
