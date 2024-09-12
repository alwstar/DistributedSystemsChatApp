@echo off
REM Open command line
start cmd /k "cd /d C:\git\DistributedSystemsChatApp && python server17.py"
timeout /t 1 /nobreak >nul
start cmd /k "cd /d C:\git\DistributedSystemsChatApp && python server17.py"
timeout /t 1 /nobreak >nul
start cmd /k "cd /d C:\git\DistributedSystemsChatApp && python server17.py"
timeout /t 16 /nobreak >nul
start cmd /k "cd /d C:\git\DistributedSystemsChatApp && python client17.py"
timeout /t 1 /nobreak >nul
start cmd /k "cd /d C:\git\DistributedSystemsChatApp && python client17.py"