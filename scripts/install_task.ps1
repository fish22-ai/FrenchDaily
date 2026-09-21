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

# Hidden action: wscript.exe runs the batch with window style 0, so the build
# never flashes a console window on the desktop.
$vbs = Join-Path $root "scripts\run_hidden.vbs"
if (-not (Test-Path $vbs)) {
    Write-Error "run_hidden.vbs not found at $vbs"
    exit 1
}
$action = New-ScheduledTaskAction -Execute "wscript.exe" -Argument "//B `"$vbs`""

# A plain daily trigger. (-Once + -RepetitionInterval registers an open-ended
# repetition pattern and is easy to get wrong — this one just repeats daily.)
$trigger = New-ScheduledTaskTrigger -Daily -At $triggerTime

# Key: NO StartWhenAvailable — if the PC is off at 5 PM, skip that day.
# DontStartIfOnBatteries is NOT set — runs on battery too.
# A 1-hour cap means a hung build cannot pile up runs behind it.
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -RunOnlyIfNetworkAvailable `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Hours 1)

$attempts = @(
    @{ Name = "S4U + Highest"; LogonType = "S4U";         RunLevel = "Highest" },
    @{ Name = "S4U + Limited"; LogonType = "S4U";         RunLevel = "Limited" },
    @{ Name = "Interactive";   LogonType = "Interactive"; RunLevel = "Limited" }
)

$installed = $null
foreach ($a in $attempts) {
    $principal = New-ScheduledTaskPrincipal `
        -UserId "$env:USERDOMAIN\$env:USERNAME" `
        -LogonType $a.LogonType `
        -RunLevel $a.RunLevel
    try {
        Register-ScheduledTask `
            -TaskName "FrenchDaily" `
            -Description "Daily French learning content build (5 PM)" `
            -Action $action `
            -Trigger $trigger `
            -Settings $settings `
            -Principal $principal `
            -Force -ErrorAction Stop | Out-Null
        $installed = $a.Name
        break
    } catch {
        Write-Host "  ($($a.Name) refused: $($_.Exception.Message.Trim()))"
    }
}

if (-not $installed) {
    Write-Error "Could not register the task. Re-run this script from an elevated (Run as administrator) PowerShell window."
    exit 1
}

Write-Host ""
Write-Host "FrenchDaily task installed successfully!  [$installed]"
Write-Host "  Schedule: Daily at ${hour}:00"
Write-Host "  Missed days: SKIPPED (not caught up on boot)"
Write-Host ""
Write-Host "To test now:     Start-ScheduledTask -TaskName FrenchDaily"
Write-Host "To view log:     type logs\cron.log"
Write-Host "To remove:       scripts\uninstall_task.ps1"
