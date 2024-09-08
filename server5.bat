@echo off
REM Open command line
start cmd /k "cd /d C:\git\DistributedSystemsChatApp && python server3.py 6005"
timeout /t 3 /nobreak >nul
start cmd /k "cd /d C:\git\DistributedSystemsChatApp && python server3.py 6006"
timeout /t 3 /nobreak >nul
start cmd /k "cd /d C:\git\DistributedSystemsChatApp && python server3.py 6007"
timeout /t 3 /nobreak >nul
start cmd /k "cd /d C:\git\DistributedSystemsChatApp && python server3.py 6008"