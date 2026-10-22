@echo off
rem Daily entry point for the DSH-Skills-Publish scheduled task.
rem Keep this file ASCII-only: cmd.exe reads it with the OEM code page.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "C:\Users\admin\.dsh\skills\dsh-skills-publish\publish-dsh-skills.ps1"
exit /b %ERRORLEVEL%
