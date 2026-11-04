# Laburo · MusoSoup — Guiones

Guiones de **Indie Now · MusoSoup**: consolidador de lanzamientos del día.
Lee los ZIP de MusoSoup y los documentos sueltos de la carpeta del día, detecta artista / lanzamiento / tipo y genera un único Word ordenado (`LANZAMIENTOS_AAAA-MM-DD.docx`).

> Repo separado pensado para **reinstalar todo desde cero en un Windows recién formateado** y que funcione tal cual como está ahora.

---

## 1. En el PC nuevo (Windows recién formateado)

### 1.1. Instalar los 2 programas base

1. **Python 3.12.x (64 bits)** desde https://www.python.org/downloads/
   - ✅ Marca **“Add python.exe to PATH”**
   - ✅ Deja marcado **“tcl/tk and IDLE”** (lo trae por defecto — es el que da la ventana)
2. **Git para Windows** desde https://git-scm.com/download/win (opcional, solo para sincronizar con GitHub)

### 1.2. Descargar este repo

**Opción A — con Git:**
```cmd
git clone https://github.com/saulnownowindie/laburo-musosoup-guiones.git
cd laburo-musosoup-guiones
```

**Opción B — sin Git (ZIP):**
1. Entra en https://github.com/saulnownowindie/laburo-musosoup-guiones
2. Clic en **Code → Download ZIP**
3. Descomprime el archivo donde quieras (ej. `C:\Laburo_MusoSoup_Guiones`)

### 1.3. Ejecutar el instalador (solo la primera vez)

Doble clic en **`INSTALAR_DESDE_CERO.bat`**

- Crea el entorno virtual `.venv` (carpeta local, no se sube a GitHub)
- Instala todas las librerías de `requirements.txt`
- Verifica que la app carga
- Al terminar abre MusoSoup automáticamente

> La primera vez tarda 1-3 min (descarga de librerías). Las siguientes veces solo doble clic en `EJECUTAR_MUSOSOUP_DIARIO.bat`.

### 1.4. Uso diario

Doble clic en **`EJECUTAR_MUSOSOUP_DIARIO.bat`** → elige la carpeta del día → Analizar → Generar.

---

## 2. Instalación manual (alternativa al .bat)

Si prefieres instalar a mano en PowerShell:

```powershell
cd C:\Laburo_MusoSoup_Guiones
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -U pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\pythonw.exe musosoup_diario.py
```

> El `.venv` va ligado a `C:\Python312` de este PC: **no se puede copiar tal cual a otro PC**. En un Windows nuevo siempre se recrea con el instalador (por eso no se sube a Git).

---

## 3. Archivos del repo

| Archivo | Para qué sirve |
|---|---|
| `musosoup_diario.py` | Lógica: ZIP, extracción, detección, generación del DOCX |
| `musosoup_ui.py` | Interfaz (autocontenida — no depende de ningún otro `.py` más) |
| `EJECUTAR_MUSOSOUP_DIARIO.bat` | Arranque diario (abre rápido si ya están las dependencias) |
| `INSTALAR_DESDE_CERO.bat` | Instalación completa en Windows recién formateado |
| `requirements.txt` | Versiones exactas probadas (Python 3.12.10) |
| `musosoup_config.json` | Config de la app (carpeta, destino, opciones). Se crea solo si no existe |
| `.gitignore` | Ignora `.venv`, `__pycache__`, logs y Word generados |

## 4. Requisitos

- **Windows 10/11 64 bits**
- **Python 3.11–3.13** (probado con **3.12.10**) con Tkinter
- **Microsoft Word** (solo para abrir el `.docx` final)
- Conexión a internet solo en la primera instalación

## 5. Problemas frecuentes

| Error | Solución |
|---|---|
| “Python no está instalado” | Instala Python 3.12 marcando **Add to PATH** |
| No aparece la ventana | En la instalación de Python debe estar **tcl/tk and IDLE**. Si no, reinstala marcándolo. |
| `ModuleNotFoundError` | Borra `.venv` y `musosoup_deps.ok`, vuelve a ejecutar `INSTALAR_DESDE_CERO.bat` |
| Todo salió pero no abre Word | Revisa que Microsoft Word está instalado |
| Cambié de carpeta / PC | La config está en `musosoup_config.json`; la app la vuelve a crear si la borras |

## 6. Subir cambios a GitHub

```cmd
cd C:\Laburo_MusoSoup_Guiones
git add .
git commit -m "describe el cambio"
git push
```

> Nunca se suben `.venv/`, `__pycache__/`, `musosoup_deps.ok`, `musosoup.log` ni los `.docx` generados (ya están en `.gitignore`).

---

*Generado para recuperación total: clonar → `INSTALAR_DESDE_CERO.bat` → `EJECUTAR_MUSOSOUP_DIARIO.bat`.*
