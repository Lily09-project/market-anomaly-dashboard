@echo off
setlocal

REM ============================================================
REM Stock Analysis Dashboard - stable Windows launcher
REM Put this file in the project root folder.
REM ============================================================

cd /d "%~dp0"
set "STREAMLIT_PORT=8765"

echo ============================================================
echo Stock Analysis Dashboard - Windows one-click launcher
echo ============================================================
echo Project path: %CD%
echo Streamlit fixed URL: http://localhost:%STREAMLIT_PORT%
echo ============================================================

REM Check required project files
if not exist "requirements.txt" (
    echo [ERROR] requirements.txt not found. Put this BAT file in the project root.
    pause
    exit /b 1
)

if not exist "run_all.py" (
    echo [ERROR] run_all.py not found. Put this BAT file in the project root.
    pause
    exit /b 1
)

if not exist "app.py" (
    echo [ERROR] app.py not found. Put this BAT file in the project root.
    pause
    exit /b 1
)

REM Find Python
set "PY_EXE="
set "PY_ARGS="
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
    set "CODEX_BUNDLED_PY=%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
    if exist "%CODEX_BUNDLED_PY%" (
        "%CODEX_BUNDLED_PY%" --version >nul 2>nul
        if not errorlevel 1 set "PY_EXE=%CODEX_BUNDLED_PY%"
    )
)

if not defined PY_EXE (
    echo [ERROR] Python was not found. Install Python 3.10+ and enable Add Python to PATH.
    pause
    exit /b 1
)

echo Using Python: %PY_EXE% %PY_ARGS%
echo [1/7] Creating or checking virtual environment...
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
        pause
        exit /b 1
    )
)

set "VENV_PY=%CD%\.venv\Scripts\python.exe"

if not exist "%VENV_PY%" (
    echo [ERROR] Virtual environment Python not found: %VENV_PY%
    pause
    exit /b 1
)

echo [2/7] Checking Python version inside .venv...
"%VENV_PY%" --version
if errorlevel 1 (
    echo [ERROR] Failed to run Python inside .venv.
    pause
    exit /b 1
)

echo [3/7] Installing dependencies into .venv...
"%VENV_PY%" -m pip install --upgrade pip
if errorlevel 1 (
    echo [ERROR] Failed to upgrade pip.
    pause
    exit /b 1
)

"%VENV_PY%" -m pip install -r requirements.txt
if errorlevel 1 (
    echo [ERROR] Failed to install requirements.txt.
    pause
    exit /b 1
)

echo [4/7] Running sample pipeline...
"%VENV_PY%" run_all.py --mode sample
if errorlevel 1 (
    echo [ERROR] run_all.py --mode sample failed.
    pause
    exit /b 1
)

echo [5/7] Running smoke test...
"%VENV_PY%" src\smoke_test.py
if errorlevel 1 (
    echo [ERROR] src\smoke_test.py failed.
    pause
    exit /b 1
)

echo [6/7] Running pytest...
set "PYTHONDONTWRITEBYTECODE=1"
set "PYTEST_ADDOPTS=--basetemp=.pytest_tmp -p no:cacheprovider"
"%VENV_PY%" -m pytest -q -p no:cacheprovider
if errorlevel 1 (
    echo [ERROR] pytest failed.
    pause
    exit /b 1
)

echo [7/7] Starting Streamlit Dashboard...
echo Project path: %CD%
echo Fixed dashboard URL: http://localhost:%STREAMLIT_PORT%
echo If the browser does not open automatically, use the fixed URL above.
"%VENV_PY%" -m streamlit run app.py --server.port %STREAMLIT_PORT%

pause
endlocal
