# Install FrenchDaily as a Windows Scheduled Task
# Run with: powershell -ExecutionPolicy Bypass -File scripts\install_task.ps1

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$root = Split-Path -Parent $root
$driver = Join-Path $root "scripts\daily.py"

if (-not (Test-Path $driver)) {
    Write-Error "daily.py not found at $driver"
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

# Windowless action: pythonw.exe has no console subsystem at all, so the run
# can never flash a window on the desktop. The driver (scripts\daily.py) starts
# every child with CREATE_NO_WINDOW, because a windowless parent launching a
# console app (git.exe) would otherwise pop a console.
$pyw = (Get-Command pythonw.exe -ErrorAction SilentlyContinue).Source
if (-not $pyw) {
    $candidate = Join-Path (Split-Path (Get-Command python.exe -ErrorAction SilentlyContinue).Source) "pythonw.exe"
    if (Test-Path $candidate) { $pyw = $candidate }
}
if (-not $pyw) {
    Write-Error "pythonw.exe not found. Install Python (with 'Add to PATH') and re-run this script."
    exit 1
}
$driver = Join-Path $root "scripts\daily.py"
Write-Host "Launcher: $pyw"
$action = New-ScheduledTaskAction -Execute $pyw -Argument "`"$driver`""

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
