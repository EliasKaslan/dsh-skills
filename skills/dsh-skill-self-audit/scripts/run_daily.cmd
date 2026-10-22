@echo off
rem ============================================================
rem  DSH skill self-audit - daily entry point (called by Task
rem  Scheduler task "DSH-Skill-SelfAudit").
rem
rem  This file is deliberately ASCII-only: cmd.exe reads .cmd with
rem  the OEM codepage (GBK on this box), so non-ASCII text here would
rem  be mangled. All real logic lives in skill_audit_daily.py.
rem ============================================================
setlocal
set "PY=C:\Users\admin\AppData\Local\Programs\Python\Python312\python.exe"
set "DAILY=C:\Users\admin\.dsh\skills\dsh-skill-self-audit\scripts\skill_audit_daily.py"
set "PYTHONDONTWRITEBYTECODE=1"
"%PY%" "%DAILY%"
set "RC=%ERRORLEVEL%"
exit /b %RC%
