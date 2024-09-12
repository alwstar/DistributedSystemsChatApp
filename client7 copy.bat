@echo off
REM Open command line
start cmd /k "cd /d C:\git\DistributedSystemsChatApp && python client7.py 7001"
timeout /t 1 /nobreak >nul
start cmd /k "cd /d C:\git\DistributedSystemsChatApp && python client7.py 7002"