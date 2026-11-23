@echo off
rem BI ML Studio - arranque no Windows (equivalente a "make run").
rem Uso: run.bat            -> http://localhost:8000
rem      run.bat 8001       -> outra porta, se a 8000 estiver ocupada
setlocal EnableExtensions
cd /d "%~dp0"
set "PYTHONUTF8=1"
set "VPY=%~dp0.venv\Scripts\python.exe"

if not exist "%VPY%" (
    echo [ERRO] A aplicacao ainda nao esta instalada. Corra primeiro install.bat
    goto :fail
)

if not exist "frontend\dist\index.html" (
    echo A compilar a interface ...
    pushd frontend
    call npm run build
    if errorlevel 1 (popd & goto :fail)
    popd
)

if not defined MLSTUDIO_HOME set "MLSTUDIO_HOME=%~dp0workspace"
set "PORT=8000"
if not "%~1"=="" set "PORT=%~1"
set "MLSTUDIO_OPEN_BROWSER=http://localhost:%PORT%"

echo.
echo  BI ML Studio em http://localhost:%PORT%
echo  O browser abre sozinho quando a aplicacao estiver pronta.
echo  Para parar: Ctrl+C nesta janela.
echo.
cd backend
"%VPY%" -m uvicorn mlstudio.api.main:app --host 127.0.0.1 --port %PORT%
if errorlevel 1 goto :fail
exit /b 0

:fail
echo.
echo  A aplicacao parou com um erro, ver as mensagens acima.
echo  Se a porta estiver ocupada, experimente: run.bat 8001
echo %cmdcmdline% | "%SystemRoot%\System32\find.exe" /i "/c" >nul
if not errorlevel 1 pause
exit /b 1
