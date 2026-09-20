@echo off
REM ===========================================================================
REM  BIMNEMO — aplicacion de escritorio
REM ---------------------------------------------------------------------------
REM  Arranca el motor y abre BIMNEMO en su propia ventana de Chromium, sin
REM  barra de direcciones ni pestanas. Al cerrar la ventana se cierra el motor.
REM
REM  Opciones (se pasan tal cual al lanzador):
REM     BIMNEMO.bat --consola      deja ver la salida del motor (diagnostico)
REM     BIMNEMO.bat --navegador    solo arranca el motor, sin ventana propia
REM     BIMNEMO.bat --port 9700    otro puerto
REM ===========================================================================

setlocal

set "RAIZ=%~dp0"
cd /d "%RAIZ%"

REM El banner de arranque de LightRAG no cabe en cp1252; sin esto el motor
REM muere con UnicodeEncodeError antes de escuchar.
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"

if not exist "%RAIZ%.venv\Scripts\python.exe" (
    echo.
    echo  [ERROR] No se encuentra el entorno virtual en .venv
    echo.
    echo  Crealo una sola vez con:
    echo      python -m venv .venv
    echo      .venv\Scripts\python.exe -m pip install -e .[api]
    echo.
    pause
    exit /b 1
)

if not exist "%RAIZ%.env" (
    echo.
    echo  [AVISO] No hay fichero .env. El panel se vera, pero la ingesta y el
    echo          chat fallaran hasta configurar un proveedor de LLM.
    echo          Copia env.example a .env y editalo.
    echo.
)

"%RAIZ%.venv\Scripts\python.exe" -m lightrag.api.bimnemo.desktop %*

if errorlevel 1 (
    echo.
    echo  BIMNEMO termino con error. Vuelve a lanzarlo con --consola para ver
    echo  la salida del motor.
    echo.
    pause
)

endlocal
