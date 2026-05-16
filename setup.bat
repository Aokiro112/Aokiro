@echo off
setlocal EnableDelayedExpansion

:: ================================================
:: Architect-JS Setup Script for Windows
:: ================================================

echo.
echo  ^[Architect-JS^] Production Setup
echo  =====================================
echo.

:: Check Node.js
where node >nul 2>&1
if !errorlevel! neq 0 (
    echo  [ERROR] Node.js is not installed. Please install Node.js v18+ from https://nodejs.org
    exit /b 1
)
for /f "tokens=*" %%v in ('node --version') do set NODE_VERSION=%%v
echo  [OK] Node.js %NODE_VERSION% found

:: Check Python
where python >nul 2>&1
if !errorlevel! neq 0 (
    echo  [ERROR] Python is not installed. Please install Python 3.10+ from https://python.org
    exit /b 1
)
for /f "tokens=*" %%v in ('python --version') do set PY_VERSION=%%v
echo  [OK] %PY_VERSION% found

echo.
echo  Step 1: Creating Python virtual environment...
if not exist ".venv" (
    python -m venv .venv
    echo  [OK] Virtual environment created
) else (
    echo  [SKIP] Virtual environment already exists
)

echo.
echo  Step 2: Installing Python dependencies...
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip --quiet
pip install -r requirements.txt --quiet
if !errorlevel! neq 0 (
    echo  [ERROR] Python dependency installation failed.
    exit /b 1
)
echo  [OK] Python dependencies installed

echo.
echo  Step 3: Installing Node.js dependencies (src/analyzer)...
cd src\analyzer
call npm install --silent
if !errorlevel! neq 0 (
    echo  [ERROR] analyzer npm install failed.
    exit /b 1
)
cd ..\..
echo  [OK] src/analyzer dependencies installed

echo.
echo  Step 4: Installing Node.js dependencies (packages/ast-pipeline)...
cd packages\ast-pipeline
call npm install --silent
if !errorlevel! neq 0 (
    echo  [ERROR] ast-pipeline npm install failed.
    exit /b 1
)
cd ..\..
echo  [OK] packages/ast-pipeline dependencies installed

echo.
echo  Step 5: Building TypeScript package...
cd packages\ast-pipeline
call npm run build
if !errorlevel! neq 0 (
    echo  [WARN] TypeScript build had errors. Check output above.
) else (
    echo  [OK] TypeScript package built
)
cd ..\..

echo.
echo  Step 6: Creating required directories...
if not exist "data\test_ast" mkdir "data\test_ast"
if not exist "data\test_files" mkdir "data\test_files"
if not exist "data\rag_db" mkdir "data\rag_db"
if not exist "datasets\v1_synthetic" mkdir "datasets\v1_synthetic"
if not exist "datasets\v2_mined" mkdir "datasets\v2_mined"
if not exist "datasets\v3_hybrid" mkdir "datasets\v3_hybrid"
if not exist "logs\failures" mkdir "logs\failures"
if not exist "models" mkdir "models"
echo  [OK] Directory structure verified

echo.
echo  Step 7: Setting up environment configuration...
if not exist ".env" (
    copy ".env.example" ".env" >nul
    echo  [OK] .env created from template — please review and edit your settings
) else (
    echo  [SKIP] .env already exists
)

echo.
echo  ================================================
echo   Setup Complete!
echo  ================================================
echo.
echo  To start the CLI:
echo    .venv\Scripts\activate.bat
echo    python core_engine\main.py
echo.
echo  Quick commands:
echo    python core_engine\main.py --help
echo    python core_engine\main.py index --path data\
echo    python core_engine\main.py query "useEffect cleanup"
echo    node src\analyzer\ast_compressor.js path\to\Component.tsx
echo    node src\analyzer\build_dataset.js
echo.
echo  Model Inference (requires llama.cpp):
echo    See README.md for llama-server setup instructions.
echo.

endlocal
