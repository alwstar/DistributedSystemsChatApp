@echo off
REM Open command line
start cmd /k "cd /d C:\git\DistributedSystemsChatApp && python s1.py"
timeout /t 2 /nobreak >nul
start cmd /k "cd /d C:\git\DistributedSystemsChatApp && python c1.py"