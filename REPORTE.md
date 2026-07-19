# T0RD0WNL04D — Reporte Técnico Completo (V.RK13.1.1)

---

## 1. Descripción General

Aplicación CLI (interfaz de línea de comandos) para descargar audio/video desde YouTube y Spotify, con suite de herramientas profesionales de audio (T00L5RK13). Escrita en **Python 3.14**, diseñada para entornos **Termux (Android)**.

| Atributo | Valor |
|----------|-------|
| **Lenguaje** | Python 3.14 |
| **Paradigma** | Programación estructurada / imperativa |
| **Entry point** | `t0rd0wnl04d.py` (~410 líneas) |
| **Total código** | ~2,500 líneas distribuidas en 13 módulos |
| **Licencia** | No especificada |

---

## 2. Arquitectura del Proyecto

```
descargar-musica/
├── t0rd0wnl04d.py          ← Entry point / menú principal
├── requirements.txt         ← Dependencias PyPI
├── config.json              ← Config persistente
├── .history.json            ← Historial de descargas
├── .cover_cache/            ← Caché de carátulas
├── .gitignore
├── REPORTE.md               ← Este documento
├── core/                    ← Lógica de negocio
│   ├── __init__.py
│   ├── downloader.py        ← Descarga de audio (yt-dlp)
│   ├── video_downloader.py  ← Descarga de video (yt-dlp)
│   ├── spotify.py           ← Importación desde Spotify
│   ├── cover.py             ← Carátulas multi-fallo (iTunes → Deezer)
│   ├── metadata_fixer.py    ← Corrector interactivo de metadatos ID3
│   ├── tools_rk13.py        ← T00L5RK13: conversor + deduplicador
│   └── utils.py             ← Utilidades, formatos, wrappers yt-dlp
├── ui/                      ← Capa de presentación (Rich)
│   ├── __init__.py
│   └── interface.py         ← Banners, tablas, menús, prompts custom
└── data/
    ├── __init__.py
    └── history.py           ← Historial de descargas JSON
```

---

## 3. Dependencias Externas

| Librería | Propósito | Tipo |
|----------|-----------|------|
| **yt-dlp** (CLI) | Motor de descarga real (YouTube, YouTube Music) | Externa (CLI) |
| **rich ≥ 13.9** | UI en terminal: colores, paneles, tablas, barras de progreso | PyPI |
| **mutagen ≥ 1.47** | Post-procesado de metadatos ID3 (mp3/m4a) | PyPI |
| **spotapi ≥ 1.2** | Cliente no-oficial de la API de Spotify | PyPI |
| **ffmpeg** (CLI) | Requerido por yt-dlp + conversor interno T00L5RK13 | Externa (CLI) |

---

## 4. Módulos — Explicación Detallada

### 4.1 `core/utils.py` (122 líneas)

**Utilidades base** — Funciones helper compartidas por todos los módulos.

| Función | Descripción |
|---------|-------------|
| `get_ytdlp_path()` | Busca yt-dlp primero en `venv/bin/`, fallback al PATH del sistema |
| `extract_info(url)` | Consulta metadatos de un video vía `yt-dlp --dump-json`. Timeout 30s |
| `extract_playlist_info(url, limit)` | Extrae lista de entradas de una playlist de YouTube. Timeout 60s |
| `search_youtube(query, limit=10)` | Busca videos en YouTube via `ytsearch{N}` de yt-dlp |
| `format_duration(seconds)` | Convierte segundos a formato legible `"Xm YYs"` |

**Formatos definidos:**

```python
FORMATS = {
    "1": {"name": "MP3 320kbps",   "ext": "mp3",  "bitrate": "320k"},
    "2": {"name": "MP3 128kbps",   "ext": "mp3",  "bitrate": "128k"},
    "3": {"name": "M4A AAC",       "ext": "m4a",  "bitrate": ""},
    "4": {"name": "OPUS",          "ext": "opus", "bitrate": ""},
    "5": {"name": "FLAC (lossless)", "ext": "flac","bitrate": ""},
    "6": {"name": "WAV (sin comprimir)", "ext": "wav","bitrate": ""},
}

VIDEO_FORMATS = {
    "1": {"name": "MP4 1080p",   "ext": "mp4",  "quality": "bestvideo[height<=1080]+bestaudio/best[height<=1080]"},
    "2": {"name": "MP4 720p",    "ext": "mp4",  "quality": "bestvideo[height<=720]+bestaudio/best[height<=720]"},
    "3": {"name": "MP4 480p",    "ext": "mp4",  "quality": "bestvideo[height<=480]+bestaudio/best[height<=480]"},
    "4": {"name": "MP4 360p",    "ext": "mp4",  "quality": "bestvideo[height<=360]+bestaudio/best[height<=360]"},
    "5": {"name": "WebM 1080p",  "ext": "webm", "quality": "bestvideo[height<=1080]+bestaudio/best[height<=1080]"},
    "6": {"name": "Mejor calidad","ext": "mp4",  "quality": "bestvideo+bestaudio/best"},
}
```

---

### 4.2 `core/downloader.py` (~391 líneas)

**Motor de descarga de AUDIO** — El módulo más grande y complejo del proyecto.

#### `_build_cmd(ytdlp, fmt, template, url)`

Construye el comando `yt-dlp`:
- **MP4 (video):** `-f bestvideo+bestaudio/best` con `--merge-output-format mp4`
- **Audio:** `-f bestaudio/best` con `--extract-audio`, `--audio-format`, `--audio-quality`, `--embed-thumbnail`, `--embed-metadata`, `--parse-metadata` (uploader→artist, playlist_title→album, upload_date→date)

#### `_run_ytdlp(cmd, prefix)`

Ejecuta yt-dlp como subproceso con `subprocess.Popen` y barra de progreso interactiva Rich:
- `BarColumn`, `DownloadColumn`, `TransferSpeedColumn`, `TimeRemainingColumn`
- Parsea líneas de salida: `XX%`, `Destination:`, `[ExtractAudio]`, `[Metadata]`, `[Merger]`, `ERROR`, `WARNING`

#### `_attempt_download(cmd, out_dir, ext)`

Wrapper con 2 fallbacks de búsqueda de archivo destino.

#### `single(url, fmt_key, output_dir)`

Flujo completo de descarga individual con reintento automático.

#### `playlist(url, fmt_key, limit, output_dir)`

Descarga de playlists con tabla de canciones, confirmación, delay 0.5s anti rate-limit.

#### `batch(urls, fmt_key, folder_name, output_dir, titles)`

Descarga por lote de URLs arbitrarias.

#### `_apply_metadata(filepath, info, ext)`

Post-procesado con **mutagen**: escribe título, artista, álbum, carátula en ID3 (mp3) o MP4 tags (m4a). Los metadatos vienen de `core/cover.py`.

---

### 4.3 `core/video_downloader.py` (~241 líneas)

**Motor de descarga de VIDEO** — Estructuralmente idéntico a `downloader.py` pero:
- Usa `VIDEO_FORMATS` y `_build_video_cmd()` (sin `--extract-audio`)
- Reusa `_run_ytdlp()` y `_attempt_download()` del módulo de audio
- No aplica metadatos vía mutagen
- Mismas 3 operaciones: `single()`, `playlist()`, `batch()`

---

### 4.4 `core/spotify.py` (271 líneas)

**Importación desde Spotify** — Usa `spotapi` para extraer tracks/playlists/álbumes/episodios y resuelve cada track a YouTube via `search_youtube()`.

Soporta:
- `https://open.spotify.com/track/XXXX`
- `https://open.spotify.com/playlist/XXXX`
- `https://open.spotify.com/album/XXXX`
- `https://open.spotify.com/episode/XXXX`
- `spotify:track:XXXX` (URI format)

Flujo: detecta tipo de link → importa metadatos → busca en YouTube → retorna lista de `(nombre, url_youtube)` para descargar.

---

### 4.5 `core/cover.py` (~199 líneas)

**Carátulas multi-fallo** — Busca carátulas cuadradas en alta resolución con 3 fuentes en cascada:

1. **iTunes Search API** — 5 etapas progresivas:
   - Artista + Título (exacto)
   - Solo artista (cualquier canción del mismo artista)
   - Solo título
   - Palabras clave (filtra stopwords)
   - Palabras clave + artista
2. **Deezer API** — Cover `cover_xl` (1000×1000), sin API key
3. Ya **no usa YouTube thumbnails** (son rectangulares y se ven feas)

`_clean_title()` elimina basura de títulos YouTube: `(Official Video)`, `[4K]`, `feat.`, `｜`, `(Letra)`, etc.

Cachea carátulas en `.cover_cache/` para no redescargar.

---

### 4.6 `core/metadata_fixer.py` (~608 líneas)

**Corrector interactivo de metadatos** — Navegador de archivos + fix individual o por lote.

| Función | Descripción |
|---------|-------------|
| `_read_tags(filepath)` | Lee metadatos ID3/MP4/FLAC/OGG con mutagen |
| `_write_tags(filepath, artist, title, album, cover_path)` | Escribe metadatos + carátula |
| `_guess_artist_title(filepath)` | Adivina artista/título desde nombre de archivo |
| `scan_for_browser(current)` | Escanea directorio, separa carpetas y archivos de audio |
| `detect_storage_roots()` | Detecta almacenamiento interno/SD en Termux |
| `interactive_browser(start_path)` | Navegador interactivo: ver carpetas, previsualizar tags, corregir individual o por lote |
| `fix_folder(start_path)` | Corrección masiva: escanea todos los archivos, busca carátula vía `_resolve_cover_url()`, aplica metadatos con barra de progreso |

**Tool 1 del menú T00L5RK13.**

---

### 4.7 `core/tools_rk13.py` (~623 líneas)

**T00L5RK13 — Suite de herramientas de audio profesional.** Menú con 3 herramientas:

#### Tool 1 — Corregir Metadatos
Llama a `interactive_browser()` de `metadata_fixer.py`. Navegación por carpetas, previsualización y corrección de metadatos + carátulas.

#### Tool 2 — Convertir Formato de Audio
Conversión batch con ffmpeg entre formatos:

| Formato | Codec | Bitrates |
|---------|-------|----------|
| MP3 | libmp3lame | Normal 128k / Alta 192k / Máxima 320k |
| M4A (AAC) | aac | Normal 128k / Alta 192k / Máxima 256k |
| Opus | libopus | Normal 96k / Alta 128k / Máxima 160k |
| OGG Vorbis | libvorbis | Normal 128k / Alta 192k / Máxima 256k |
| FLAC | flac | Lossless |

Flujo:
1. Navegador interactivo para seleccionar carpeta origen
2. Resumen de archivos encontrados por extensión
3. Selección de formato destino y calidad
4. Crea carpeta nueva `nombreOriginal_formato/`
5. Convierte cada archivo con barra de progreso
6. Aplica metadatos + carátula (iTunes multi-fallo)
7. Opción de eliminar carpeta original al finalizar

#### Tool 3 — Organizar / Deduplicar
Detección de archivos duplicados en una carpeta:

| Método | Descripción |
|--------|-------------|
| Nombre | Compara nombres normalizados (sin extensión, minúsculas, sin espacios extra) |
| Metadatos | Compara artista + título de tags ID3 |
| Hash MD5 | Compara hash exacto del contenido del archivo |

Acciones por grupo de duplicados:
- Conservar el de **mejor bitrate**
- Conservar el **más pequeño**
- Conservar un **formato específico** (ej: m4a)
- **Manual**: elegir qué archivo conservar

---

### 4.8 `ui/interface.py` (~263 líneas)

**Capa de presentación** — Toda la UI usa la librería **Rich**.

| Función | Descripción |
|---------|-------------|
| `clear()` | Limpia pantalla (compatible Termux) |
| `show_banner()` | Banner estilizado con nombre + binario + créditos |
| `show_menu()` | Menú principal con 12 opciones + emojis |
| `show_info_panel(info)` | Panel de información del video |
| `show_formats_table()` | Tabla de formatos de audio |
| `show_video_formats_table()` | Tabla de formatos de video |
| `show_playlist_table()` | Lista de canciones con duración total |
| `show_search_results()` | Resultados de búsqueda YouTube |
| `show_urls_table()` | Lista de URLs a descargar |
| `config_menu()` | Cambiar directorio de descargas |
| `prompt_ask(prompt_text, default="")` | Prompt custom con `input()` plano (evita eco `^M` en Termux) |
| `press_enter()` | Espera Enter con `input()` plano |
| `confirm_ask(prompt_text, default=True)` | Confirmación Sí/No con `input()` plano |

**Nota:** Todos los prompts (`prompt_ask`, `confirm_ask`, `press_enter`) usan `input()` de Python plano en vez de `Prompt.ask()`/`Confirm.ask()`/`console.input()` de Rich para evitar el eco `^M` en Termux.

---

### 4.9 `data/history.py` (45 líneas)

**Historial de descargas** en `.history.json`. Máximo 50 entradas FIFO. Cada entrada: `{titulo, url, formato, fecha}`. Visualización: tabla Rich con últimas 15 descargas.

---

### 4.10 `t0rd0wnl04d.py` (~410 líneas)

**Orquestador principal / Entry point** — Loop principal del menú con 12 opciones.

```
while True:
    show_banner()
    show_menu()
    choice = prompt_ask()
    ─────────────────────────────────
    choice == "1"  → Spotify (import + download batch)
    choice == "2"  → Buscar YouTube (search + select + download)
    choice == "3"  → Una Canción Audio (URL + format + single)
    choice == "4"  → Lista Audio (playlist URL + format + limit)
    choice == "5"  → Varios Audios (folder + URLs + format + batch)
    choice == "6"  → Un Video (URL + format + single video)
    choice == "7"  → Lista Videos (playlist URL + format + limit video)
    choice == "8"  → Varios Videos (folder + URLs + format + batch video)
    choice == "9"  → Ver Registro (history.show())
    choice == "10" → T00L5RK13 (tools_rk13_menu())
    choice == "11" → Ajustes App (config_menu())
    choice == "12" → Salir
```

#### Detalle por Opción

**1 — Spotify**
Pide URL de Spotify, llama a `import_from_spotify()`, valida resultados, pide confirmación y formato, ejecuta `download_batch()`.

**2 — Buscar YouTube**
Pide query, ejecuta `search_youtube()` con spinner, muestra resultados numerados. Soporta selección individual (`1`), rango (`1-3`), todos (`*`).

**3 — Una Canción (Audio)**
Pide URL, muestra formatos, directorio personalizado opcional, ejecuta `download_single()`. Si falla, ofrece reintentar con otro formato.

**4 — Lista Audio**
Pide URL de playlist, formato, directorio, límite de canciones. Ejecuta `download_playlist()`.

**5 — Varios Audios**
Pide nombre de carpeta, loop de ingreso de URLs, formato. Ejecuta `download_batch()`.

**6, 7, 8 — Video**
Idéntico a 3, 4, 5 pero usando `core/video_downloader.py`.

**9 — Registro**
Muestra historial de descargas.

**10 — T00L5RK13**
Abre la suite de herramientas profesionales con 3 subherramientas (ver 4.7).

**11 — Ajustes**
Cambia directorio de descargas por defecto.

**12 — Salir**
Break del loop y mensaje de despedida.

---

## 5. Flujo de Datos Típico

### Ejemplo: Descargar una canción desde Spotify

```
Usuario pega URL de Spotify
  ↓
t0rd0wnl04d.py (opción 1)
  ↓ llama a
core/spotify.import_from_spotify(url)
  ↓ detecta tipo vía regex
detect_link_type(url) → ("track", "1evWpIlEfSZnXtHtpILB6b")
  ↓
_import_track(track_id)
  ↓ API HTTP GraphQL
spotapi.Public.song_info(track_id)
  → trackUnion.name = "Calabria"
  → trackUnion.firstArtist.profile.name = "DMNDS"
  ↓
core.utils.search_youtube("DMNDS - Calabria")
  → yt-dlp ytsearch → YouTube URL
  ↓
Retorna (name, [(name, yt_url)])
  ↓
Usuario confirma descarga + formato (ej: M4A AAC)
  ↓
core/downloader.batch([yt_url], fmt_key, ...)
  ↓ por cada URL
_download_track()
  ↓
_build_cmd() → args de yt-dlp
  ↓
_run_ytdlp() → subprocess.Popen + barra Rich
  ↓
_attempt_download() → reintento si falla
  ↓
_apply_metadata() → mutagen + cover (iTunes multi-fallo)
  ↓
history.save()
  ↓
Resumen: "✓ 1/1 DMNDS - Calabria"
```

---

## 6. Consideraciones Técnicas Clave

### 6.1 Sin OOP
Todo el código es procedural/funcional, sin clases definidas por el usuario. La UI se inyecta como módulo global `console = Console()`.

### 6.2 Subprocesos
yt-dlp y ffmpeg se ejecutan como `subprocess.Popen` con stdout parseado línea por línea para barras de progreso en tiempo real.

### 6.3 API de Spotify no-oficial
Usa `spotapi` que reverse-ingeniera la API GraphQL de Spotify. Inherentemente frágil: los hashes de consultas y estructura de respuestas pueden cambiar.

### 6.4 Metadatos híbridos YouTube + iTunes + Deezer
Combina 3 fuentes para metadatos. Si iTunes no encuentra match exacto, prueba Deezer. Si Deezer falla, busca por artista relacionado en iTunes. No usa YouTube thumbnails (rectangulares).

### 6.5 Robustez
- Reintentos automáticos en descargas fallidas
- Timeouts en consultas a yt-dlp (30s singles, 60s playlists)
- Fallback para detección de archivos destino
- Prompts con `input()` plano para evitar problemas de terminal en Termux

### 6.6 Target Termux
- Compatible con Android vía Termux
- Usa `clear` en vez de `cls`
- Sin dependencias gráficas (solo terminal)
- Almacenamiento detectado automáticamente (interno/SD)

---

## 7. Posibles Mejoras / Deuda Técnica

| Área | Problema | Impacto |
|------|----------|---------|
| **Tests** | Zero test coverage | Riesgo alto de regresiones |
| **Logging** | Usa `console.print()` en vez de `logging` | Sin niveles ni rotación |
| **Manejo de errores** | `except Exception` genéricos en múltiples lugares | Oculta errores específicos |
| **Configuración** | Solo directorio de descarga. No persiste formato favorito | UX limitada |
| **Concurrencia** | Descargas secuenciales con delay 0.5s | Lento para lotes grandes |
| **Dependencia frágil** | `spotapi` no es oficial de Spotify | Cambios en API rompen el flujo |
| **Type hints** | Mayoría del código sin anotaciones | Menos mantenible |
| **Internacionalización** | Solo español, textos hardcodeados | No scalable |

---

## 8. Perfil para Creador de Contenido

### Nichos Potenciales
- Herramientas prácticas para Android/Termux
- Descarga y procesado de contenido multimedia
- Automatización con Python

### Ángulos de Contenido
- Cómo construir un downloader YouTube/Spotify desde cero
- Integración de APIs no-oficiales (Spotify reverse engineering)
- UI en terminal profesional con Rich
- Post-procesado de metadatos de audio con mutagen
- Suite de herramientas CLI profesionales (T00L5RK13)

### Stack
```
Python 3.14  +  yt-dlp  +  Rich  +  mutagen  +  spotapi  +  ffmpeg
```

---

## 9. Resumen de Archivos

| Archivo | Líneas | Propósito |
|---------|--------|-----------|
| `t0rd0wnl04d.py` | ~410 | Entry point, menú principal |
| `core/__init__.py` | 0 | Package marker |
| `core/downloader.py` | ~391 | Motor de descarga de audio |
| `core/video_downloader.py` | ~241 | Motor de descarga de video |
| `core/spotify.py` | 271 | Importación desde Spotify |
| `core/cover.py` | ~199 | Carátulas multi-fallo (iTunes → Deezer) |
| `core/metadata_fixer.py` | ~608 | Corrector interactivo de metadatos |
| `core/tools_rk13.py` | ~623 | T00L5RK13: conversor + deduplicador |
| `core/utils.py` | 122 | Utilidades, formatos, wrappers |
| `ui/__init__.py` | 0 | Package marker |
| `ui/interface.py` | ~263 | Renderizado Rich + prompts custom |
| `data/__init__.py` | 0 | Package marker |
| `data/history.py` | 45 | Historial JSON |
| `requirements.txt` | ~5 | Dependencias PyPI |
| **Total** | **~2,500** | |
