@echo off
rem BI ML Studio - instalacao no Windows (equivalente a "make install" + "make build").
rem Uso: duplo clique, ou "install.bat" na linha de comandos (".\install.bat" no PowerShell).
setlocal EnableExtensions
cd /d "%~dp0"
set "PYTHONUTF8=1"
set "PIP_DISABLE_PIP_VERSION_CHECK=1"

echo.
echo  BI ML Studio - instalacao no Windows
echo  ------------------------------------
echo.

rem --- Python 3.10 ou superior (recomendado 3.12) ---------------------------
set "PY="
py -3 --version >nul 2>&1
if not errorlevel 1 set "PY=py -3"
if not defined PY (
    python --version >nul 2>&1
    if not errorlevel 1 set "PY=python"
)
if not defined PY goto :no_python
%PY% -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)"
if errorlevel 1 goto :old_python
for /f "delims=" %%v in ('%PY% --version') do echo  Encontrado: %%v

rem --- Node.js, para compilar a interface ------------------------------------
where npm >nul 2>&1
if errorlevel 1 goto :no_node
for /f "delims=" %%v in ('node --version') do echo  Encontrado: Node.js %%v
echo.

rem --- 1. Ambiente virtual ----------------------------------------------------
if not exist ".venv\Scripts\python.exe" (
    echo [1/3] A criar o ambiente virtual .venv ...
    %PY% -m venv .venv
    if errorlevel 1 goto :fail
) else (
    echo [1/3] Ambiente virtual .venv ja existe.
)
set "VPY=%~dp0.venv\Scripts\python.exe"

rem --- 2. Dependencias Python -------------------------------------------------
echo [2/3] A instalar as dependencias Python. Na primeira vez demora alguns minutos ...
"%VPY%" -m pip install --upgrade pip >nul
"%VPY%" -m pip install -r backend\requirements.txt
if errorlevel 1 goto :pip_fail

rem --- 3. Interface (frontend) ------------------------------------------------
echo.
echo [3/3] A instalar e compilar a interface ...
pushd frontend
call npm ci --no-audit --no-fund
if errorlevel 1 call npm install --no-audit --no-fund
if errorlevel 1 (popd & goto :fail)
call npm run build
if errorlevel 1 (popd & goto :fail)
popd

echo.
echo  Instalacao concluida. Para arrancar a aplicacao: run.bat
echo.
call :maybe_pause
exit /b 0

:no_python
echo [ERRO] Nao encontrei o Python 3.10 ou superior.
echo        Instale o Python 3.12 em https://www.python.org/downloads/windows/
echo        e marque a opcao "Add python.exe to PATH". Depois abra uma nova janela e repita.
goto :fail

:old_python
echo [ERRO] A versao do Python e anterior a 3.10. Instale o Python 3.12:
echo        https://www.python.org/downloads/windows/
goto :fail

:no_node
echo [ERRO] Nao encontrei o Node.js, necessario para compilar a interface.
echo        Instale a versao LTS em https://nodejs.org/ e abra uma nova janela antes de repetir.
goto :fail

:pip_fail
echo.
echo [ERRO] A instalacao das dependencias Python falhou.
echo        Se a mensagem falar em "Microsoft Visual C++" ou "building wheel", a sua versao
echo        do Python ainda nao tem pacotes prontos: instale o Python 3.12, apague a pasta
echo        .venv e corra de novo install.bat
goto :fail

:fail
echo.
echo  Instalacao interrompida.
call :maybe_pause
exit /b 1

:maybe_pause
rem Pausa apenas quando o script foi aberto com duplo clique (a janela fecharia logo).
echo %cmdcmdline% | "%SystemRoot%\System32\find.exe" /i "/c" >nul
if not errorlevel 1 pause
exit /b 0
