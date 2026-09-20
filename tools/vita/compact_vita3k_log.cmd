@echo off
setlocal
if "%~1"=="" (
  echo Arrastra el log de Vita3K sobre este archivo.
  pause
  exit /b 1
)
where py >nul 2>nul
if errorlevel 1 (
  python "%~dp0compact_vita3k_log.py" "%~1"
) else (
  py -3 "%~dp0compact_vita3k_log.py" "%~1"
)
set "result=%errorlevel%"
pause
exit /b %result%
