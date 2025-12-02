# Trading Bot Auto-Start Setup Script
# This creates a Windows Scheduled Task to start the bot automatically

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Trading Bot Auto-Start Setup" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

$taskName = "TradingBot-AutoStart"
$scriptPath = "C:\Users\arias\OneDrive\Desktop\trading-bot\start_trading_bot.bat"

# Check if task already exists
$existingTask = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue

if ($existingTask) {
    Write-Host "Task '$taskName' already exists." -ForegroundColor Yellow
    $response = Read-Host "Do you want to replace it? (Y/N)"
    if ($response -ne 'Y' -and $response -ne 'y') {
        Write-Host "Setup cancelled." -ForegroundColor Red
        exit
    }
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
    Write-Host "Old task removed." -ForegroundColor Green
}

Write-Host ""
Write-Host "Choose auto-start option:" -ForegroundColor Yellow
Write-Host "  1. Start at 9:00 AM EST every weekday (market days)"
Write-Host "  2. Start at Windows login"
Write-Host "  3. Both (login + 9:00 AM backup)"
Write-Host ""
$choice = Read-Host "Enter choice (1, 2, or 3)"

$action = New-ScheduledTaskAction -Execute $scriptPath

switch ($choice) {
    "1" {
        # 9:00 AM EST, Monday-Friday
        $trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At 9:00AM
        Write-Host "Setting up daily start at 9:00 AM (weekdays only)..." -ForegroundColor Cyan
    }
    "2" {
        # At login
        $trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
        Write-Host "Setting up start at Windows login..." -ForegroundColor Cyan
    }
    "3" {
        # Both triggers
        $trigger1 = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At 9:00AM
        $trigger2 = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
        $trigger = @($trigger1, $trigger2)
        Write-Host "Setting up both login and 9:00 AM triggers..." -ForegroundColor Cyan
    }
    default {
        Write-Host "Invalid choice. Using default (9:00 AM weekdays)." -ForegroundColor Yellow
        $trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At 9:00AM
    }
}

# Task settings
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable

# Register the task
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -Description "Automatically starts the Trading Bot" -RunLevel Highest

Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "  Auto-Start Setup Complete!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Host "Task Name: $taskName" -ForegroundColor White
Write-Host "Script: $scriptPath" -ForegroundColor White
Write-Host ""
Write-Host "To manage this task:" -ForegroundColor Yellow
Write-Host "  - Open Task Scheduler (taskschd.msc)"
Write-Host "  - Look for '$taskName' in Task Scheduler Library"
Write-Host ""
Write-Host "To remove auto-start:" -ForegroundColor Yellow
Write-Host "  Unregister-ScheduledTask -TaskName '$taskName'" -ForegroundColor Gray
Write-Host ""

Read-Host "Press Enter to exit"
