@echo off
REM Open command line
start cmd /k "cd /d C:\git\DistributedSystemsChatApp\new12 && python s.py"
timeout /t 1 /nobreak >nul
start cmd /k "cd /d C:\git\DistributedSystemsChatApp\new12 && python s.py"