@echo off
chcp 65001 >nul
"C:\Users\ftbbo\Nextcloud4\OneDrive Backup\Documents (sync'd)\Development\Nexus\.venv\Scripts\python.exe" -u -X utf8 "C:\Users\ftbbo\Nextcloud4\OneDrive Backup\Documents (sync'd)\Development\Nexus\core\intraday_monitor.py" >> "C:\Users\ftbbo\Nextcloud4\OneDrive Backup\Documents (sync'd)\Development\Nexus\data\sniper.log" 2>&1