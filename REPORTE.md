# T0RD0WNL04D — Reporte Técnico Completo

---

## 1. Descripción General

Aplicación CLI (interfaz de línea de comandos) para descargar audio/video desde YouTube y Spotify. Escrita en **Python 3.14**, diseñada para entornos **Termux (Android)**.

| Atributo | Valor |
|----------|-------|
| **Lenguaje** | Python 3.14 |
| **Paradigma** | Programación estructurada / imperativa (sin clases ni OOP, excepto uso de librerías externas) |
| **Entry point** | `t0rd0wnl04d.py` (369 líneas) |
| **Total código** | ~1,400 líneas distribuidas en 10 módulos |
| **Licencia** | No especificada |

---

## 2. Arquitectura del Proyecto

```
descargar-musica/
├── t0rd0wnl04d.py          ← Entry point / menú principal
├── requirements.txt         ← Dependencias
├── config.json              ← Config persistente
├── .history.json            ← Historial de descargas
├── .cover_cache/            ← Caché de carátulas (iTunes)
├── downloads/               ← Descargas por defecto
├── core/                    ← Módulos de lógica de negocio
│   ├── __init__.py
│   ├── downloader.py        ← Descarga de audio
│   ├── video_downloader.py  ← Descarga de video
│   ├── spotify.py           ← Importación desde Spotify
│   ├── cover.py             ← Metadatos y carátulas (iTunes)
│   └── utils.py             ← Utilidades (yt-dlp wrapper, formatos)
├── ui/                      ← Capa de presentación
│   ├── __init__.py
│   └── interface.py         ← Renderizado Rich (banners, tablas, menús)
└── data/
    ├── __init__.py
    └── history.py           ← Persistencia de historial JSON
```

---

## 3. Dependencias Externas

| Librería | Propósito | Tipo |
|----------|-----------|------|
| **yt-dlp** (CLI) | Motor de descarga real (YouTube, YouTube Music) | Externa (CLI) |
| **rich ≥ 13.9** | UI en terminal: colores, paneles, tablas, barras de progreso | PyPI |
| **mutagen ≥ 1.47** | Post-procesado de metadatos ID3 (mp3/m4a) | PyPI |
| **spotapi ≥ 1.2** | Cliente no-oficial de la API de Spotify (playlists, tracks, álbumes) | PyPI |
| **ffmpeg** (externo) | Requerido por yt-dlp para conversión de audio/video | Externa (CLI) |

---

## 4. Módulos — Explicación Detallada

### 4.1 `core/utils.py` (122 líneas)

**Utilidades base** — Funciones helper compartidas por todos los módulos.

| Función | Descripción |
|---------|-------------|
| `get_ytdlp_path()` | Busca yt-dlp primero en `venv/bin/`, fallback al PATH del sistema |
| `extract_info(url)` | Consulta metadatos de un video vía `yt-dlp --dump-json`. Retorna título, duración, uploader, vistas, etc. Timeout 30s |
| `extract_playlist_info(url, limit)` | Extrae lista de entradas de una playlist de YouTube. Timeout 60s. Soporta límite opcional |
| `search_youtube(query, limit=10)` | Busca videos en YouTube via `ytsearch{N}` de yt-dlp. Retorna lista con título, url, duración, canal |
| `format_duration(seconds)` | Convierte segundos a formato legible `"Xm YYs"` o `"Xh Ym Zs"` |

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

### 4.2 `core/downloader.py` (387 líneas)

**Motor de descarga de AUDIO** — El módulo más grande y complejo del proyecto.

#### `_build_cmd(ytdlp, fmt, template, url)`

Construye el comando `yt-dlp` según el formato destino:
- **MP4 (video):** `-f bestvideo+bestaudio/best` con `--merge-output-format mp4`
- **Audio:** `-f bestaudio/best` con `--extract-audio`, `--audio-format`, `--audio-quality`, más flags de embedding: `--embed-thumbnail`, `--embed-metadata`, y `--parse-metadata` para mapear uploader→artist, playlist_title→album, upload_date→date

#### `_run_ytdlp(cmd, prefix)`

Ejecuta yt-dlp como subproceso con `subprocess.Popen` y pipe de stdout en modo texto línea por línea.

- Renderiza una **barra de progreso interactiva** usando `rich.progress.Progress` con:
  - `BarColumn` (barra visual)
  - `DownloadColumn` (tamaño descargado)
  - `TransferSpeedColumn` (velocidad)
  - `TimeRemainingColumn` (tiempo restante)
- **Parseo de líneas de salida:**
  - `[download] XX.X%` → actualiza porcentaje en la barra
  - `Destination: ...` → detecta ruta del archivo de salida
  - `[ExtractAudio]` → cambia descripción a "Extrayendo audio..."
  - `[Metadata]` / `[EmbedThumbnail]` → cambia a "Imagen y metadata incorporada..."
  - `[Merger] into "..."` → detecta archivo mergeado
  - `ERROR` / `WARNING` → acumula mensajes de error

#### `_attempt_download(cmd, out_dir, ext)`

Wrapper que:
1. Llama a `_run_ytdlp()`
2. Si éxito y archivo detectado → retorna `(True, path, errors)`
3. Fallback 1: busca archivos por extensión en `out_dir`
4. Fallback 2: cualquier archivo en `out_dir`
5. Si no encuentra nada → retorna `(False, None, errors)`

#### `single(url, fmt_key, output_dir)`

Flujo completo de descarga individual:
1. Valida formato
2. Crea directorio
3. Extrae info del video
4. Muestra panel de información
5. Construye y ejecuta comando
6. **Reintenta automáticamente** si falla (con sleep 1s)
7. Aplica metadatos vía `_apply_metadata()`
8. Guarda en historial

#### `playlist(url, fmt_key, limit, output_dir)`

1. Extrae entries de la playlist
2. Crea subdirectorio con nombre de la playlist
3. Muestra tabla de canciones con duración total
4. Pide confirmación al usuario
5. Itera secuencialmente: descarga cada entry con contador `[i/total]`
6. Delay de 0.5s entre tracks (anti rate-limit)
7. Muestra resumen con tabla de completadas/fallidas/ubicación

#### `batch(urls, fmt_key, folder_name, output_dir, titles)`

Similar a playlist pero para URLs arbitrarias (no necesariamente de una playlist). Acepta `titles` opcional para mostrar nombres en lugar de URLs.

#### `_apply_metadata(filepath, info, ext)`

Post-procesado de metadatos usando **mutagen**:
- **m4a (MP4):** Escribe `\xa9nam` (título), `\xa9ART` (artista), `\xa9alb` (álbum), `covr` (carátula JPEG)
- **mp3 (ID3):** Escribe `TIT2` (título), `TPE1` (artista), `TALB` (álbum), `APIC` (carátula)
- Los metadatos vienen de `core/cover.py` que consulta iTunes, con fallback a datos limpios de YouTube

---

### 4.3 `core/video_downloader.py` (240 líneas)

**Motor de descarga de VIDEO** — Estructuralmente idéntico a `downloader.py` pero:

- Usa `_build_video_cmd()` que no aplica `--extract-audio`
- Usa `VIDEO_FORMATS` en vez de `FORMATS`
- Reusa `_run_ytdlp()` y `_attempt_download()` del módulo de audio (importados directamente)
- No aplica metadatos vía mutagen (innecesario para video)
- Mismas 3 operaciones: `single()`, `playlist()`, `batch()`
- Reintento automático en caso de fallo

---

### 4.4 `core/spotify.py` (271 líneas)

**Importación desde Spotify** — El módulo más complejo en términos de integración externa.

#### `detect_link_type(url)`

Usa dos regex para parsear URLs y URIs de Spotify:

```python
SPOTIFY_RE = re.compile(
    r'(?:open\.spotify\.com|spotify)[/:]'
    r'(playlist|episode|track|album)/([a-zA-Z0-9]+)'
)
```

Soporta:
- `https://open.spotify.com/track/XXXX`
- `https://open.spotify.com/playlist/XXXX`
- `https://open.spotify.com/album/XXXX`
- `https://open.spotify.com/episode/XXXX`
- `spotify:track:XXXX` (URI format)

#### `import_from_spotify(url)`

Dispatcher principal:
1. Detecta tipo de link
2. Delega a la función específica según tipo
3. Retorna `(nombre, lista_de_resultados)` o `(None, None)` en error

Cada resultado es un tuple `(titulo_artista_track, youtube_url)`.

#### `_import_playlist(playlist_id)`

1. Usa `spotapi.PublicPlaylist(playlist_id)` para conectar
2. Obtiene nombre de la playlist
3. Pagina todos los tracks via `pp.paginate_playlist()` (maneja playlists grandes)
4. Extrae artista y título de cada track
5. Llama a `_resolve_and_print()` para búsqueda en YouTube

#### `_import_track(track_id)`

1. Usa `Public.song_info(track_id)` para obtener datos del track
2. Extrae nombre y primer artista de `trackUnion.firstArtist`
3. Busca en YouTube con query `"Artista - Track"`

#### `_import_episode(episode_id)`

1. Usa `spotapi.Podcast.get_episode()`
2. Obtiene nombre del podcast + episodio
3. Busca en YouTube

#### `_import_album(album_id)`

1. Usa `spotapi.PublicAlbum(album_id)`
2. Extrae todos los tracks del álbum
3. Busca cada uno en YouTube con barra de progreso

#### `_resolve_and_print(tracks, content_label)`

Para cada track `(artist, title)`:
1. Construye query `"Artist - Title"`
2. Ejecuta `search_youtube(query)` (yt-dlp ytsearch)
3. Muestra ✓ o ✗ con progreso numérico
4. Acumula resultados encontrados
5. Reporta tracks no encontrados al final

---

### 4.5 `core/cover.py` (116 líneas)

**Metadatos enriquecidos vía iTunes API** — Mejora la calidad de metadatos post-descarga.

#### `get_clean_metadata(info)`

Punto de entrada principal:
1. Limpia el título YouTube con `_clean_title()`
2. Consulta iTunes Search API
3. Si encuentra match → retorna datos reales de iTunes (track, artist, album) + carátula descargada
4. Si no → retorna datos limpios de YouTube sin carátula

#### `_clean_title(title, artist=None)`

Regex que remueve basura típica de títulos de YouTube:

| Patrón | Ejemplo |
|--------|---------|
| `(Official Video)` | "Song (Official Video)" → "Song" |
| `[4K]` / `[HD]` | "Song [4K]" → "Song" |
| `feat. Artist` | "Song feat. Artist" → "Song" |
| `ft. Artist` | "Song ft. Artist" → "Song" |
| `x Artist` / `× Artist` | "Song x Artist" → "Song" |
| `Artist - ` prefix | "Artist - Song" → "Song" (si coincide con uploader) |

#### `_search_itunes(artist, title)`

1. Construye URL de búsqueda: `https://itunes.apple.com/search?term={query}&limit=5&media=music&entity=song`
2. Intenta con `"Artist Title"`, fallback a solo `"Title"`
3. Toma el primer resultado
4. Escala artwork de 100×100 a 600×600
5. Retorna `{artist, track, album, art_url}`

#### `_download_cover(art_url, cache_key)`

- Cachea carátulas en `.cover_cache/` local
- Nombres archivo: `{artist}_{track}.jpg` (URL-encoded)
- No redescarga si ya existe en caché

---

### 4.6 `ui/interface.py` (226 líneas)

**Capa de presentación** — Toda la UI usa la librería **Rich** para renderizado en terminal.

| Función | Descripción | Elementos Rich usados |
|---------|-------------|----------------------|
| `clear()` | Limpia pantalla (compatible Termux) | — |
| `show_banner()` | Banner estilizado con nombre "T0RD0WNL04D" en binario + créditos | `Panel`, `Align` |
| `show_menu()` | Menú principal con 11 opciones + emojis | `Table` (box SIMPLE) |
| `show_info_panel(info)` | Info del video: título, canal, duración, fecha, vistas, likes | `Panel`, `Table.grid` |
| `show_formats_table()` | Tabla de formatos de audio disponibles | `Panel`, `Table` |
| `show_video_formats_table()` | Tabla de formatos de video | `Panel`, `Table` |
| `show_playlist_table()` | Lista de canciones con duración total | `Panel`, `Table` |
| `show_search_results()` | Resultados de búsqueda YouTube | `Panel`, `Table` |
| `show_urls_table()` | Lista de URLs a descargar | `Panel`, `Table` |
| `config_menu()` | Cambiar directorio de descargas | `Panel`, `Prompt.ask` |

**Paleta de colores:** Tema rojo/negro consistente (`bright_red`, `white`, `yellow`, `green`, `cyan`, `dim`).

---

### 4.7 `data/history.py` (45 líneas)

**Persistencia de historial de descargas** en archivo JSON.

- **Almacenamiento:** `.history.json` en la raíz del proyecto
- **Formato:** Array JSON, cada entrada con `{titulo, url, formato, fecha}`
- **Límite:** Máximo 50 entradas (FIFO)
- **Visualización:** Tabla Rich con últimas 15 descargas

```json
[
  {
    "titulo": "Calabria",
    "url": "https://www.youtube.com/watch?v=...",
    "formato": "M4A AAC",
    "fecha": "2026-07-14T12:30:00"
  }
]
```

---

### 4.8 `t0rd0wnl04d.py` (369 líneas)

**Orquestador principal / Entry point** — Loop principal del menú con 11 opciones.

#### Estructura del Loop

```
while True:
    show_banner()
    show_menu()
    choice = Prompt.ask()
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
    choice == "10" → Ajustes (config_menu())
    choice == "11" → Salir
```

#### Detalle por Opción

**1 — Spotify**
- Pide URL de Spotify
- Llama a `import_from_spotify()`
- Valida que haya resultados
- Muestra tabla con URLs encontradas
- Pide confirmación de descarga
- Pide formato de audio
- Ejecuta `download_batch()` con URLs resueltas

**2 — Buscar YouTube**
- Pide query de búsqueda
- Ejecuta `search_youtube()` con spinner de carga
- Muestra resultados numerados
- Soporta selección: número individual (`1`), rango (`1-3`), todos (`*`)
- Descarga simple (1 resultado) o batch (múltiples)

**3 — Una Canción (Audio)**
- Pide URL (detecta Spotify y redirige a opción 1)
- Muestra formatos disponibles
- Pide directorio personalizado (opcional)
- Ejecuta `download_single()`
- Si falla, ofrece reintentar con otro formato

**4 — Lista Audio**
- Pide URL de playlist
- Muestra formatos
- Pide directorio personalizado
- Pide límite de canciones
- Ejecuta `download_playlist()`

**5 — Varios Audios**
- Pide nombre de carpeta
- Loop de ingreso de URLs (termina con "y")
- Muestra formatos
- Ejecuta `download_batch()`

**6, 7, 8 — Video**
- Idéntico a 3, 4, 5 pero usando `core/video_downloader.py`

**9 — Registro**
- Muestra historial de descargas

**10 — Ajustes**
- Cambia directorio de descargas por defecto

**11 — Salir**
- Break del loop y mensaje de despedida

#### Manejo de Errores

- Solo `KeyboardInterrupt` capturado a nivel de `main()`
- Cada opción usa `continue` para volver al menú en lugar de excepciones
- Mensajes de error en rojo (`[red]`)

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
Usuario confirma descarga
  ↓ Elige formato (ej: M4A AAC)
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
_apply_metadata() → mutagen + iTunes cover
  ↓
history.save()
  ↓
Resumen: "✓ 1/1 DMNDS - Calabria"
```

---

## 6. Consideraciones Técnicas Clave

### 6.1 Sin OOP
Todo el código es procedural/funcional, sin clases definidas por el usuario (solo se usan objetos de librerías externas como `Console()`, `Panel()`, etc.). La UI se inyecta como módulo global `console = Console()`.

### 6.2 Subprocesos
yt-dlp se ejecuta como `subprocess.Popen` con:
- `stdout=subprocess.PIPE, stderr=subprocess.STDOUT` (mezcla stdout/stderr)
- `text=True, bufsize=1` (línea por línea)
- Parseo en tiempo real para actualizar barra de progreso

### 6.3 API de Spotify no-oficial
Usa `spotapi`, una librería que reverse-ingeniera la API GraphQL de Spotify (`api-partner.spotify.com/pathfinder/v1/query`). Esto es inherentemente frágil:
- Los hashes de consultas persistentes (`sha256Hash`) pueden cambiar
- La estructura de las respuestas puede cambiar (ej: `trackUnion.artists` → `trackUnion.firstArtist`)
- No hay garantía de disponibilidad

### 6.4 Metadatos híbridos YouTube + iTunes
Combina dos fuentes para metadatos de audio:
1. **YouTube** → uploader, título crudo, fecha de subida
2. **iTunes Search API** → artista real, nombre de álbum, carátula en alta resolución (600×600)

Esto produce tags de mejor calidad que usar solo los datos de YouTube.

### 6.5 Robustez
- Reintentos automáticos en descargas fallidas
- Timeouts en consultas a yt-dlp (30s singles, 60s playlists)
- Fallback para detección de archivos destino
- Sin embargo: **no hay tests automatizados**, no hay logging estructurado, y los `except Exception` genéricos pueden ocultar bugs

### 6.6 Target Termux
- Compatible con Android vía Termux
- Usa `clear` en vez de `cls`
- Barras de progreso adaptables a terminal angosta (40-60 columnas)
- Sin dependencias gráficas (solo terminal)

---

## 7. Posibles Mejoras / Deuda Técnica

| Área | Problema | Impacto |
|------|----------|---------|
| **Tests** | Zero test coverage (unit + integration) | Riesgo alto de regresiones |
| **Logging** | Usa `console.print()` en vez de módulo `logging` | No hay niveles, rotación, ni formato estructurado |
| **Manejo de errores** | `except Exception` genéricos en múltiples lugares | Oculta errores específicos |
| **Configuración** | Solo directorio de descarga. No persiste formato favorito, ni últimas URLs | Experiencia de usuario limitada |
| **Concurrencia** | Descargas secuenciales con delay de 0.5s | Lento para lotes grandes. Podría usar asyncio/threading |
| **Dependencia frágil** | `spotapi` no es oficial de Spotify | Cambios en API de Spotify rompen el flujo |
| **Type hints** | Mayoría del código sin anotaciones de tipo | Menos legible para mantenimiento, sin autocompletado IDE |
| **Internacionalización** | Solo español, textos hardcodeados | No scalable a otros idiomas |

---

## 8. Perfil para Creador de Contenido

Si un experto en programación quisiera crear contenido basado en este programa:

### Nichos Potenciales
- Herramientas prácticas para Android/Termux
- Descarga de contenido multimedia
- Automatización de tareas con Python

### Ángulos de Contenido
- Cómo construir un downloader de YouTube/Spotify desde cero
- Integración de APIs no-oficiales (Spotify reverse engineering)
- UI en terminal profesional con Rich
- Post-procesado de metadatos de audio con mutagen
- Manejo de subprocesos con pipes en tiempo real

### Stack a Destacar
```
Python 3.14  +  yt-dlp  +  Rich  +  mutagen  +  spotapi  +  ffmpeg
```

### Ideas para Videos/Tutoriales
1. "Cómo hacer un downloader de música para Termux en Python"
2. "Metadatos profesionales con mutagen + iTunes API"
3. "Construye tu propio spotdl con Python"
4. "Barras de progreso en terminal con Rich"
5. "Reverse engineering de APIs: Spotify GraphQL"
6. "De idea a app funcional: Arquitectura de un downloader"

---

## 9. Resumen de Archivos

| Archivo | Líneas | Propósito |
|---------|--------|-----------|
| `t0rd0wnl04d.py` | 369 | Entry point, menú principal, orquestación |
| `core/__init__.py` | 0 | Package marker |
| `core/downloader.py` | 387 | Motor de descarga de audio |
| `core/video_downloader.py` | 240 | Motor de descarga de video |
| `core/spotify.py` | 271 | Importación desde Spotify |
| `core/cover.py` | 116 | Metadatos iTunes + carátulas |
| `core/utils.py` | 122 | Utilidades, formatos, wrappers |
| `ui/__init__.py` | 0 | Package marker |
| `ui/interface.py` | 226 | Renderizado Rich (UI) |
| `data/__init__.py` | 0 | Package marker |
| `data/history.py` | 45 | Historial JSON |
| `requirements.txt` | ~5 | Dependencias PyPI |
| **Total** | **~1,400** | |
