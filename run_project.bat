@echo off
chcp 65001 >nul
setlocal
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"

REM ============================================================
REM Market Regime Lab - Windows one-click launcher
REM ============================================================

cd /d "%~dp0"

if /I "%~1"=="--help" goto :usage
if "%~1"=="" goto :arguments_ready
if /I "%~1"=="--validate" goto :arguments_ready
echo [ERROR] Unsupported argument: %~1
goto :usage_error

:arguments_ready

echo ============================================================
echo Market Regime Lab - Windows one-click launcher
echo ============================================================
echo Project path: %CD%

for %%F in (requirements.txt requirements-dev.txt run_all.py web\package.json) do (
    if not exist "%%F" (
        echo [ERROR] %%F not found. Put this BAT file in the project root.
        goto :fail
    )
)

REM The dependency locks are built and tested with Python 3.12.
set "PY_EXE="
set "PY_ARGS="
if exist "%CD%\.venv\Scripts\python.exe" (
    "%CD%\.venv\Scripts\python.exe" -c "import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 12) else 1)" >nul 2>nul
    if errorlevel 1 (
        echo [ERROR] Existing .venv must use Python 3.12. Preserve or move it before creating a new environment.
        goto :fail
    )
    set "PY_EXE=%CD%\.venv\Scripts\python.exe"
)
if defined PY_EXE goto :python_ready

py -3.12 --version >nul 2>nul
if not errorlevel 1 (
    set "PY_EXE=py"
    set "PY_ARGS=-3.12"
)
if defined PY_EXE goto :python_ready

python -c "import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 12) else 1)" >nul 2>nul
if not errorlevel 1 set "PY_EXE=python"

if not defined PY_EXE (
    echo [ERROR] Python 3.12 was not found. Install Python 3.12 and enable Add Python to PATH.
    goto :fail
)

:python_ready
echo Using Python: %PY_EXE% %PY_ARGS%
echo [1/8] Creating or checking the virtual environment...
set "VENV_PY=%CD%\.venv\Scripts\python.exe"
if not exist "%VENV_PY%" (
    "%PY_EXE%" %PY_ARGS% -m venv .venv
    if errorlevel 1 (
        echo [ERROR] Failed to create the virtual environment.
        goto :fail
    )
)
"%VENV_PY%" -m pip --version >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Existing .venv is broken. Preserve or move it before creating a new environment.
    goto :fail
)

echo [2/8] Installing locked Python dependencies (requirements-dev.txt lock)...
"%VENV_PY%" -m pip install --disable-pip-version-check --upgrade "pip>=26.2"
if errorlevel 1 goto :fail
"%VENV_PY%" -m pip install --disable-pip-version-check -r requirements-dev.lock.txt
if errorlevel 1 (
    echo [ERROR] Failed to install the development dependency lock.
    goto :fail
)
"%VENV_PY%" -m pip check
if errorlevel 1 goto :fail

echo [3/8] Generating data and exporting the analysis for the web app...
"%VENV_PY%" run_all.py --mode sample
if errorlevel 1 (
    echo [ERROR] run_all.py --mode sample failed.
    goto :fail
)

echo [4/8] Running zero-warning pytest...
set "PYTHONDONTWRITEBYTECODE=1"
set "PYTEST_BASETEMP=%TEMP%\market-regime-lab_pytest_%RANDOM%_%RANDOM%"
"%VENV_PY%" -W error -m pytest -q -p no:cacheprovider --basetemp "%PYTEST_BASETEMP%"
if errorlevel 1 (
    echo [ERROR] pytest failed.
    goto :fail
)
if exist "%PYTEST_BASETEMP%" rmdir /s /q "%PYTEST_BASETEMP%" >nul 2>nul

echo [5/8] Compiling sources and verifying public release boundaries...
"%VENV_PY%" -m compileall -q run_all.py src scripts tests
if errorlevel 1 goto :fail
"%VENV_PY%" scripts\verify_release.py
if errorlevel 1 goto :fail

if /I "%~1"=="--validate" (
    echo [SECURITY] Running Bandit, Ruff and a strict dependency audit...
    "%VENV_PY%" -m bandit -q -r run_all.py src scripts
    if errorlevel 1 goto :fail
    "%VENV_PY%" -m ruff check run_all.py src scripts tests
    if errorlevel 1 goto :fail
    "%VENV_PY%" -m pip_audit --strict --progress-spinner off
    if errorlevel 1 goto :fail
)

echo [6/8] Checking Node.js...
where node >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Node.js 22 or newer was not found. Install it from https://nodejs.org/ and run this file again.
    goto :fail
)

echo [7/8] Installing and checking the web app...
pushd web
call npm ci --no-audit --no-fund
if errorlevel 1 goto :web_fail
if /I "%~1"=="--validate" (
    call npm run typecheck
    if errorlevel 1 goto :web_fail
    call npm run lint
    if errorlevel 1 goto :web_fail
    call npm run coverage
    if errorlevel 1 goto :web_fail
)
call npm run build
if errorlevel 1 goto :web_fail
if /I "%~1"=="--validate" (
    call npm run size
    if errorlevel 1 goto :web_fail
    popd
    echo Validation completed successfully. Web server launch skipped.
    endlocal
    exit /b 0
)

echo [8/8] Starting Market Regime Lab at http://127.0.0.1:4173
echo Press Ctrl+C to stop the site. This window must stay open.
call npm run preview -- --host 127.0.0.1
popd
endlocal
exit /b 0

:web_fail
popd
echo [ERROR] The web app could not be installed, checked or built.
goto :fail

:fail
echo.
echo [ERROR] run_project.bat failed.
if /I not "%~1"=="--validate" pause
endlocal
exit /b 1

:usage
echo Usage: run_project.bat [--validate ^| --help]
echo   no argument   Rebuild the sample analysis, run the tests, build the web app and open it locally.
echo   --validate    Run every Python, security and web quality gate without starting the site.
endlocal
exit /b 0

:usage_error
echo Use run_project.bat --help for supported options.
endlocal
exit /b 2
