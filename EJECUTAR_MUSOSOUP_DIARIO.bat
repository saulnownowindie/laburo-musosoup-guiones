@echo off
setlocal EnableExtensions
cd /d "%~dp0"

rem ─────────────────────────────────────────────────────────────
rem  Arranque diario: si ya está instalado, abre rápido.
rem  Si algo falla, delega en INSTALAR_DESDE_CERO.bat.
rem ─────────────────────────────────────────────────────────────

if not exist ".venv\Scripts\pythonw.exe" goto :instalar
if not exist "musosoup_deps.ok" goto :instalar

rem Verificación ligera (sin mostrar ventana)
".venv\Scripts\python.exe" -c "import musosoup_ui, docx, pypdf, pymupdf" >nul 2>&1
if errorlevel 1 goto :instalar

start "" ".venv\Scripts\pythonw.exe" "musosoup_diario.py"
exit /b 0

:instalar
echo No se encontró la instalación local. Ejecutando la instalación desde cero...
call "%~dp0INSTALAR_DESDE_CERO.bat"
exit /b %errorlevel%
