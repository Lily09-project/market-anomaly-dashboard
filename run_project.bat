@echo off
chcp 65001 >nul
setlocal
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"

REM ============================================================
REM Stock Analysis Dashboard - stable Windows launcher
REM Put this file in the project root folder.
REM ============================================================

cd /d "%~dp0"
set "STREAMLIT_PORT=8765"

if /I "%~1"=="--help" goto :usage
if "%~1"=="" goto :arguments_ready
if /I "%~1"=="--validate" goto :arguments_ready
echo [ERROR] Unsupported argument: %~1
goto :usage_error

:arguments_ready

echo ============================================================
echo Stock Analysis Dashboard - Windows one-click launcher
echo ============================================================
echo Project path: %CD%
echo Streamlit fixed URL: http://localhost:%STREAMLIT_PORT%
echo ============================================================

REM Check required project files
if not exist "requirements.txt" (
    echo [ERROR] requirements.txt not found. Put this BAT file in the project root.
    if /I not "%~1"=="--validate" pause
    exit /b 1
)

if not exist "requirements-dev.txt" (
    echo [ERROR] requirements-dev.txt not found. Put this BAT file in the project root.
    if /I not "%~1"=="--validate" pause
    exit /b 1
)
if not exist "run_all.py" (
    echo [ERROR] run_all.py not found. Put this BAT file in the project root.
    if /I not "%~1"=="--validate" pause
    exit /b 1
)

if not exist "app.py" (
    echo [ERROR] app.py not found. Put this BAT file in the project root.
    if /I not "%~1"=="--validate" pause
    exit /b 1
)

REM Fail clearly if the fixed dashboard port is already occupied.
if /I "%~1"=="--validate" goto :port_ready
set "PORT_PID="
for /f "tokens=5" %%P in ('netstat -ano ^| findstr /R /C:":%STREAMLIT_PORT% .*LISTENING"') do set "PORT_PID=%%P"
if defined PORT_PID (
    echo [ERROR] Port %STREAMLIT_PORT% is already in use.
    echo [ERROR] Existing process ID: %PORT_PID%
    echo Close that process or stop the other dashboard before retrying.
    if /I not "%~1"=="--validate" pause
    exit /b 1
)

:port_ready

REM Find Python
set "PY_EXE="
set "PY_ARGS="
if exist "%CD%\.venv\Scripts\python.exe" (
    "%CD%\.venv\Scripts\python.exe" --version >nul 2>nul
    if not errorlevel 1 set "PY_EXE=%CD%\.venv\Scripts\python.exe"
)

if defined PY_EXE goto :python_ready

where python >nul 2>nul
if not errorlevel 1 (
    python --version >nul 2>nul
    if not errorlevel 1 set "PY_EXE=python"
)

if not defined PY_EXE (
    where py >nul 2>nul
    if not errorlevel 1 (
        py -3 --version >nul 2>nul
        if not errorlevel 1 (
            set "PY_EXE=py"
            set "PY_ARGS=-3"
        )
    )
)

if not defined PY_EXE (
    echo [ERROR] Python was not found. Install Python 3.10+ and enable Add Python to PATH.
    if /I not "%~1"=="--validate" pause
    exit /b 1
)

:python_ready
echo Using Python: %PY_EXE% %PY_ARGS%
echo [1/9] Creating or checking virtual environment...
set "VENV_PY=%CD%\.venv\Scripts\python.exe"

if exist "%VENV_PY%" (
    "%VENV_PY%" --version >nul 2>nul
    if errorlevel 1 (
        echo [WARN] Existing .venv is not usable. Recreating virtual environment...
        rmdir /s /q ".venv"
    )
)

if not exist "%VENV_PY%" (
    "%PY_EXE%" %PY_ARGS% -m venv .venv
    if errorlevel 1 (
        echo [ERROR] Failed to create virtual environment.
        if /I not "%~1"=="--validate" pause
        exit /b 1
    )
)

set "VENV_PY=%CD%\.venv\Scripts\python.exe"

if not exist "%VENV_PY%" (
    echo [ERROR] Virtual environment Python not found: %VENV_PY%
    if /I not "%~1"=="--validate" pause
    exit /b 1
)

echo [2/9] Checking Python version inside .venv...
"%VENV_PY%" --version
if errorlevel 1 (
    echo [ERROR] Failed to run Python inside .venv.
    if /I not "%~1"=="--validate" pause
    exit /b 1
)

echo [3/9] Installing dependencies into .venv...
"%VENV_PY%" -m pip install --upgrade "pip>=26.2"
if errorlevel 1 (
    echo [ERROR] Failed to upgrade pip.
    if /I not "%~1"=="--validate" pause
    exit /b 1
)

if exist "requirements-dev.lock" (
    "%VENV_PY%" -m pip install -r requirements-dev.lock
) else (
    "%VENV_PY%" -m pip install -r requirements-dev.txt
)
if errorlevel 1 (
    echo [ERROR] Failed to install requirements-dev.txt.
    if /I not "%~1"=="--validate" pause
    exit /b 1
)

echo [4/9] Running sample pipeline...
"%VENV_PY%" run_all.py --mode sample
if errorlevel 1 (
    echo [ERROR] run_all.py --mode sample failed.
    if /I not "%~1"=="--validate" pause
    exit /b 1
)

echo [5/9] Running smoke test...
"%VENV_PY%" src\smoke_test.py
if errorlevel 1 (
    echo [ERROR] src\smoke_test.py failed.
    if /I not "%~1"=="--validate" pause
    exit /b 1
)

echo [6/9] Running zero-warning pytest...
set "PYTHONDONTWRITEBYTECODE=1"
set "PYTEST_BASETEMP=%TEMP%\market-anomaly-dashboard_pytest_%RANDOM%_%RANDOM%"
"%VENV_PY%" -W error -m pytest -q -p no:cacheprovider --basetemp "%PYTEST_BASETEMP%"
if errorlevel 1 (
    echo [ERROR] pytest failed.
    if /I not "%~1"=="--validate" pause
    exit /b 1
)
if exist "%PYTEST_BASETEMP%" rmdir /s /q "%PYTEST_BASETEMP%" >nul 2>nul

echo [7/9] Compiling Python sources...
"%VENV_PY%" -m compileall -q app.py src scripts tests
if errorlevel 1 (
    echo [ERROR] Python compilation check failed.
    exit /b 1
)

echo [8/9] Checking installed dependency consistency...
"%VENV_PY%" -m pip check
if errorlevel 1 (
    echo [ERROR] Installed dependencies are inconsistent.
    exit /b 1
)

echo [9/9] Verifying public release boundaries...
"%VENV_PY%" scripts\verify_release.py
if errorlevel 1 (
    echo [ERROR] Public release verification failed.
    exit /b 1
)

if /I "%~1"=="--validate" (
    echo [SECURITY] Running Bandit and strict dependency audit...
    "%VENV_PY%" -m bandit -q -r app.py src scripts
    if errorlevel 1 exit /b 1
    "%VENV_PY%" -m pip_audit --strict --progress-spinner off
    if errorlevel 1 exit /b 1
    echo Validation completed successfully. Streamlit launch skipped.
    exit /b 0
)

echo Starting Streamlit Dashboard...
echo Project path: %CD%
echo Fixed dashboard URL: http://localhost:%STREAMLIT_PORT%
echo If the browser does not open automatically, use the fixed URL above.
"%VENV_PY%" -m streamlit run app.py --server.port %STREAMLIT_PORT%

pause
endlocal
exit /b 0

:usage
echo Usage: run_project.bat [--validate ^| --help]
echo   no argument   Rebuild sample artifacts, verify them, and start Streamlit.
echo   --validate    Run pipeline, tests, compile, release, and security checks only.
endlocal
exit /b 0

:usage_error
echo Use run_project.bat --help for supported options.
endlocal
exit /b 2
