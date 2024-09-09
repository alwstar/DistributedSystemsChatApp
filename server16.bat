@echo off
REM Open command line
start cmd /k "cd /d C:\git\DistributedSystemsChatApp && python server16.py"
timeout /t 1 /nobreak >nul
start cmd /k "cd /d C:\git\DistributedSystemsChatApp && python server16.py"
timeout /t 1 /nobreak >nul
start cmd /k "cd /d C:\git\DistributedSystemsChatApp && python server16.py"
timeout /t 1 /nobreak >nul
start cmd /k "cd /d C:\git\DistributedSystemsChatApp && python client16.py"