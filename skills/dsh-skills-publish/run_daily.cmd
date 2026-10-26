@echo off
rem Daily entry point for the DSH-Skills-Publish scheduled task.
rem Keep this file ASCII-only: cmd.exe reads it with the OEM code page.
rem %~dp0 is this file's own folder, so the skill folder can move to any machine/user.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0publish-dsh-skills.ps1"
exit /b %ERRORLEVEL%
