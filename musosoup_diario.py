#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Indie Now · MusoSoup — consolidador de lanzamientos del día
===========================================================
Lee los ZIP de MusoSoup y todos los documentos sueltos de la carpeta del día,
detecta artista / lanzamiento / tipo, verifica los datos contra las fuentes y
genera un único Word ordenado.

Este archivo es la LÓGICA (ZIP, extracción, detección, DOCX). La interfaz con
estética IndieDL (con su kit visual incluido) vive en `musosoup_ui.py`.
"""

from __future__ import annotations

import hashlib
import html
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import unicodedata
import zipfile
from datetime import date
from pathlib import Path

import tkinter as tk
from tkinter import messagebox

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor
from pypdf import PdfReader

try:
    import pymupdf
except ImportError:
    pymupdf = None
try:
    from striprtf.striprtf import rtf_to_text
except ImportError:
    rtf_to_text = None
try:
    from openpyxl import load_workbook
except ImportError:
    load_workbook = None

from musosoup_ui import MusoSoupApp, init_fonts

try:
    import ctypes
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    pass


AQUI = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(AQUI, "musosoup_config.json")
LOG_FILE = os.path.join(AQUI, "musosoup.log")

TEXT_EXTENSIONS = {'.pdf', '.docx', '.doc', '.rtf', '.txt', '.md', '.html', '.htm',
                   '.pages', '.odt', '.pptx', '.xlsx', '.csv'}
IGNORE_DIRS = {'info completa', '__pycache__', '.git'}
PRIORITY_WORDS = ('press', 'release', 'press-release', 'press_release', 'epk',
                  'media', 'bio', 'biography', 'artist', 'info')
GENERADO_RE = re.compile(r'^(LANZAMIENTOS_|MUSOSOUP_.*_LANZAMIENTOS).*\.docx$', re.I)

MESES = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio',
         'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre']

CONFIG_DEFECTO = {
    "carpeta": "",
    "destino": "",
    "indice": True,
    "texto_completo": True,
    "sin_asociar": True,
    "abrir": True,
    "orden": "zip",
}


# ─────────────────────────────────────────────────────────────
# LOG / CANCELACIÓN / CONFIG
# ─────────────────────────────────────────────────────────────
class Cancelado(Exception):
    """El usuario pidió detener el proceso."""


_cancelar_evt = threading.Event()


def _check():
    if _cancelar_evt.is_set():
        raise Cancelado("Proceso cancelado.")


def _log(msg):
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(time.strftime("%Y-%m-%d %H:%M:%S  ") + str(msg) + "\n")
    except Exception:
        pass


def _warn(msg):
    _log(msg)


def cargar_config():
    cfg = dict(CONFIG_DEFECTO)
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            for k in CONFIG_DEFECTO:
                if k in data:
                    cfg[k] = data[k]
    except Exception:
        pass
    return cfg


def guardar_config(cfg):
    try:
        data = {k: cfg.get(k, CONFIG_DEFECTO[k]) for k in CONFIG_DEFECTO}
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as exc:
        _log(f"No pude guardar la configuración: {exc}")


# ─────────────────────────────────────────────────────────────
# EXTRACCIÓN · DETECCIÓN · ASOCIACIÓN  (lógica original de MusoSoup)
# ─────────────────────────────────────────────────────────────

def normalize_text(text):
    if not text: return ''
    text=text.replace('\r\n','\n').replace('\r','\n')
    lines=[re.sub(r'[ \t]+',' ',x).strip() for x in text.split('\n')]
    out=[]; empty=0
    for x in lines:
        if not x:
            empty+=1
            if empty<=2: out.append('')
        else:
            empty=0; out.append(x)
    return '\n'.join(out).strip()


def extract_txt(path):
    for enc in ('utf-8-sig','utf-8','cp1252','latin-1'):
        try: return path.read_text(encoding=enc)
        except (UnicodeDecodeError,OSError): pass
    return ''


def extract_pdf(path):
    if pymupdf:
        try:
            pdf=pymupdf.open(str(path)); pages=[p.get_text('text',sort=True) or '' for p in pdf]; pdf.close()
            text=normalize_text('\n\n'.join(pages))
            if text: return text
        except Exception as e:
            _warn(f'Advertencia PyMuPDF en {path.name}: {e}')
    reader=PdfReader(str(path)); pages=[]
    for page in reader.pages:
        try: pages.append(page.extract_text() or '')
        except Exception as e: _warn(f'Advertencia pypdf en {path.name}: {e}')
    return normalize_text('\n\n'.join(pages))


def extract_docx(path):
    doc=Document(str(path)); parts=[p.text for p in doc.paragraphs]
    for table in doc.tables:
        for row in table.rows: parts.append(' | '.join(c.text for c in row.cells))
    return normalize_text('\n'.join(parts))


def extract_rtf(path):
    raw=extract_txt(path)
    if rtf_to_text:
        try: return normalize_text(rtf_to_text(raw))
        except Exception: pass
    return normalize_text(raw)


def extract_html(path):
    raw=extract_txt(path)
    raw=re.sub(r'(?is)<script.*?</script>','\n',raw); raw=re.sub(r'(?is)<style.*?</style>','\n',raw)
    raw=re.sub(r'(?i)<br\s*/?>','\n',raw); raw=re.sub(r'(?i)</p\s*>','\n\n',raw)
    raw=re.sub(r'<[^>]+>',' ',raw)
    return normalize_text(html.unescape(raw))


def extract_xlsx(path):
    if not load_workbook: return ''
    wb=load_workbook(str(path),read_only=True,data_only=True); parts=[]
    for ws in wb.worksheets:
        parts.append(f'[HOJA: {ws.title}]')
        for row in ws.iter_rows(values_only=True):
            vals=['' if v is None else str(v) for v in row]
            if any(vals): parts.append(' | '.join(vals))
    return normalize_text('\n'.join(parts))


def extract_pptx(path):
    try:
        from pptx import Presentation
    except ImportError: return ''
    prs=Presentation(str(path)); parts=[]
    for i,slide in enumerate(prs.slides,1):
        parts.append(f'[DIAPOSITIVA {i}]')
        for shape in slide.shapes:
            if hasattr(shape,'text') and shape.text: parts.append(shape.text)
    return normalize_text('\n'.join(parts))


def extract_doc_old(path):
    tmp=Path(tempfile.mkdtemp(prefix='muso_doc_'))
    try:
        for exe in ('soffice','libreoffice'):
            if shutil.which(exe):
                r=subprocess.run([exe,'--headless','--convert-to','docx','--outdir',str(tmp),str(path)],capture_output=True,text=True,timeout=120)
                out=tmp/(path.stem+'.docx')
                if r.returncode==0 and out.exists(): return extract_docx(out)
        try:
            import win32com.client
            word=win32com.client.Dispatch('Word.Application'); word.Visible=False
            doc=word.Documents.Open(str(path.resolve()),ReadOnly=True); text=doc.Content.Text; doc.Close(False); word.Quit()
            return normalize_text(text)
        except Exception: return ''
    finally: shutil.rmtree(tmp,ignore_errors=True)


def extract_pages(path):
    tmp=Path(tempfile.mkdtemp(prefix='muso_pages_'))
    try:
        if path.is_dir():
            p=path/'preview.pdf'
            return extract_pdf(p) if p.exists() else ''
        try:
            with zipfile.ZipFile(path) as z: z.extractall(tmp)
            previews=list(tmp.rglob('preview.pdf'))
            return extract_pdf(previews[0]) if previews else ''
        except Exception: return ''
    finally: shutil.rmtree(tmp,ignore_errors=True)


def extract_document(path):
    s=path.suffix.lower()
    if s=='.pdf': return extract_pdf(path)
    if s=='.docx': return extract_docx(path)
    if s=='.doc': return extract_doc_old(path)
    if s in {'.txt','.md','.csv'}: return normalize_text(extract_txt(path))
    if s=='.rtf': return extract_rtf(path)
    if s in {'.html','.htm'}: return extract_html(path)
    if s=='.xlsx': return extract_xlsx(path)
    if s=='.pptx': return extract_pptx(path)
    if s=='.pages': return extract_pages(path)
    if s=='.odt':
        tmp=Path(tempfile.mkdtemp(prefix='muso_odt_'))
        try:
            with zipfile.ZipFile(path) as z: raw=z.read('content.xml').decode('utf-8','ignore')
            raw=re.sub(r'</text:p>','\n\n',raw); raw=re.sub(r'<[^>]+>',' ',raw)
            return normalize_text(html.unescape(raw))
        except Exception: return ''
        finally: shutil.rmtree(tmp,ignore_errors=True)
    return ''


def find_textual_documents(root):
    docs=[]
    for p in root.rglob('*'):
        if any(part.lower() in IGNORE_DIRS for part in p.parts): continue
        if p.is_file() and p.suffix.lower() in TEXT_EXTENSIONS: docs.append(p)
        elif p.is_dir() and p.suffix.lower()=='.pages': docs.append(p)
    return sorted(docs,key=lambda p:str(p).lower())


def score_candidate(p):
    name=p.name.lower(); score=0
    score += sum(10 for w in PRIORITY_WORDS if w in name)
    if p.suffix.lower() in {'.pdf','.docx','.rtf','.txt'}: score+=5
    return score


def detect_metadata(text):
    lines=[x.strip() for x in text.splitlines() if x.strip()]
    artist=release=kind=''

    def clean_value(v):
        v=v.strip().strip('“”"\'')
        v=re.sub(r'\s+', ' ', v).strip()
        return v

    # Explicit metadata fields are the strongest source.
    for line in lines[:120]:
        m=re.match(r'^(artist|artist name|performer|band)\s*:\s*(.+)$',line,re.I)
        if m and not artist:
            artist=clean_value(m.group(2))
        m=re.match(r'^(single|release|release title|track|track title|title)\s*:\s*(.+)$',line,re.I)
        if m and not release:
            release=clean_value(m.group(2))

    # Common press-release header:
    # "Comunicado de Prensa: Chup de Pot - «Clímax Control»"
    # "Press Release: Chup de Pot - “Clímax Control”"
    if not artist or not release:
        for line in lines[:60]:
            candidate=re.sub(
                r'^(?:comunicado\s+de\s+prensa|press\s*release|pressrelease)\s*:\s*',
                '',
                line,
                flags=re.I
            ).strip()
            m=re.match(r'^(.+?)\s+-\s+(.+?)$',candidate)
            if m:
                a=clean_value(m.group(1))
                r=clean_value(m.group(2))
                bad_prefix=('comunicado de prensa','press release','pressrelease','release date','submitted by')
                if (a and r and len(a)<=120 and len(r)<=180
                        and not a.lower().startswith(bad_prefix)):
                    if not artist:
                        artist=a
                    if not release:
                        release=r
                    break

    # Natural-language press-release patterns.
    # Example: "Indie folk artist Michi shares ‘Short Story’, the first single..."
    for line in lines[:100]:
        m=re.search(
            r'\b(?:artist|singer-songwriter|band|group)\s+([A-Z][A-Za-z0-9&.\'’ -]{1,80}?)\s+shares\s+[\'“‘]([^\'”’]+)[\'”’]',
            line
        )
        if m:
            a=clean_value(m.group(1))
            r=clean_value(m.group(2))
            if not artist:
                artist=a
            if not release:
                release=r
            break

    # If the sentence says "X shares 'Title'" without a preceding role.
    if not artist or not release:
        for line in lines[:100]:
            m=re.match(
                r'^([A-Z][A-Za-z0-9&.\'’ -]{1,80}?)\s+shares\s+[\'“‘]([^\'”’]+)[\'”’]',
                line
            )
            if m:
                if not artist:
                    artist=clean_value(m.group(1))
                if not release:
                    release=clean_value(m.group(2))
                break

    # Type: only explicit release/type language. Never infer EP/Album
    # merely because those words occur in the body.
    for line in lines[:140]:
        low=line.lower()
        if (
            re.search(r'\boriginal\s+single\b',low)
            or re.match(r'^(single|type|release type|format)\s*:\s*single\b',low)
            or low=='single'
            or re.search(r'\b(?:first|second|third|fourth|fifth|new|latest)\s+single\b',low)
            or re.search(r'\b(?:shares|unveils|announces)\b.*\bsingle\b',low)
        ):
            kind='Single'
            break
        if (
            re.search(r'\boriginal\s+ep\b',low)
            or re.match(r'^(ep|type|release type|format)\s*:\s*ep\b',low)
            or low=='ep'
        ):
            kind='EP'
            break
        if (
            re.search(r'\boriginal\s+album\b',low)
            or re.match(r'^(album|type|release type|format)\s*:\s*album\b',low)
            or low=='album'
        ):
            kind='Album'
            break

    return artist,release,kind

def norm(v):
    import unicodedata
    v=unicodedata.normalize('NFKD',v or '')
    v=''.join(c for c in v if not unicodedata.combining(c)).lower()
    return ' '.join(re.sub(r'[^a-z0-9]+',' ',v).split())


def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''): h.update(chunk)
    return h.hexdigest()


def process_zip(zip_path):
    tmp=Path(tempfile.mkdtemp(prefix='muso_zip_'))
    try:
        with zipfile.ZipFile(zip_path) as z:
            base=tmp.resolve()
            for m in z.infolist():
                target=(tmp/m.filename).resolve()
                if not str(target).startswith(str(base)): raise ValueError(f'Ruta insegura en ZIP: {m.filename}')
            z.extractall(tmp)
        sources=[]
        for p in find_textual_documents(tmp):
            _check()
            try:
                text=normalize_text(extract_document(p))
            except Exception as e:
                _warn(f'Advertencia leyendo {p.name}: {e}')
                text=''
            sources.append({'name':p.name,'text':text,'origin':'ZIP'})
        combined='\n\n'.join(s['text'] for s in sources)
        artist,release,kind=detect_metadata(combined)
        if not artist or not release:
            stem=re.sub(r'^MS[-_]', '', zip_path.stem, flags=re.I)
            # Nombre típico: Artista_con_guiones-Titulo_del_tema → separa en el primer «-».
            m=re.match(r'^([^-]+?)-(.+)$', stem) or re.match(r'^(.+?)[_](.+)$', stem)
            if m:
                if not artist:
                    artist=m.group(1).replace('_',' ').strip()
                if not release:
                    release=m.group(2).replace('_',' ').strip()
            elif not artist:
                artist=stem.replace('_',' ').strip()
        return {'artist':artist,'release':release,'type':kind,'zip_name':zip_path.name,'sources':sources}
    finally: shutil.rmtree(tmp,ignore_errors=True)


def external_docs(folder,zip_files):
    zset={p.resolve() for p in zip_files}; out=[]
    for p in find_textual_documents(folder):
        _check()
        if p.resolve() in zset: continue
        # No volver a incorporar documentos generados por este consolidador.
        if re.match(r'^(LANZAMIENTOS_|MUSOSOUP_.*_LANZAMIENTOS).*\.docx$', p.name, re.I):
            continue
        try:
            text=normalize_text(extract_document(p))
        except Exception as e:
            _warn(f'Advertencia leyendo {p.name}: {e}')
            text=''
        # No descartar el archivo aunque esté vacío o no tenga texto extraíble.
        out.append({'path':p,'name':p.name,'text':text,'hash':sha(p)})
    return out


def attach_external(launches,docs):
    unmatched=[]

    def tokens(v):
        return [t for t in norm(v).split() if len(t)>=3]

    for d in docs:
        a,r,_=detect_metadata(d['text'])
        na,nr=norm(a),norm(r)
        nn=norm(d['name'])
        candidates=[]

        for i,l in enumerate(launches):
            la,lr=norm(l['artist']),norm(l['release'])
            score=0

            # Strong: detected artist/release from the document matches the launch.
            if na and la:
                if na==la:
                    score += 180
                elif la in na or na in la:
                    score += 140
                else:
                    la_tokens=set(tokens(la))
                    na_tokens=set(tokens(na))
                    common=la_tokens & na_tokens
                    if common:
                        # Artist name token overlap is useful only for reasonably
                        # distinctive tokens.
                        score += 90 + 25*len(common)

            if nr and lr:
                if nr==lr:
                    score += 180
                elif lr in nr or nr in lr:
                    score += 140
                else:
                    common=set(tokens(lr)) & set(tokens(nr))
                    if common:
                        score += 80

            # Strong evidence directly in the document text.
            body=norm(d['text'])
            if la and len(la)>=4 and re.search(r'\b'+re.escape(la)+r'\b',body):
                score += 90
            if lr and len(lr)>=4 and re.search(r'\b'+re.escape(lr)+r'\b',body):
                score += 110

            # Filename evidence is only a secondary signal.
            if la and la in nn:
                score += 45
            if lr and lr in nn:
                score += 45

            # Directory proximity is useful for files such as
            # "michi.rtf" sitting beside "MS-Michi-Short_Story.zip".
            try:
                d_parent=norm(d['path'].parent.name)
                la_tokens=set(tokens(la))
                if d_parent and la_tokens and any(tok == d_parent for tok in la_tokens):
                    score += 140
                if d_parent and la and d_parent in la:
                    score += 110
            except Exception:
                pass

            # Short filename such as michi.rtf -> Michi.
            la_tokens=tokens(la)
            name_tokens=set(tokens(nn))
            for t in la_tokens:
                if t in name_tokens:
                    score += 55

            if score:
                candidates.append((score,i))

        candidates.sort(reverse=True)

        # Require meaningful evidence and a clear winner.
        if candidates:
            best_score,best_i=candidates[0]
            second_score=candidates[1][0] if len(candidates)>1 else 0

            if best_score>=100 and best_score>second_score:
                launches[best_i]['sources'].append({
                    'name':d['name'],
                    'text':d['text'],
                    'origin':'ARCHIVO EXTERNO'
                })
                continue

        unmatched.append(d)

    return unmatched


def detect_standalone_release(doc):
    """Detecta un lanzamiento probable dentro de un documento externo.

    Es intencionalmente conservador: solo promueve el documento si encuentra
    artista, título y tipo mediante frases de anuncio reconocibles. El texto
    original se conserva completo y la ficha queda marcada para revisión.
    """
    text = doc.get('text', '') or ''
    name = Path(doc.get('name', '')).stem
    artist = release = kind = ''

    # Casos frecuentes en comunicados y bios, con captura de frase completa.
    patterns = [
        (r'[\"“‘]([^\"”’]{2,100})[\"”’]\s+is\s+(?:the\s+)?(?:debut|new|latest|first)\s+single\s+from\s+(?:the\s+)?[\w\s/&-]{0,100}?(?:band|artist|project)\s+([A-Z][A-Za-z0-9&.\'’ -]{1,70}?)(?:,\s+arriving|\s+whose|\s+with|\.)', 'Single', 'RA'),
        (r'([A-Z][A-Za-z0-9&.\'’ -]{1,70}?)\s+(?:today\s+)?(?:have|has)\s+released\s+(?:their|its|a|the)?\s*(?:debut|new|latest)?\s*EP\s+[\"“‘]?([^\"”’.,\n]{2,100})', 'EP', 'AR'),
        (r'(?:releasing|released|release)\s+(?:our|their|its|a|the)?\s*(?:second|debut|new|latest)?\s*EP\s*[, :]?\s*[\"“‘]([^\"”’]{2,100})[\"”’]', 'EP'),
        (r'(?:new|debut|latest|first)\s+single\s+[\"“‘]([^\"”’]{2,100})[\"”’]', 'Single'),
        # "Tongue Tied is a grungy riff-rocker that ..." (ficha de una canción)
        (r'(?:^|\n)\s*([A-Z][A-Za-z0-9&.\'’ -]{1,60}?)\s+is\s+an?\s+[^.\n]{0,80}?\b(?:riff-rocker|rocker|song|track|single|ballad|anthem|banger)\b', 'Canción'),
    ]
    for entry in patterns:
        pattern, detected_kind = entry[0], entry[1]
        order = entry[2] if len(entry) > 2 else 'RA'
        m = re.search(pattern, text, re.I)
        if not m:
            continue
        if len(m.groups()) == 2:
            if order == 'AR':
                artist, release = m.group(1).strip(), m.group(2).strip()
            else:
                release, artist = m.group(1).strip(), m.group(2).strip()
            artist = re.sub(r'^(?:(?:UK|US|Brazilian|Portuguese|Swedish|Malmö-based|Brooklyn-based)\s+)?(?:duo|band|artist|group|project)\s+', '', artist, flags=re.I)
        else:
            release = m.group(1).strip()
            # First-person bios commonly identify the artist as "We're X".
            who = re.search(r"\b(?:we['’]re|we are)\s+([A-Z][A-Za-z0-9&.\'’ -]{1,60}?)(?:,|\s+(?:a|an|the)\s+|\.)", text, re.I)
            if who:
                artist = who.group(1).strip()
        kind = detected_kind
        if artist and release:
            break

    # Artist in filename is useful corroboration for short/first-person bios.
    if not artist:
        artist = re.sub(r'[_-]+', ' ', name).strip()
        artist = re.sub(r'\.(?:press|release)$', '', artist, flags=re.I)

    # For the common "debut single from ..." form, the group name can follow
    # the descriptor; avoid retaining generic words such as "band".
    if artist:
        artist = re.sub(r'^(?:the\s+)?(?:band|artist|duo|group|project)\s+', '', artist, flags=re.I).strip()
        artist = re.sub(r'\s+(?:is|makes|are)$', '', artist, flags=re.I).strip()
    if release:
        release = re.split(r'\s+(?:via|on|alongside)\s+', release, maxsplit=1, flags=re.I)[0].strip()

    if not (artist and release and kind):
        return None
    return {
        'artist': artist,
        'release': release,
        'type': kind,
        'zip_name': '',
        'sources': [{'name': doc['name'], 'text': text, 'origin': 'ARCHIVO EXTERNO'}],
        'candidate_review': True,
    }


def promote_standalone_releases(unmatched):
    """Convierte documentos externos con evidencia fuerte en fichas revisables."""
    candidates = []
    remaining = []
    seen = set()
    for doc in unmatched:
        launch = detect_standalone_release(doc)
        if not launch:
            remaining.append(doc)
            continue
        key = (norm(launch['artist']), norm(launch['release']))
        if key in seen:
            # Preserve duplicates as supporting sources on the same candidate.
            existing = next(x for x in candidates if (norm(x['artist']), norm(x['release'])) == key)
            existing['sources'].extend(launch['sources'])
        else:
            seen.add(key)
            candidates.append(launch)
    return candidates, remaining


def normalize_compare(value):
    if not value:
        return ''
    return re.sub(r'[^a-z0-9áéíóúüñ]+', ' ', value.lower()).strip()


def infer_project_type_from_text(text):
    """Solo clasifica cuando el propio texto aporta evidencia suficiente."""
    t = normalize_compare(text)
    if re.search(r'\b(band|banda|four piece|power trio|duo|group)\b', t):
        return 'Banda'
    if re.search(r'\b(musical project|music project|proyecto musical)\b', t):
        return 'Proyecto'
    if re.search(r'\b(artist|artista|singer songwriter|solo artist|composer)\b', t):
        return 'Artista'
    return ''


def detect_release_type(text):
    """
    Identifica el tipo del lanzamiento actual.
    Prioriza expresiones explícitas de single/EP/álbum y evita clasificar
    como álbum un single que simplemente menciona un álbum futuro.
    """
    t = normalize_compare(text)

    # En material de prensa, 'single' suele describir directamente el release.
    # Si aparece de forma explícita, gana sobre menciones contextuales a un álbum.
    if re.search(r'\b(new|latest|first|debut|original|forthcoming)?\s*single\b', t):
        return 'Single'
    if re.search(r'\bsencillo\b', t):
        return 'Single'

    if re.search(r'\b(ep|extended play)\b', t):
        return 'EP'

    # Para álbum, exigimos lenguaje que lo presente como el lanzamiento,
    # no solo una mención a un álbum relacionado.
    if re.search(r'\b(release|releasing|released|debut|new|forthcoming)\s+album\b', t):
        return 'Álbum'
    if re.search(r'\b(full length album|full-length album|debut album|new album)\b', t):
        return 'Álbum'

    # 'Canción/track' queda como categoría de último recurso.
    if re.search(r'\b(song|track|cancion|canción|tema)\b', t):
        return 'Canción'

    return ''

def verify_launch_metadata(launch):
    """
    Compara los metadatos detectados con TODAS las fuentes del lanzamiento.
    No inventa datos: si hay conflicto o no hay evidencia suficiente,
    lo marca como 'No verificado' / 'No especificado'.
    """
    sources = launch.get('sources', [])
    combined = '\n'.join(s.get('text', '') for s in sources if s.get('text'))

    artist = launch.get('artist', '').strip()
    release = launch.get('release', '').strip()
    detected_types = []

    # Evidencia por fuente.
    for s in sources:
        txt = s.get('text', '') or ''
        typ = detect_release_type(txt)
        if typ and typ not in detected_types:
            detected_types.append(typ)

    # Tipo de proyecto: solo si el conjunto de fuentes lo respalda.
    project_types = []
    for s in sources:
        typ = infer_project_type_from_text(s.get('text', '') or '')
        if typ and typ not in project_types:
            project_types.append(typ)

    # Si hay un único tipo explícito, se utiliza. Si hay conflicto, no se fuerza.
    project_type = project_types[0] if len(project_types) == 1 else ''
    if len(project_types) > 1:
        project_type = ''

    # El tipo de lanzamiento se conserva si todas las evidencias explícitas
    # coinciden; si no hay evidencia, se deja sin especificar.
    release_type = ''
    if detected_types:
        if len(set(detected_types)) == 1:
            release_type = detected_types[0]
        else:
            # Prioridad solo cuando una categoría aparece claramente en campos
            # de encabezado existentes del propio lanzamiento.
            original = normalize_compare(launch.get('type', ''))
            for candidate in ('Single', 'EP', 'Álbum', 'Canción'):
                if normalize_compare(candidate) in original:
                    release_type = candidate
                    break

    # Respaldo: el tipo detectado en el encabezado del press release.
    if not release_type:
        previo = (launch.get('type') or '').strip()
        release_type = {'Single': 'Single', 'EP': 'EP', 'Album': 'Álbum'}.get(previo, '')

    # Comprobación simple de presencia de artista y lanzamiento en las fuentes.
    artist_supported = bool(artist and normalize_compare(artist) in normalize_compare(combined))
    release_supported = bool(release and normalize_compare(release) in normalize_compare(combined))

    launch['verified_project_type'] = project_type or 'No especificado'
    launch['verified_artist'] = artist if artist_supported else (artist or 'No especificado')
    launch['verified_release'] = release if release_supported else (release or 'No especificado')
    launch['verified_release_type'] = release_type or 'No especificado'

    checks = []
    checks.append('✓' if artist_supported else '!')
    checks.append('✓' if release_supported else '!')
    checks.append('✓' if project_type else '!')
    checks.append('✓' if release_type else '!')
    launch['verification_status'] = 'VERIFICADO' if all(x == '✓' for x in checks) else 'REVISAR'
    if launch.get('candidate_review'):
        launch['verification_status'] = 'CANDIDATO — REVISAR'
    launch['verification_checks'] = checks





# ─────────────────────────────────────────────────────────────
# DOCX · utilidades de bajo nivel
# ─────────────────────────────────────────────────────────────
NEGRO = RGBColor(0x0A, 0x0D, 0x10)
AMARILLO_RGB = RGBColor(0xFF, 0xF3, 0x33)
GRIS = RGBColor(0x6E, 0x7A, 0x87)
GRIS_OSC = RGBColor(0x3A, 0x42, 0x4A)
VERDE = RGBColor(0x1F, 0x6B, 0x3F)
AMBAR = RGBColor(0x8A, 0x5A, 0x00)

F_NEGRO = '0A0D10'
F_AMARILLO = 'FFF333'
F_CLARO = 'F4F4EF'
F_ETIQUETA = 'E8E8E0'
F_VERDE = 'DFF3E6'
F_AMBAR = 'FFEFCF'
BORDE = 'D2D2C8'
ANCHO_UTIL = 6.8  # pulgadas, A4 con márgenes de 0.7"

_PPR_DESPUES_BDR = ('w:shd', 'w:tabs', 'w:suppressAutoHyphens', 'w:kinsoku', 'w:wordWrap',
                    'w:overflowPunct', 'w:topLinePunct', 'w:autoSpaceDE', 'w:autoSpaceDN',
                    'w:bidi', 'w:adjustRightInd', 'w:snapToGrid', 'w:spacing', 'w:ind',
                    'w:contextualSpacing', 'w:mirrorIndents', 'w:suppressOverlap', 'w:jc',
                    'w:textDirection', 'w:textAlignment', 'w:textboxTightWrap',
                    'w:outlineLvl', 'w:divId', 'w:cnfStyle', 'w:rPr', 'w:sectPr',
                    'w:pPrChange')
_PPR_DESPUES_SHD = _PPR_DESPUES_BDR[1:]
_TBLPR_DESPUES_BORDERS = ('w:shd', 'w:tblLayout', 'w:tblCellMar', 'w:tblLook',
                          'w:tblCaption', 'w:tblDescription')


def _xml_safe(texto):
    """Quita caracteres que XML no admite (los PDF a veces los traen)."""
    return re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\ufffe\uffff]', '', texto or '')


def _insertar(padre, el, sucesores):
    for tag in sucesores:
        found = padre.find(qn(tag))
        if found is not None:
            found.addprevious(el)
            return
    padre.append(el)


def _spacing(p, before=0, after=0, line=1.0):
    f = p.paragraph_format
    f.space_before = Pt(before)
    f.space_after = Pt(after)
    f.line_spacing = line


def _run(p, text, size=9.5, bold=False, color=None, italic=False):
    r = p.add_run(_xml_safe(text))
    r.font.size = Pt(size)
    r.bold = bold
    r.italic = italic
    if color is not None:
        r.font.color.rgb = color
    return r


def _p_border(p, edge='left', color='E6D800', sz=24, space=6):
    pPr = p._p.get_or_add_pPr()
    bdr = pPr.find(qn('w:pBdr'))
    if bdr is None:
        bdr = OxmlElement('w:pBdr')
        _insertar(pPr, bdr, _PPR_DESPUES_BDR)
    e = OxmlElement(f'w:{edge}')
    e.set(qn('w:val'), 'single')
    e.set(qn('w:sz'), str(sz))
    e.set(qn('w:space'), str(space))
    e.set(qn('w:color'), color)
    bdr.append(e)


def _p_shade(p, fill):
    pPr = p._p.get_or_add_pPr()
    shd = OxmlElement('w:shd')
    shd.set(qn('w:val'), 'clear')
    shd.set(qn('w:color'), 'auto')
    shd.set(qn('w:fill'), fill)
    _insertar(pPr, shd, _PPR_DESPUES_SHD)


def _hr(doc, before=2, after=4):
    p = doc.add_paragraph()
    _spacing(p, before, after)
    _p_border(p, 'bottom', BORDE, sz=4, space=1)
    for r in p.runs:
        r.font.size = Pt(2)
    p.paragraph_format.line_spacing = Pt(2)
    return p


def _campo(p, instr, size=7, color=GRIS):
    """Inserta un campo de Word (PAGE / NUMPAGES), cada parte en su propio run."""
    for kind in ('begin', 'instr', 'separate', 'text', 'end'):
        r = p.add_run()
        r.font.size = Pt(size)
        r.font.color.rgb = color
        if kind == 'instr':
            it = OxmlElement('w:instrText')
            it.set(qn('xml:space'), 'preserve')
            it.text = f' {instr} '
            r._r.append(it)
        elif kind == 'text':
            t = OxmlElement('w:t')
            t.text = '1'
            r._r.append(t)
        else:
            fc = OxmlElement('w:fldChar')
            fc.set(qn('w:fldCharType'), kind)
            r._r.append(fc)


def _tabla(doc, filas, anchos, borde=BORDE, interior=True):
    t = doc.add_table(rows=filas, cols=len(anchos))
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    t.autofit = False
    tblPr = t._tbl.tblPr
    b = OxmlElement('w:tblBorders')
    for edge in ('top', 'left', 'bottom', 'right', 'insideH', 'insideV'):
        e = OxmlElement(f'w:{edge}')
        visible = borde and (interior or edge not in ('insideH', 'insideV'))
        e.set(qn('w:val'), 'single' if visible else 'nil')
        e.set(qn('w:sz'), '4')
        e.set(qn('w:space'), '0')
        e.set(qn('w:color'), borde or 'auto')
        b.append(e)
    _insertar(tblPr, b, _TBLPR_DESPUES_BORDERS)
    for i, w in enumerate(anchos):
        t.columns[i].width = Inches(w)
        for row in t.rows:
            row.cells[i].width = Inches(w)
    for row in t.rows:
        trPr = row._tr.get_or_add_trPr()
        cs = OxmlElement('w:cantSplit')
        cs.set(qn('w:val'), 'true')
        trPr.append(cs)
    return t


def _celda(cell, fill=None, margen=(55, 55, 110, 110), borde_inf=None, valign='center'):
    tcPr = cell._tc.get_or_add_tcPr()
    if borde_inf:
        tb = OxmlElement('w:tcBorders')
        e = OxmlElement('w:bottom')
        e.set(qn('w:val'), 'single')
        e.set(qn('w:sz'), str(borde_inf[1]))
        e.set(qn('w:space'), '0')
        e.set(qn('w:color'), borde_inf[0])
        tb.append(e)
        tcPr.append(tb)
    if fill:
        shd = OxmlElement('w:shd')
        shd.set(qn('w:val'), 'clear')
        shd.set(qn('w:color'), 'auto')
        shd.set(qn('w:fill'), fill)
        tcPr.append(shd)
    mar = OxmlElement('w:tcMar')
    for k, v in zip(('top', 'bottom', 'left', 'right'), margen):
        e = OxmlElement(f'w:{k}')
        e.set(qn('w:w'), str(v))
        e.set(qn('w:type'), 'dxa')
        mar.append(e)
    tcPr.append(mar)
    va = OxmlElement('w:vAlign')
    va.set(qn('w:val'), valign)
    tcPr.append(va)


def _celda_texto(cell, partes, align=None, fill=None, **kw):
    """`partes`: lista de (texto, tamaño, negrita, color)."""
    _celda(cell, fill=fill, **kw)
    p = cell.paragraphs[0]
    _spacing(p, 0, 0)
    if align:
        p.alignment = align
    for texto, size, bold, color in partes:
        _run(p, texto, size, bold, color)
    return p


def _mantener_junto(tabla):
    for row in tabla.rows:
        for cell in row.cells:
            for p in cell.paragraphs:
                p.paragraph_format.keep_with_next = True


def _repetir_cabecera(row):
    trPr = row._tr.get_or_add_trPr()
    h = OxmlElement('w:tblHeader')
    h.set(qn('w:val'), 'true')
    trPr.append(h)


def _espacio(doc, pts=6):
    p = doc.add_paragraph()
    _spacing(p, 0, 0)
    p.paragraph_format.line_spacing = Pt(pts)
    return p


def _estado_visual(estado):
    if estado == 'VERIFICADO':
        return F_VERDE, VERDE
    return F_AMBAR, AMBAR


# ─────────────────────────────────────────────────────────────
# DOCX · bloques
# ─────────────────────────────────────────────────────────────
def add_text(doc, texto):
    """Texto de la fuente sin alterar, con espaciado compacto."""
    for line in _xml_safe(texto).split('\n'):
        p = doc.add_paragraph()
        _spacing(p, 0, 0)
        if line:
            p.add_run(line)
        else:
            p.paragraph_format.space_after = Pt(2)


def add_source(doc, source, etiqueta=None, texto_completo=True):
    p = doc.add_paragraph()
    _spacing(p, 8, 3)
    p.paragraph_format.keep_with_next = True
    p.paragraph_format.left_indent = Inches(0.08)
    _p_border(p, 'left', 'E6D800', sz=30, space=4)
    _p_shade(p, F_CLARO)
    _run(p, source['name'], 9.5, True, NEGRO)
    origen = etiqueta or source.get('origin', '')
    if origen:
        _run(p, f'   ·   {origen}', 7.5, True, GRIS)
    if not texto_completo:
        n = len((source.get('text') or '').split())
        _run(p, f'   ·   {n} palabras', 7.5, False, GRIS)
        return
    if source.get('text'):
        add_text(doc, source['text'])
    else:
        q = doc.add_paragraph()
        _spacing(q, 0, 2)
        _run(q, '[Sin texto extraíble en el archivo fuente]', 9, False, GRIS, italic=True)
    _hr(doc)


def _portada(doc, carpeta, total, candidatos, verificados, revisar, pendientes):
    t = _tabla(doc, 1, [ANCHO_UTIL], borde=None)
    cell = t.rows[0].cells[0]
    _celda(cell, fill=F_NEGRO, margen=(170, 150, 240, 240), borde_inf=(F_AMARILLO, 40),
           valign='top')
    p = cell.paragraphs[0]
    _spacing(p, 0, 1)
    _run(p, 'LANZAMIENTOS MUSOSOUP', 22, True, AMARILLO_RGB)
    d = date.today()
    p = cell.add_paragraph()
    _spacing(p, 0, 1)
    _run(p, f'{d.day:02d} de {MESES[d.month - 1]} de {d.year}', 10.5, True,
         RGBColor(0xF4, 0xF6, 0xF8))
    p = cell.add_paragraph()
    _spacing(p, 0, 0)
    _run(p, f'Carpeta procesada: {carpeta}', 7.5, False, RGBColor(0xAA, 0xB4, 0xBE))

    _espacio(doc, 8)
    # Tira de cifras
    cifras = [(str(total), 'LANZAMIENTOS ZIP', NEGRO),
              (str(candidatos), 'CANDIDATOS', AMBAR),
              (str(verificados), 'VERIFICADOS', VERDE),
              (str(revisar), 'A REVISAR', AMBAR),
              (str(pendientes), 'PENDIENTES', GRIS_OSC)]
    s = _tabla(doc, 1, [ANCHO_UTIL / 5] * 5, borde=BORDE)
    for i, (n, lbl, col) in enumerate(cifras):
        c = s.rows[0].cells[i]
        _celda(c, fill=F_CLARO, margen=(70, 70, 100, 100))
        p = c.paragraphs[0]
        _spacing(p, 0, 0)
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        _run(p, n, 18, True, col)
        q = c.add_paragraph()
        _spacing(q, 0, 0)
        q.alignment = WD_ALIGN_PARAGRAPH.CENTER
        _run(q, lbl, 7, True, GRIS)


def _indice(doc, launches):
    p = doc.add_paragraph()
    _spacing(p, 12, 4)
    p.paragraph_format.keep_with_next = True
    _p_border(p, 'left', 'E6D800', sz=30, space=5)
    p.paragraph_format.left_indent = Inches(0.08)
    _run(p, 'ÍNDICE', 11, True, NEGRO)
    anchos = [0.45, 1.8, 1.9, 1.05, 1.6]
    t = _tabla(doc, 1 + len(launches), anchos, borde=BORDE)
    for i, h in enumerate(('N.º', 'ARTISTA / BANDA', 'LANZAMIENTO', 'TIPO', 'ESTADO')):
        _celda_texto(t.rows[0].cells[i], [(h, 7.5, True, AMARILLO_RGB)], fill=F_NEGRO)
    _repetir_cabecera(t.rows[0])
    for n, l in enumerate(launches, 1):
        row = t.rows[n]
        zebra = F_CLARO if n % 2 == 0 else 'FFFFFF'
        fill_e, color_e = _estado_visual(l['verification_status'])
        _celda_texto(row.cells[0], [(f'{n:02d}', 8.5, True, GRIS)], fill=zebra)
        _celda_texto(row.cells[1], [(l['verified_artist'], 9, True, NEGRO)], fill=zebra)
        _celda_texto(row.cells[2], [(l['verified_release'], 9, False, NEGRO)], fill=zebra)
        _celda_texto(row.cells[3], [(l['verified_release_type'], 8.5, False, GRIS_OSC)],
                     fill=zebra)
        _celda_texto(row.cells[4], [(l['verification_status'], 7.5, True, color_e)],
                     fill=fill_e, align=WD_ALIGN_PARAGRAPH.CENTER)
    p = doc.add_paragraph()
    _spacing(p, 5, 0)
    _run(p, 'Los datos de cada ficha se comparan contra las fuentes recopiladas. Lo que '
            'las fuentes no respaldan queda como «No especificado» y los conflictos se '
            'marcan como REVISAR; los candidatos salen de documentos sueltos.', 7.5, False, GRIS, italic=True)


def add_launch(doc, i, l, texto_completo=True):
    _espacio(doc, 10)
    fill_e, color_e = _estado_visual(l['verification_status'])

    # Cabecera: número · artista — lanzamiento · estado
    h = _tabla(doc, 1, [0.6, 4.7, 1.5], borde=None)
    _celda_texto(h.rows[0].cells[0], [(f'{i:02d}', 15, True, AMARILLO_RGB)],
                 fill=F_NEGRO, align=WD_ALIGN_PARAGRAPH.CENTER, margen=(90, 90, 60, 60))
    c = h.rows[0].cells[1]
    p = _celda_texto(c, [(l['verified_artist'], 13, True, NEGRO)], fill=F_CLARO,
                     margen=(80, 80, 160, 100))
    if l['verified_release'] != 'No especificado':
        _run(p, '   ·   ', 11, False, GRIS)
        _run(p, l['verified_release'], 11, False, GRIS_OSC)
    _celda_texto(h.rows[0].cells[2], [(l['verification_status'], 8.5, True, color_e)],
                 fill=fill_e, align=WD_ALIGN_PARAGRAPH.CENTER)
    _mantener_junto(h)

    # Ficha 2 × 4
    f = _tabla(doc, 2, [1.5, 1.9, 1.5, 1.9], borde=BORDE)
    celdas = [
        ('ARTISTA / BANDA', l['verified_artist'], 'LANZAMIENTO', l['verified_release']),
        ('TIPO DE PROYECTO', l['verified_project_type'],
         'TIPO DE LANZAMIENTO', l['verified_release_type']),
    ]
    for r, (a, va, b, vb) in enumerate(celdas):
        row = f.rows[r]
        _celda_texto(row.cells[0], [(a, 7, True, GRIS)], fill=F_ETIQUETA)
        _celda_texto(row.cells[1], [(va, 10, False, NEGRO)])
        _celda_texto(row.cells[2], [(b, 7, True, GRIS)], fill=F_ETIQUETA)
        _celda_texto(row.cells[3], [(vb, 10, False, NEGRO)])
    _mantener_junto(f)

    # Comprobación + ZIP
    p = doc.add_paragraph()
    _spacing(p, 4, 1)
    p.paragraph_format.keep_with_next = True
    _run(p, 'COMPROBACIÓN   ', 7, True, GRIS)
    nombres = ('Artista', 'Lanzamiento', 'Proyecto', 'Tipo')
    for k, (nombre, chk) in enumerate(zip(nombres, l['verification_checks'])):
        ok = chk == '✓'
        _run(p, f'{nombre} ', 8, False, GRIS_OSC)
        _run(p, 'OK' if ok else 'REVISAR', 8, True, VERDE if ok else AMBAR)
        if k < 3:
            _run(p, '     ', 8)
    if l.get('zip_name'):
        _run(p, f'      ·      ZIP: {l["zip_name"]}', 7.5, False, GRIS)

    for s in l['sources']:
        add_source(doc, s, texto_completo=texto_completo)


def _pie(section):
    fp = section.footer.paragraphs[0]
    fp.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _spacing(fp, 2, 0)
    _run(fp, 'MusoSoup · Consolidado de lanzamientos · Página ', 7, False, GRIS)
    _campo(fp, 'PAGE')
    _run(fp, ' de ', 7, False, GRIS)
    _campo(fp, 'NUMPAGES')


def create_docx(path, launches, unmatched, folder, indice=True, texto_completo=True,
                progreso=None):
    doc = Document()
    section = doc.sections[0]
    section.page_width = Inches(8.27)
    section.page_height = Inches(11.69)
    section.top_margin = Inches(0.6)
    section.bottom_margin = Inches(0.6)
    section.left_margin = Inches(0.7)
    section.right_margin = Inches(0.7)

    style = doc.styles['Normal']
    style.font.name = 'Arial'
    style.element.rPr.rFonts.set(qn('w:eastAsia'), 'Arial')
    style.font.size = Pt(9.5)
    style.paragraph_format.space_before = Pt(0)
    style.paragraph_format.space_after = Pt(0)
    style.paragraph_format.line_spacing = 1.0

    doc.core_properties.title = 'Lanzamientos MusoSoup'
    doc.core_properties.author = 'Indie Now'

    regulares = [l for l in launches if not l.get('candidate_review')]
    candidatos = [l for l in launches if l.get('candidate_review')]
    launches = regulares + candidatos          # misma numeración en índice y fichas
    verificados = sum(1 for l in regulares if l['verification_status'] == 'VERIFICADO')
    _portada(doc, folder, len(regulares), len(candidatos), verificados,
             len(regulares) - verificados, len(unmatched))
    if indice and launches:
        _indice(doc, launches)

    for i, l in enumerate(launches, 1):
        _check()
        if i == len(regulares) + 1 and candidatos:
            _espacio(doc, 14)
            p = doc.add_paragraph()
            _spacing(p, 6, 3)
            p.paragraph_format.keep_with_next = True
            p.paragraph_format.left_indent = Inches(0.08)
            _p_border(p, 'left', 'E6D800', sz=30, space=5)
            _run(p, 'CANDIDATOS DETECTADOS EN DOCUMENTOS SUELTOS', 13, True, NEGRO)
            p = doc.add_paragraph()
            _spacing(p, 0, 2)
            p.paragraph_format.keep_with_next = True
            _run(p, 'Estas fichas no tenían un ZIP asociado. Se detectaron por frases de '
                    'lanzamiento en las fuentes y requieren revisión antes de tratarlas '
                    'como confirmadas.', 8.5, False, GRIS, italic=True)
        if progreso:
            progreso(8 + 80 * i / max(1, len(launches)),
                     f'Escribiendo {i}/{len(launches)} · {l["verified_artist"]}')
        add_launch(doc, i, l, texto_completo)

    if unmatched:
        _check()
        _espacio(doc, 14)
        p = doc.add_paragraph()
        _spacing(p, 6, 3)
        p.paragraph_format.keep_with_next = True
        p.paragraph_format.left_indent = Inches(0.08)
        _p_border(p, 'left', 'E6D800', sz=30, space=5)
        _run(p, 'DOCUMENTOS PENDIENTES DE CLASIFICAR', 13, True, NEGRO)
        p = doc.add_paragraph()
        _spacing(p, 0, 4)
        _run(p, 'Se encontraron en la carpeta del día, pero no hubo evidencia suficiente '
                'para asignarlos a un lanzamiento sin riesgo de mezclar información. '
                'Se conservan íntegramente.', 8.5, False, GRIS, italic=True)
        for i, s in enumerate(unmatched, 1):
            add_source(doc, s, etiqueta=f'N.º {i:02d}', texto_completo=texto_completo)

    _pie(section)
    path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(path))


# ─────────────────────────────────────────────────────────────
# FLUJO: escanear → analizar → generar
# ─────────────────────────────────────────────────────────────
def listar_zips(folder):
    folder = Path(folder)
    zips = []
    for p in folder.rglob('*.zip'):
        try:
            rel = p.relative_to(folder).parts
        except ValueError:
            rel = p.parts
        if any(part.lower() in IGNORE_DIRS for part in rel):
            continue
        if p.is_file():
            zips.append(p)
    return sorted(zips, key=lambda p: str(p).lower())


def resumen_carpeta(carpeta):
    """Conteo rápido (sin leer el contenido) para mostrar al elegir la carpeta."""
    folder = Path(carpeta)
    zips = listar_zips(folder)
    docs = [p for p in find_textual_documents(folder) if not GENERADO_RE.match(p.name)]
    return {'zips': len(zips), 'docs': len(docs)}


def ruta_salida(carpeta, destino=''):
    base = Path(destino) if destino else Path(carpeta) / 'INFO COMPLETA'
    return base / f'LANZAMIENTOS_{date.today().isoformat()}.docx'


def _ruta_disponible(path):
    """Si el Word de hoy está abierto (bloqueado), guarda con sufijo _2, _3…"""
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        return path
    try:
        with open(path, 'ab'):
            pass
        return path
    except OSError:
        pass
    n = 2
    while True:
        cand = path.with_name(f'{path.stem}_{n}{path.suffix}')
        if not cand.exists():
            return cand
        n += 1


def analizar(carpeta, progreso):
    _cancelar_evt.clear()
    folder = Path(carpeta)
    zips = listar_zips(folder)
    progreso(2, f'{len(zips)} ZIP encontrados en la carpeta.')
    launches, errores = [], []
    total = max(1, len(zips))
    for i, z in enumerate(zips, 1):
        _check()
        progreso(3 + 67 * (i - 1) / total, f'ZIP {i}/{len(zips)} · {z.name}')
        try:
            l = process_zip(z)
            launches.append(l)
        except Cancelado:
            raise
        except Exception as exc:
            errores.append((z.name, str(exc)))
            _log(f'ERROR en {z.name}: {exc}\n{traceback.format_exc()}')

    _check()
    progreso(72, 'Buscando documentos sueltos fuera de los ZIP…')
    ext = []
    unmatched = []
    asociados = 0
    try:
        ext = external_docs(folder, zips)
        _check()
        progreso(90, f'{len(ext)} documentos sueltos · asociándolos a su lanzamiento…')
        unmatched = attach_external(launches, ext)
        candidatos, unmatched = promote_standalone_releases(unmatched)
        # Documentos que nombran a un artista recién detectado se vinculan a él.
        if candidatos and unmatched:
            unmatched = attach_external(candidatos, unmatched)
        launches.extend(candidatos)
        asociados = len(ext) - len(unmatched) - sum(len(c['sources']) for c in candidatos)
    except Cancelado:
        raise
    except Exception as exc:
        errores.append(('DOCUMENTOS EXTERNOS', str(exc)))
        _log(f'ERROR externos: {exc}\n{traceback.format_exc()}')

    for n, l in enumerate(launches):
        l['id'] = n
        verify_launch_metadata(l)
    for n, u in enumerate(unmatched):
        u['id'] = n
        u.setdefault('origin', 'ARCHIVO EXTERNO')
    return {
        'carpeta': str(folder),
        'zips': len(zips),
        'externos': len(ext),
        'asociados': max(0, asociados),
        'candidatos': sum(1 for l in launches if l.get('candidate_review')),
        'launches': launches,
        'unmatched': unmatched,
        'errores': errores,
    }


def generar(analisis, sel_lanzamientos, sel_sin_asociar, cfg, progreso):
    _cancelar_evt.clear()
    launches = [l for l in analisis['launches'] if l['id'] in sel_lanzamientos]
    unmatched = ([u for u in analisis['unmatched'] if u['id'] in sel_sin_asociar]
                 if cfg.get('sin_asociar', True) else [])
    if not launches and not unmatched:
        raise RuntimeError('No hay nada seleccionado para escribir en el documento.')
    if cfg.get('orden') == 'artista':
        launches.sort(key=lambda l: norm(l['verified_artist']))
    destino = ruta_salida(analisis['carpeta'], cfg.get('destino', ''))
    progreso(4, 'Preparando el documento…')
    # Se arma en memoria; la ruta final se decide justo antes de guardar.
    tmp = Path(tempfile.mkdtemp(prefix='muso_out_')) / destino.name
    try:
        create_docx(tmp, launches, unmatched, analisis['carpeta'],
                    indice=bool(cfg.get('indice', True)),
                    texto_completo=bool(cfg.get('texto_completo', True)),
                    progreso=progreso)
        _check()
        progreso(95, 'Guardando…')
        final = _ruta_disponible(destino)
        shutil.copyfile(tmp, final)
    finally:
        shutil.rmtree(tmp.parent, ignore_errors=True)
    return final


class Backend:
    def config(self):
        return cargar_config()

    def guardar(self, cfg):
        guardar_config(cfg)

    def existe(self, ruta):
        return bool(ruta) and os.path.exists(ruta)

    def resumen(self, carpeta):
        return resumen_carpeta(carpeta)

    def salida_prevista(self, carpeta, destino=''):
        return str(ruta_salida(carpeta, destino))

    def analizar(self, carpeta, progreso):
        return analizar(carpeta, progreso)

    def generar(self, analisis, sel_lanzamientos, sel_sin_asociar, cfg, progreso):
        return str(generar(analisis, sel_lanzamientos, sel_sin_asociar, cfg, progreso))

    def cancelar(self):
        _cancelar_evt.set()

    def registrar_error(self, exc, tb):
        _log('ERROR\n' + (tb or repr(exc)))


def main():
    _cancelar_evt.clear()
    backend = Backend()
    root = tk.Tk()
    # La ventana se arma completa fuera de pantalla y aparece de una sola vez.
    root.withdraw()
    alpha_ok = True
    try:
        root.attributes('-alpha', 0.0)
    except Exception:
        alpha_ok = False
    init_fonts(root)
    app = MusoSoupApp(root, backend)
    app._alpha_ok = alpha_ok
    root.protocol('WM_DELETE_WINDOW', app.cerrar)
    root.mainloop()


if __name__ == '__main__':
    try:
        main()
    except Exception as ex:
        _log(f'fatal: {ex!r}\n{traceback.format_exc()}')
        try:
            messagebox.showerror('Indie Now · MusoSoup', str(ex))
        except Exception:
            pass
