@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title MusoSoup - Instalador desde cero

echo ============================================================
echo   MUSOSOUP - Instalacion desde cero (Windows recien formateado)
echo ============================================================
echo.

set "VENV=.venv"
set "PYLAUNCHER=0"
set "PYTHON_EXE="
set "PYTHONW_EXE="

echo [1/6] Buscando Python 3.11, 3.12 o 3.13...
echo.

REM 1) Python launcher de python.org (py -3.12, etc.)
where py >nul 2>&1
if %errorlevel%==0 (
  for %%V in (3.13 3.12 3.11) do (
    if not defined PYTHON_EXE (
      py -%%V -c "import sys; sys.exit(0 if sys.version_info>=(3,11) else 1)" >nul 2>&1
      if !errorlevel!==0 (
        set "PYLAUNCHER=1"
        set "PYTHON_EXE=py -%%V"
        set "PYTHONW_EXE=pyw -%%V"
      )
    )
  )
)

REM 2) python en PATH
if not defined PYTHON_EXE (
  where python >nul 2>&1
  if !errorlevel!==0 (
    python -c "import sys; sys.exit(0 if sys.version_info>=(3,11) else 1)" >nul 2>&1
    if !errorlevel!==0 (
      set "PYTHON_EXE=python"
      set "PYTHONW_EXE=pythonw"
    )
  )
)

if not defined PYTHON_EXE (
  echo.
  echo ERROR: No se encontro Python 3.11+ con Tkinter.
  echo.
  echo Instala Python desde https://www.python.org/downloads/
  echo   IMPORTANTE al instalar:
  echo   - Marca "Add python.exe to PATH"
  echo   - Marca "tcl/tk and IDLE"  ^(viene marcado por defecto^)
  echo   - Version recomendada: Python 3.12.x de 64 bits
  echo.
  echo Cuando termines, vuelve a ejecutar este INSTALAR_DESDE_CERO.bat
  echo.
  pause
  exit /b 1
)

echo  Python encontrado: %PYTHON_EXE%
%PYTHON_EXE% --version
echo.

echo [2/6] Verificando Tkinter...
%PYTHON_EXE% -c "import tkinter; print('  Tkinter OK -', tkinter.TkVersion)"
if errorlevel 1 (
  echo.
  echo ERROR: Tkinter no esta disponible.
  echo En el instalador de Python, vuelve a instalar y marca "tcl/tk and IDLE".
  pause
  exit /b 1
)
echo.

echo [3/6] Creando entorno virtual en .venv\ ...
if exist "%VENV%\Scripts\python.exe" (
  echo  Ya existe .venv. Lo reutilizamos.
) else (
  %PYTHON_EXE% -m venv "%VENV%"
  if errorlevel 1 (
    echo ERROR: No se pudo crear el entorno virtual.
    pause
    exit /b 1
  )
)
echo  Entorno listo.
echo.

echo [4/6] Actualizando pip y setuptools...
" %VENV%\Scripts\python.exe" -m pip install -U pip setuptools wheel
if errorlevel 1 (
  echo ADVERTENCIA: no se pudo actualizar pip. Seguimos igualmente.
)
echo.

echo [5/6] Instalando dependencias desde requirements.txt...
echo  ^(Esto puede tardar 1-3 minutos la primera vez^)
"%VENV%\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
  echo.
  echo ERROR: Fallo la instalacion de dependencias.
  echo Revisa tu conexion a internet e intentalo de nuevo.
  pause
  exit /b 1
)
echo  Dependencias instaladas.
echo.

echo [6/6] Verificando que todo carga...
"%VENV%\Scripts\python.exe" -c "import tkinter, musosoup_ui; import docx, pypdf, pymupdf, striprtf, openpyxl, pptx, PIL; print('  Carga principal OK')"
if errorlevel 1 (
  echo ERROR: No se pudo cargar la aplicacion tras instalar.
  pause
  exit /b 1
)
echo.

echo ok> "musosoup_deps.ok"
echo ============================================================
echo   LISTO. Abriendo MusoSoup...
echo ============================================================
echo.
start "" "%VENV%\Scripts\pythonw.exe" "musosoup_diario.py"
exit /b 0
