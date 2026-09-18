@echo off
REM ===================================================================
REM  StillFriends - lanzador para doble clic
REM  Este archivo se deja en ASCII puro a proposito: cmd lo lee con la
REM  codepage del sistema, y cualquier tilde aqui saldria rota.
REM ===================================================================
setlocal

REM UTF-8 en la consola, para los marcos y los emoji de la salida.
chcp 65001 >nul 2>&1
set "PYTHONIOENCODING=utf-8"
set "PYTHONUTF8=1"

REM Trabajar siempre desde la carpeta del script, venga de donde venga.
cd /d "%~dp0"
title StillFriends

REM --- Buscar Python -------------------------------------------------
set "PY="
where py >nul 2>&1 && set "PY=py -3"
if not defined PY (where python >nul 2>&1 && set "PY=python")
if not defined PY (
    echo.
    echo  No se encontro Python en el PATH.
    echo  Instalalo desde https://www.python.org/downloads/
    echo  y marca "Add python.exe to PATH" durante la instalacion.
    echo.
    pause
    exit /b 1
)

REM --- Comprobar dependencias ----------------------------------------
%PY% -c "import playwright, rich" >nul 2>&1
if errorlevel 1 (
    echo.
    echo  Faltan dependencias. Instalando, esto tarda un poco...
    echo.
    REM No hace falta "playwright install": usamos el Edge ya instalado.
    %PY% -m pip install -r requirements.txt || goto :fallo_deps
    echo.
    echo  Listo.
    echo.
)

REM --- Si arrastraron argumentos, pasarlos tal cual -------------------
if not "%~1"=="" (
    %PY% stillfriends.py %*
    echo.
    pause
    exit /b %errorlevel%
)

REM Cortafuegos por si no hay teclado (lanzado desde un script u otra
REM herramienta): sin el, un set /p que lee EOF daria vueltas sin fin.
set /a INTENTOS=0

REM --- Menu -----------------------------------------------------------
:menu
cls
echo.
echo   ===============================================================
echo     S T I L L F R I E N D S
echo     quien se queda, quien se va, quien no te sigue
echo   ===============================================================
echo.
echo     1.  Revisar y abrir el informe
echo     I.  Abrir el informe sin revisar
echo     2.  Revisar solo Facebook
echo     3.  Revisar solo Instagram
echo     4.  Revisar solo X / Twitter
echo.
echo     5.  Quien no me sigue de vuelta
echo     6.  Historial de revisiones
echo     7.  Historial con nombres
echo     8.  Ver las listas guardadas
echo.
echo     9.  Revisar sin guardar  (prueba)
echo     L.  Iniciar sesion en las redes  (la primera vez)
echo     0.  Salir
echo.
set "opcion="
set /p "opcion=  Elige una opcion: "

if /i "%opcion%"=="l" ( set "ARGS=login" & goto :correr )
if /i "%opcion%"=="i" ( set "ARGS=report" & goto :correr )
if "%opcion%"=="1" ( set "ARGS=check --html" & goto :correr )
if "%opcion%"=="2" ( set "ARGS=check -p fb" & goto :correr )
if "%opcion%"=="3" ( set "ARGS=check -p ig" & goto :correr )
if "%opcion%"=="4" ( set "ARGS=check -p x" & goto :correr )
if "%opcion%"=="5" ( set "ARGS=unrequited" & goto :correr )
if "%opcion%"=="6" ( set "ARGS=history" & goto :correr )
if "%opcion%"=="7" ( set "ARGS=history -d" & goto :correr )
if "%opcion%"=="8" ( set "ARGS=list" & goto :correr )
if "%opcion%"=="9" ( set "ARGS=check --dry-run" & goto :correr )
if "%opcion%"=="0" exit /b 0

set /a INTENTOS+=1
if %INTENTOS% GEQ 15 (
    echo.
    echo  Demasiadas opciones no validas. Saliendo.
    exit /b 1
)
goto :menu

:correr
cls
echo.
%PY% stillfriends.py %ARGS%
echo.
echo   ---------------------------------------------------------------
set "seguir="
set /p "seguir=  Enter para volver al menu, o escribe S para salir: "
if /i "%seguir%"=="s" exit /b 0
goto :menu

:fallo_deps
echo.
echo  No se pudieron instalar las dependencias.
echo  Prueba a mano:  pip install -r requirements.txt
echo.
pause
exit /b 1
