@echo off
cd /d "%~dp0"

REM Load environment variables from .env if present
if exist ".env" (
    for /f "usebackq eol=# tokens=1,* delims==" %%A in (".env") do (
        if not "%%A"=="" set "%%A=%%B"
    )
)

REM Priority 1: Use Python inside suite .venv
if exist ".venv\Scripts\python.exe" (
    set "PYTHON_EXE=.venv\Scripts\python.exe"
) else if exist "..\ai-subtitle-studio\.venv\Scripts\python.exe" (
    echo [INFO] Suite .venv not found. Using .venv from ai-subtitle-studio...
    set "PYTHON_EXE=..\ai-subtitle-studio\.venv\Scripts\python.exe"
) else (
    set "PYTHON_EXE=python"
)

REM Validate Python environment
"%PYTHON_EXE%" -c "import PySide6" >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo.
    echo =======================================================================
    echo  [ENVIRONMENT ERROR]
    echo  Could not find a valid Python environment with PySide6.
    echo  Target Python: "%PYTHON_EXE%"
    echo.
    echo  Resolution:
    echo  1. Ensure .venv exists at: %~dp0.venv
    echo  2. Or run: pip install -r requirements.txt
    echo =======================================================================
    echo.
    pause
    exit /b 1
)

echo Starting AI Subtitle Suite...
"%PYTHON_EXE%" main.py %*

if %ERRORLEVEL% neq 0 (
    echo.
    echo [ERROR] Application exited with error code %ERRORLEVEL%.
    pause
)
