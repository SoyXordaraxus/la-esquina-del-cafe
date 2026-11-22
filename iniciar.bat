@echo off
rem =====================================================================
rem  La Esquina del Cafe - arranque en Windows (sin Docker)
rem
rem  Uso (doble clic = modo MySQL):
rem    iniciar.bat                MySQL local (DATABASE_URL del archivo .env)
rem    iniciar.bat reset          MySQL: borra la base, la vuelve a poblar y arranca
rem    iniciar.bat sqlite         Plan B: SQLite en backend\esquina.db (no necesita MySQL)
rem    iniciar.bat sqlite reset   SQLite: borra esquina.db, la vuelve a poblar y arranca
rem
rem  La configuracion se lee de .env (copia .env.ejemplo como .env).
rem  Ctrl+C apaga el servidor (y genera el respaldo al cerrar).
rem =====================================================================
setlocal
chcp 65001 >nul
title La Esquina del Café
cd /d "%~dp0"
set "RAIZ=%~dp0"
set "BACKEND=%~dp0backend"

rem ---------- Argumentos ----------
set "MOTOR=mysql"
set "RESET=no"
set "ARG_RESET="
:leer_args
if "%~1"=="" goto fin_args
if /i "%~1"=="sqlite" set "MOTOR=sqlite" & shift & goto leer_args
if /i "%~1"=="mysql"  set "MOTOR=mysql"  & shift & goto leer_args
if /i "%~1"=="reset"  set "RESET=si"     & shift & goto leer_args
echo Opción no reconocida: %~1
echo Uso: iniciar.bat [sqlite] [reset]
goto error
:fin_args

rem ---------- Python: venv\Scripts\python si existe, si no python / py ----------
set "PY="
if exist "%RAIZ%venv\Scripts\python.exe" set PY="%RAIZ%venv\Scripts\python.exe"
if defined PY goto python_listo
python --version >nul 2>&1
if not errorlevel 1 set "PY=python"
if defined PY goto python_listo
py -3 --version >nul 2>&1
if not errorlevel 1 set "PY=py -3"
if defined PY goto python_listo
echo.
echo [ERROR] No se encontró Python.
echo         Instala Python 3.12 o superior desde https://www.python.org/downloads/
echo         y marca la casilla "Add python.exe to PATH" durante la instalación.
goto error
:python_listo

rem ---------- Configuración: archivo .env (CLAVE=valor, # para comentarios) ----------
if exist "%RAIZ%.env" goto leer_env
if /i "%MOTOR%"=="sqlite" goto env_listo
echo.
echo [ERROR] No existe el archivo .env en la carpeta del proyecto.
echo         Copia .env.ejemplo como .env y ajusta DATABASE_URL con tu usuario y
echo         contraseña de MySQL. Si no tienes MySQL, usa:  iniciar.bat sqlite
goto error
:leer_env
for /f "usebackq eol=# tokens=1,* delims==" %%A in ("%RAIZ%.env") do set "%%A=%%B"
:env_listo

if /i "%MOTOR%"=="sqlite" set "DATABASE_URL=sqlite:///./esquina.db"
if not defined PUERTO set "PUERTO=8000"
if not defined HOST set "HOST=127.0.0.1"

cd /d "%BACKEND%"

rem ---------- Dependencias ----------
%PY% preparar.py deps %MOTOR%
if errorlevel 1 goto error

rem ---------- Reset (pide confirmación) ----------
if not "%RESET%"=="si" goto preparar_bd
echo.
echo  ATENCIÓN: "reset" borra TODOS los datos de la base (%MOTOR%) y carga los datos iniciales.
set "CONFIRMA="
set /p "CONFIRMA=  Escribe SI para continuar: "
if /i not "%CONFIRMA%"=="SI" goto cancelado
set "ARG_RESET=reset"

rem ---------- Base de datos: conexión, creación y datos iniciales ----------
:preparar_bd
%PY% preparar.py bd %ARG_RESET%
if errorlevel 1 goto error

rem ---------- Puerto libre ----------
%PY% preparar.py puerto %PUERTO% %HOST%
if errorlevel 1 goto error

set "URL=http://127.0.0.1:%PUERTO%/login.html"
echo.
echo ==============================================================
if /i "%MOTOR%"=="sqlite" (echo   Base de datos: SQLite ^(backend\esquina.db^)) else (echo   Base de datos: MySQL ^(DATABASE_URL de .env^))
echo   Abrir:   %URL%
echo   API:     http://127.0.0.1:%PUERTO%/docs
echo   Ctrl+C para apagar el servidor
echo ==============================================================
echo.

rem El navegador se abre cuando el servidor ya responde (en segundo plano)
start "" /b %PY% preparar.py navegador %URL%

%PY% -m uvicorn main:app --host %HOST% --port %PUERTO%
if errorlevel 1 goto error
goto fin

:cancelado
echo Reset cancelado. No se modificó la base de datos.
goto fin

:error
echo.
echo El sistema no pudo arrancar. Lee el mensaje de arriba.
pause
endlocal
exit /b 1

:fin
endlocal
exit /b 0
