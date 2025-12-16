@echo off
chcp 65001 >nul
"C:\Users\ftbbo\Nextcloud4\OneDrive Backup\Documents (sync'd)\Development\Nexus\.venv\Scripts\python.exe" -u -X utf8 "C:\Users\ftbbo\Nextcloud4\OneDrive Backup\Documents (sync'd)\Development\Nexus\core\scan_episodic_pivots.py" >> "C:\Users\ftbbo\Nextcloud4\OneDrive Backup\Documents (sync'd)\Development\Nexus\data\ep_auto.log" 2>&1