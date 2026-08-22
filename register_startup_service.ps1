$action = New-ScheduledTaskAction -Execute "python.exe" -Argument "C:\Users\Roshan.Sah\itom\scripts\start_server.py" -WorkingDirectory "C:\Users\Roshan.Sah\itom"
$trigger = New-ScheduledTaskTrigger -AtLogon
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
Register-ScheduledTask -TaskName "ITOM_Portal_Server" -Action $action -Trigger $trigger -Settings $settings -Description "ITOM On-Premise Production Server & Telemetry Auto-Sync Engine" -Force
