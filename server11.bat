@echo off
REM Open command line
start cmd /k "cd /d C:\git\DistributedSystemsChatApp && python server11.py 5001 5101 5201"
timeout /t 1 /nobreak >nul
start cmd /k "cd /d C:\git\DistributedSystemsChatApp && python server11.py 5002 5102 5202"
timeout /t 1 /nobreak >nul
start cmd /k "cd /d C:\git\DistributedSystemsChatApp && python server11.py 5003 5103 5203"
timeout /t 1 /nobreak >nul
start cmd /k "cd /d C:\git\DistributedSystemsChatApp && python server11.py 5004 5104 5204"