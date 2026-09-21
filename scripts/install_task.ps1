# Install FrenchDaily as a Windows Scheduled Task
# Run with: powershell -ExecutionPolicy Bypass -File scripts\install_task.ps1

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$root = Split-Path -Parent $root
$bat = Join-Path $root "scripts\daily.bat"

if (-not (Test-Path $bat)) {
    Write-Error "daily.bat not found at $bat"
    exit 1
}

# Remove existing task if present
Unregister-ScheduledTask -TaskName "FrenchDaily" -Confirm:$false -ErrorAction SilentlyContinue

# Read cron from config.toml
$configPath = Join-Path $root "config.toml"
$cron = "0 17 * * *"  # default: 5 PM

if (Test-Path $configPath) {
    $config = Get-Content $configPath -Raw
    if ($config -match 'cron\s*=\s*"([^"]+)"') {
        $cron = $Matches[1]
    }
}

Write-Host "Installing FrenchDaily scheduled task with cron: $cron"

# Parse cron for hour
$hour = 17  # default
if ($cron -match '^0\s+(\d+)\s+\*') {
    $hour = [int]$Matches[1]
}

$triggerTime = (Get-Date).Date.AddHours($hour)
if ($triggerTime -lt (Get-Date)) {
    $triggerTime = $triggerTime.AddDays(1)
}

Write-Host "Scheduled for daily at ${hour}:00"

$action = New-ScheduledTaskAction -Execute "cmd.exe" -Argument "/c `"$bat`""
$trigger = New-ScheduledTaskTrigger -Once -At $triggerTime -RepetitionInterval (New-TimeSpan -Days 1)

# Key: NO StartWhenAvailable — if the PC is off at 5 PM, skip that day.
# DontStartIfOnBatteries is NOT set — runs on battery too.
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -RunOnlyIfNetworkAvailable

$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType S4U -RunLevel Highest

Register-ScheduledTask `
    -TaskName "FrenchDaily" `
    -Description "Daily French learning content build (5 PM)" `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Principal $principal | Out-Null

Write-Host ""
Write-Host "FrenchDaily task installed successfully!"
Write-Host "  Schedule: Daily at ${hour}:00"
Write-Host "  Missed days: SKIPPED (not caught up on boot)"
Write-Host ""
Write-Host "To test now:     schtasks /run /tn FrenchDaily"
Write-Host "To view log:     type logs\cron.log"
Write-Host "To remove:       scripts\uninstall_task.ps1"
