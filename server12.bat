@echo off
REM Open command line
start cmd /k "cd /d C:\git\DistributedSystemsChatApp && python server12.py 1"
timeout /t 1 /nobreak >nul
start cmd /k "cd /d C:\git\DistributedSystemsChatApp && python server12.py 2"
timeout /t 1 /nobreak >nul
start cmd /k "cd /d C:\git\DistributedSystemsChatApp && python server12.py 3"
timeout /t 1 /nobreak >nul
start cmd /k "cd /d C:\git\DistributedSystemsChatApp && python server12.py 4"