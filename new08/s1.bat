@echo off
REM Open command line
start cmd /k "cd /d C:\git\DistributedSystemsChatApp\new03 && python s1.py 6001"
timeout /t 1 /nobreak >nul
start cmd /k "cd /d C:\git\DistributedSystemsChatApp\new03 && python s1.py 6002"
timeout /t 1 /nobreak >nul
start cmd /k "cd /d C:\git\DistributedSystemsChatApp\new03 && python s1.py 6003"
timeout /t 15 /nobreak >nul
start cmd /k "cd /d C:\git\DistributedSystemsChatApp\new03 && python c1.py"