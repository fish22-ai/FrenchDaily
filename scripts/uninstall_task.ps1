# Uninstall FrenchDaily Windows Scheduled Task
# Run with: powershell -ExecutionPolicy Bypass -File scripts\uninstall_task.ps1

$ErrorActionPreference = "SilentlyContinue"

Unregister-ScheduledTask -TaskName "FrenchDaily" -Confirm:$false

if ($?) {
    Write-Host "FrenchDaily task removed."
} else {
    Write-Host "No FrenchDaily task found (or already removed)."
}
