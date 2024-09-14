@echo off
REM Open command line
start cmd /k "cd /d C:\git\DistributedSystemsChatApp\new11 && python s1.py"
timeout /t 2 /nobreak >nul
start cmd /k "cd /d C:\git\DistributedSystemsChatApp\new11 && python c1.py"