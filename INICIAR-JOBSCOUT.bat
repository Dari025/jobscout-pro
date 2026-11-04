@echo off
setlocal
cd /d "%~dp0"
title JobScout Pro

set "VENV_DIR=%~dp0.venv"
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
set "STREAMLIT_BROWSER_GATHER_USAGE_STATS=false"

if not exist "%VENV_DIR%\Scripts\python.exe" (
    echo.
    echo JobScout Pro - preparando Python...
    where py >nul 2>nul
    if not errorlevel 1 (
        py -3 -m venv "%VENV_DIR%"
    ) else (
        python -m venv "%VENV_DIR%"
    )
    if errorlevel 1 goto :error
)

echo.
echo JobScout Pro - comprobando dependencias...
"%VENV_DIR%\Scripts\python.exe" -m pip install -r requirements.txt --disable-pip-version-check
if errorlevel 1 goto :error

set "PYTHONPATH=%~dp0src"
echo.
echo Iniciando JobScout en tu equipo (solo acceso local)...
echo Cuando aparezca la direccion, abre http://127.0.0.1:8502
echo No cierres esta ventana mientras uses JobScout.
echo.

"%VENV_DIR%\Scripts\python.exe" -m streamlit run app.py --server.address 127.0.0.1 --server.port 8502 --server.headless false --browser.gatherUsageStats false
if errorlevel 1 goto :error
goto :end

:error
echo.
echo No se pudo iniciar JobScout. Revisa el mensaje anterior.
echo Comprueba que Python 3.10 o superior este instalado y que tengas conexion a Internet para instalar las dependencias.
pause

:end
endlocal
