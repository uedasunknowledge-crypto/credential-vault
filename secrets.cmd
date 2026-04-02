@echo off
setlocal

set "ROOT_DIR=%~dp0"
set "PYTHON_EXE=%ROOT_DIR%.venv\Scripts\python.exe"
set "SRC_DIR=%ROOT_DIR%src"

if not exist "%PYTHON_EXE%" goto missing

if defined PYTHONPATH (
  set "PYTHONPATH=%SRC_DIR%;%PYTHONPATH%"
) else (
  set "PYTHONPATH=%SRC_DIR%"
)

"%PYTHON_EXE%" -m credential_vault.cli %*
exit /b %ERRORLEVEL%

:missing
echo .venv not found. 1>&2
exit /b 1
