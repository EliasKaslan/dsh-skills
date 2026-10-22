@echo off
set "PS=C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"
set "SC=C:\Users\admin\.dsh\skills\dsh-repo-sync\sync-dsh-repos.ps1"
"%PS%" -NoProfile -ExecutionPolicy Bypass -File "%SC%"
exit /b %ERRORLEVEL%
