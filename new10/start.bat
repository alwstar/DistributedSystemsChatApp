@echo off
REM Open command line
start cmd /k "cd /d C:\git\DistributedSystemsChatApp\new10 && python s1.py"
timeout /t 1 /nobreak >nul
start cmd /k "cd /d C:\git\DistributedSystemsChatApp\new10 && python c1.py"