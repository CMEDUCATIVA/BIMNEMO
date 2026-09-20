@echo off
REM ===========================================================================
REM  BIMNEMO — construir el instalador de Windows
REM ---------------------------------------------------------------------------
REM  Uso:
REM     scripts\release\construir_instalador.bat            (usa el VERSION)
REM     scripts\release\construir_instalador.bat v1.2.0
REM
REM  Deja el instalador en installer\salida\BIMNEMO-<version>-instalador.exe
REM ===========================================================================

setlocal
set "RAIZ=%~dp0..\.."
cd /d "%RAIZ%"

set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"

if "%~1"=="" (
    set /p VERSION=<VERSION
) else (
    set "VERSION=%~1"
)

echo.
echo === 1/2  Preparando los ficheros ===
".venv\Scripts\python.exe" scripts\release\empaquetar.py %VERSION%
if errorlevel 1 goto :error

echo.
echo === 2/2  Compilando el instalador ===
set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" (
    echo.
    echo No se encontro Inno Setup 6.
    echo Descargalo de https://jrsoftware.org/isdl.php e instalalo.
    goto :error
)

REM Inno Setup quiere la version sin la "v" de la etiqueta.
set "NUMERO=%VERSION%"
if "%NUMERO:~0,1%"=="v" set "NUMERO=%NUMERO:~1%"

"%ISCC%" /DVersion=%NUMERO% "installer\BIMNEMO.iss"
if errorlevel 1 goto :error

echo.
echo Listo: installer\salida\BIMNEMO-%NUMERO%-instalador.exe
endlocal
exit /b 0

:error
echo.
echo La construccion fallo.
endlocal
exit /b 1
