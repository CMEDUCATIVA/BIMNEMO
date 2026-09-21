@echo off
REM ===========================================================================
REM  BIMNEMO — aplicacion de escritorio
REM ---------------------------------------------------------------------------
REM  Arranca el motor y abre la ventana de BIMNEMO. Al cerrar la ventana se
REM  cierra el motor.
REM
REM  Opciones (se pasan tal cual al lanzador):
REM     BIMNEMO.bat --consola      deja ver la salida del motor (diagnostico)
REM     BIMNEMO.bat --solo-motor   solo arranca el motor, sin ventana
REM     BIMNEMO.bat --port 9700    otro puerto
REM ===========================================================================

setlocal

set "RAIZ=%~dp0"
cd /d "%RAIZ%"

REM El banner de arranque de LightRAG no cabe en cp1252; sin esto el motor
REM muere con UnicodeEncodeError antes de escuchar.
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"

REM Tres formas de estar instalado, y hay que soportar las tres:
REM   * con el instalador        -> bimnemo-consola.exe, que es el interprete
REM                                 del paquete con la cara de BIMNEMO
REM   * paquetes anteriores      -> python.exe a secas
REM   * clonado para desarrollar -> entorno virtual en .venv\
set "PY=%RAIZ%python\bimnemo-consola.exe"
if not exist "%PY%" set "PY=%RAIZ%python\python.exe"
if not exist "%PY%" set "PY=%RAIZ%.venv\Scripts\python.exe"

if not exist "%PY%" (
    echo.
    echo  [ERROR] No se encuentra el interprete, ni en python\ ni en .venv\
    echo.
    echo  Si clonaste el repositorio, crea el entorno una sola vez con:
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

"%PY%" -m lightrag.api.bimnemo.desktop %*

if errorlevel 1 (
    echo.
    echo  BIMNEMO termino con error. Vuelve a lanzarlo con --consola para ver
    echo  la salida del motor.
    echo.
    pause
)

endlocal
