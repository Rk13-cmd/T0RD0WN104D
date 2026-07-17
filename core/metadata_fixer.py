import re
import base64
import urllib.parse
from pathlib import Path

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.align import Align
from rich import box
from rich.progress import Progress, TextColumn, BarColumn
from rich.prompt import Prompt, Confirm

from core.cover import _resolve_cover_url, _download_cover, CACHE_DIR
from ui.interface import show_section_header

console = Console()

AUDIO_EXTENSIONS = (".mp3", ".m4a", ".opus", ".ogg", ".flac")

# ── Almacenamiento ──────────────────────────────────────────────────────────────

def _read_mount_table():
    """Read /proc/self/mounts or fallback to `mount` command."""
    import subprocess
    try:
        return Path("/proc/self/mounts").read_text()
    except Exception:
        try:
            return subprocess.check_output(
                ["mount"], text=True, stderr=subprocess.DEVNULL, timeout=3
            )
        except Exception:
            return ""


def detect_storage_roots():
    """Return list of (label, Path) for accessible storage roots."""
    candidates = []
    seen = set()

    def add(label, path):
        p = Path(path)
        try:
            real = p.resolve()
        except Exception:
            real = p
        if str(real) in seen:
            return
        seen.add(str(real))
        if p.is_dir():
            candidates.append((label, p))

    add("Almacenamiento interno", "/sdcard")

    # Mount table for SD (if reachable)
    for line in _read_mount_table().splitlines():
        parts = line.split()
        if len(parts) < 3:
            continue
        mnt = parts[2]
        if any(p in mnt for p in ("/emulated", "/self", "/sdcard", "/primary", "Android")):
            continue
        if re.search(r'[0-9A-Fa-f]{4}[-:][0-9A-Fa-f]{4}', mnt) or "/media_rw" in mnt:
            add("Tarjeta SD", mnt)

    # Common Termux symlinks
    TERMUX_SYMLINKS = {"music": "Música", "downloads": "Descargas"}
    storage_dir = Path("/data/data/com.termux/files/home/storage")
    if storage_dir.is_dir():
        for child in sorted(storage_dir.iterdir()):
            if child.name in TERMUX_SYMLINKS:
                add(TERMUX_SYMLINKS[child.name], child)

    return candidates


def show_storage_bar():
    """Print a one-line summary of detected storage roots."""
    from rich.text import Text
    roots = detect_storage_roots()
    parts = []
    for label, path in roots:
        parts.append(f"[cyan]{label}[/cyan] ([dim]{path}[/dim])")
    if parts:
        console.print("  💽  " + "  |  ".join(parts))
    console.print()


def _pick_storage_root(roots):
    """Let user pick a storage root from list. Returns chosen Path."""
    if not roots:
        return Path.cwd()

    from ui.interface import clear
    clear()
    console.print("[bold yellow]Seleccionar almacenamiento:[/bold yellow]\n")

    tbl = Table(box=box.SIMPLE, show_header=False, padding=(0, 2))
    tbl.add_column("#", style="bright_red", width=4, justify="right")
    tbl.add_column("Almacenamiento", style="cyan")
    for i, (label, path) in enumerate(roots, 1):
        tbl.add_row(f"[{i}]", f"{label}  [dim]{path}[/dim]")
    console.print(tbl)

    choice = Prompt.ask("\n  [bright_red]>[/bright_red]", default="1")
    try:
        idx = int(choice) - 1
        if 0 <= idx < len(roots):
            return roots[idx][1]
    except ValueError:
        pass
    return roots[0][1]


def _read_tags(filepath):
    """Read artist, title, album, has_cover from any audio format."""
    ext = filepath.suffix.lower()
    info = {"artist": "", "title": "", "album": "", "has_cover": False}

    try:
        if ext == ".mp3":
            from mutagen.mp3 import MP3
            from mutagen.id3 import ID3
            audio = MP3(str(filepath))
            if audio.tags:
                info["artist"] = str(audio.tags.get("TPE1", [""])[0])
                info["title"] = str(audio.tags.get("TIT2", [""])[0])
                info["album"] = str(audio.tags.get("TALB", [""])[0])
                info["has_cover"] = "APIC" in audio.tags

        elif ext == ".m4a":
            from mutagen.mp4 import MP4
            audio = MP4(str(filepath))
            info["artist"] = audio.get("\xa9ART", [""])[0]
            info["title"] = audio.get("\xa9nam", [""])[0]
            info["album"] = audio.get("\xa9alb", [""])[0]
            info["has_cover"] = bool(audio.get("covr"))

        elif ext in (".opus", ".ogg"):
            try:
                from mutagen.oggopus import OggOpus
                audio = OggOpus(str(filepath))
            except Exception:
                from mutagen.oggvorbis import OggVorbis
                audio = OggVorbis(str(filepath))
            info["artist"] = audio.get("artist", [""])[0]
            info["title"] = audio.get("title", [""])[0]
            info["album"] = audio.get("album", [""])[0]
            info["has_cover"] = bool(audio.get("metadata_block_picture"))

        elif ext == ".flac":
            from mutagen.flac import FLAC
            audio = FLAC(str(filepath))
            info["artist"] = audio.get("artist", [""])[0]
            info["title"] = audio.get("title", [""])[0]
            info["album"] = audio.get("album", [""])[0]
            info["has_cover"] = bool(audio.pictures)

    except Exception:
        pass

    info["artist"] = info["artist"].strip()
    info["title"] = info["title"].strip()
    info["album"] = info["album"].strip()
    return info


def _write_tags(filepath, artist, title, album, cover_path=None):
    """Write metadata + optional cover to any audio format."""
    ext = filepath.suffix.lower()

    if ext == ".mp3":
        from mutagen.mp3 import MP3
        from mutagen.id3 import ID3, APIC, TPE1, TALB, TIT2
        audio = MP3(str(filepath))
        if audio.tags is None:
            audio.tags = ID3()
        audio.tags["TIT2"] = TIT2(encoding=3, text=title)
        audio.tags["TPE1"] = TPE1(encoding=3, text=artist)
        audio.tags["TALB"] = TALB(encoding=3, text=album)
        if cover_path:
            with open(cover_path, "rb") as f:
                audio.tags.delall("APIC")
                audio.tags.add(APIC(encoding=3, mime="image/jpeg", type=3, desc="Cover", data=f.read()))
        audio.save()

    elif ext == ".m4a":
        from mutagen.mp4 import MP4, MP4Cover
        audio = MP4(str(filepath))
        audio["\xa9nam"] = title
        audio["\xa9ART"] = artist
        audio["\xa9alb"] = album
        if cover_path:
            with open(cover_path, "rb") as f:
                audio["covr"] = [MP4Cover(f.read(), MP4Cover.FORMAT_JPEG)]
        audio.save()

    elif ext in (".opus", ".ogg"):
        try:
            from mutagen.oggopus import OggOpus
            audio = OggOpus(str(filepath))
        except Exception:
            from mutagen.oggvorbis import OggVorbis
            audio = OggVorbis(str(filepath))
        audio["artist"] = artist
        audio["title"] = title
        audio["album"] = album
        if cover_path:
            from mutagen.flac import Picture
            pic = Picture()
            pic.data = open(cover_path, "rb").read()
            pic.type = 3
            pic.mime = "image/jpeg"
            pic.width = 0
            pic.height = 0
            pic.depth = 0
            pic.colors = 0
            audio["metadata_block_picture"] = [base64.b64encode(pic.write()).decode()]
        audio.save()

    elif ext == ".flac":
        from mutagen.flac import FLAC, Picture
        audio = FLAC(str(filepath))
        audio["artist"] = artist
        audio["title"] = title
        audio["album"] = album
        if cover_path:
            pic = Picture()
            pic.data = open(cover_path, "rb").read()
            pic.type = 3
            pic.mime = "image/jpeg"
            pic.width = 0
            pic.height = 0
            pic.depth = 0
            pic.colors = 0
            audio.add_picture(pic)
        audio.save()


def _guess_artist_title(filepath):
    """Try to read existing tags; fallback to filename parsing."""
    info = _read_tags(filepath)
    if info["artist"] and info["title"]:
        return info["artist"], info["title"]

    name = filepath.stem
    m = re.match(r'^(.+?)\s*[-–]\s*(.+)$', name)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    return "", name.strip()


def _apply_metadata_fix(filepath, meta):
    """Apply corrected metadata + cover to a single file."""
    ext = filepath.suffix.lower()
    track = meta["track"]
    artist = meta["artist"]
    album = meta.get("album", "")
    art_url = meta.get("art_url", "")
    cover_path = None
    if art_url:
        cache_key = urllib.parse.quote(f"{artist}_{track}")
        cover_path = _download_cover(art_url, cache_key)
    _write_tags(filepath, artist, track, album, cover_path)


def check_file_status(filepath):
    """Return dict with full status of an audio file.
    
    Returns: {artist, title, album, has_cover, ext, filepath}
    """
    info = _read_tags(filepath)
    info["ext"] = filepath.suffix.lower().lstrip(".")
    info["filepath"] = filepath
    if not info["artist"] or not info["title"]:
        artist, title = _guess_artist_title(filepath)
        info["artist"] = artist
        info["title"] = title
    return info


def scan_for_browser(folder_path):
    """Scan folder and return (dirs, files_with_status).
    
    dirs: sorted list of subdirectory Paths
    files_with_status: list of dicts from check_file_status
    """
    folder = Path(folder_path).expanduser().resolve()
    dirs = sorted([d for d in folder.iterdir() if d.is_dir()])
    files = []
    for f in folder.iterdir():
        if f.is_file() and f.suffix.lower() in AUDIO_EXTENSIONS:
            files.append(check_file_status(f))
    files.sort(key=lambda x: x["filepath"].name.lower())
    return dirs, files


def _show_file_detail_panel(status):
    """Display a Rich panel with detailed file info."""
    artist = status.get("artist") or "[dim]sin tags[/dim]"
    title = status.get("title") or "[dim]sin tags[/dim]"
    album = status.get("album") or "[dim]sin album[/dim]"
    cover = "[green]✓ tiene portada[/green]" if status.get("has_cover") else "[red]✗ sin portada[/red]"

    grid = Table.grid(padding=(0, 1))
    grid.add_column(style="bold yellow", justify="right")
    grid.add_column(style="white")
    grid.add_row("Archivo:", status["filepath"].name)
    grid.add_row("Artista:", artist)
    grid.add_row("Título:", title)
    grid.add_row("Álbum:", album)
    grid.add_row("Portada:", cover)
    grid.add_row("Formato:", status["ext"].upper())

    console.print(Panel(
        Align.center(grid),
        title=f"[bold white]Información del archivo[/bold white]",
        border_style="bright_red",
        box=box.ROUNDED,
    ))


def _fix_single_file(filepath):
    """Fix a single audio file: metadata + cover via iTunes."""
    artist, title = _guess_artist_title(filepath)
    if not title:
        return False, "no se pudo identificar la canción"

    result = _resolve_cover_url(artist, title)
    if not result:
        return False, "sin carátula disponible"

    try:
        _apply_metadata_fix(filepath, result)
        return True, f"{result['artist']} - {result['track']}"
    except Exception as e:
        return False, str(e)


def _recover_single(filepath):
    """Re-download and apply cover only for a single file (keeps existing text metadata)."""
    artist, title = _guess_artist_title(filepath)
    if not title:
        return False, "no se pudo identificar la canción"

    result = _resolve_cover_url(artist, title)
    if not result or not result.get("art_url"):
        return False, "sin portada disponible"

    try:
        cache_key = urllib.parse.quote(f"{result['artist']}_{result['track']}")
        cover_path = _download_cover(result["art_url"], cache_key)
        if not cover_path:
            return False, "no se pudo descargar la portada"

        info = _read_tags(filepath)
        _write_tags(
            filepath,
            info["artist"] or result["artist"],
            info["title"] or result["track"],
            info["album"] or result.get("album", ""),
            cover_path,
        )
        return True, f"portada actualizada: {result['artist']} - {result['track']}"
    except Exception as e:
        return False, str(e)


def _show_file_menu(filepath):
    """Interactive sub-menu for a single audio file."""
    while True:
        clear = __import__("ui.interface", fromlist=["clear"]).clear
        clear()
        status = check_file_status(filepath)
        _show_file_detail_panel(status)
        console.print()
        console.print("[bold yellow]Acciones disponibles:[/bold yellow]")
        console.print("  [1] 🔄 Corregir metadata + portada")
        console.print("  [2] 🖼  Re-descargar solo portada")
        console.print("  [3] 🔙 Volver")
        console.print()
        act = Prompt.ask("  [bright_red]>[/bright_red]", default="3")
        if act == "1":
            ok, msg = _fix_single_file(filepath)
            if ok:
                console.print(f"  [green]✓ {msg}[/green]")
            else:
                console.print(f"  [red]✗ {msg}[/red]")
            console.input("\n[dim]Presiona Enter...[/dim]")
        elif act == "2":
            ok, msg = _recover_single(filepath)
            if ok:
                console.print(f"  [green]✓ {msg}[/green]")
            else:
                console.print(f"  [red]✗ {msg}[/red]")
            console.input("\n[dim]Presiona Enter...[/dim]")
        elif act == "3":
            break


def interactive_browser(start_path):
    """Navegador de carpetas interactivo para corregir metadatos y portadas."""
    from ui.interface import clear

    roots = detect_storage_roots()
    start = Path(start_path).expanduser().resolve()

    if not start.is_dir():
        if roots:
            start = _pick_storage_root(roots)
        else:
            console.print(f"[red]Ruta invalida: {start_path}[/red]")
            console.input("\n[dim]Presiona Enter...[/dim]")
            return

    if len(roots) > 1:
        clear()
        show_section_header("📁 CORREGIR METADATOS")
        console.print(f"  Ruta: [cyan]{start}[/cyan]")
        console.print(f"  [0] Usar esta   [1-{len(roots)}] Elegir otra raíz\n")
        choice = Prompt.ask("  [bright_red]>[/bright_red]", default="0")
        try:
            n = int(choice)
            if 1 <= n <= len(roots):
                start = roots[n - 1][1]
        except ValueError:
            pass
        clear()
        show_section_header("📁 CORREGIR METADATOS")
        show_storage_bar()
    else:
        clear()
        show_section_header("📁 CORREGIR METADATOS")

    current = start

    while True:
        dirs, files = scan_for_browser(current)

        from ui.interface import clear
        clear()
        show_section_header(f"📁 CORREGIR METADATOS")
        console.print(f"  [dim]Ruta: {current}[/dim]\n")

        # ── Folders ─────────────────────────────────────────────────────────────────
        nav_start = 1  # .
        nav_prev  = 2  # ..
        nav_dir_start = 3  # first subdir

        console.print("[bold yellow]CARPETAS:[/bold yellow]")
        ftable = Table(box=box.SIMPLE, show_header=False, padding=(0, 2))
        ftable.add_column("#", style="bright_red", width=4, justify="right")
        ftable.add_column("Carpeta", style="cyan")
        ftable.add_row("[1]", "📂 .  (esta carpeta)")
        ftable.add_row("[2]", "📂 .. (atrás)")
        for i, d in enumerate(dirs, nav_dir_start):
            ftable.add_row(f"[{i}]", f"📂 {d.name}")
        ftable.add_row()
        console.print(ftable)
        console.print()

        nav_dir_end = nav_dir_start + len(dirs) - 1 if dirs else nav_dir_start - 1
        file_start = nav_dir_end + 1

        # ── Files ───────────────────────────────────────────────────────────────────
        console.print("[bold yellow]ARCHIVOS:[/bold yellow]")
        if files:
            ftbl = Table(box=box.SIMPLE, show_header=True, padding=(0, 1))
            ftbl.add_column("#", style="dim", width=4)
            ftbl.add_column("Archivo", style="white", width=35)
            ftbl.add_column("Artista", style="cyan", width=20)
            ftbl.add_column("Portada", style="yellow", width=10)

            for i, info in enumerate(files, file_start):
                artist = info["artist"][:18] if info["artist"] else "[dim]?[/dim]"
                cover = "[green]✓[/green]" if info["has_cover"] else "[red]✗[/red]"
                ftbl.add_row(f"[{i}]", info["filepath"].name[:33], artist, cover)
            console.print(ftbl)
        else:
            console.print("  [dim](sin archivos de audio)[/dim]")
        console.print()

        file_end = file_start + len(files) - 1 if files else file_start - 1

        # ── Actions ─────────────────────────────────────────────────────────────────
        console.print("[bold]Acciones:[/bold]")
        console.print("  \\[f] Fix toda la carpeta    \\[i] Fix archivo individual")
        console.print("  \\[b] Atrás                  \\[q] Salir")
        console.print()

        act = Prompt.ask("  [bright_red]>[/bright_red]").strip().lower()

        if act == "q":
            break
        elif act == "b":
            if current.parent != current:
                current = current.parent
        elif act == "f":
            clear()
            fix_folder(current)
            console.input("\n[dim]Presiona Enter para continuar...[/dim]")
        elif act == "i":
            idx_str = Prompt.ask("  Número del archivo")
            try:
                idx = int(idx_str) - file_start
                if 0 <= idx < len(files):
                    _show_file_menu(files[idx]["filepath"])
                else:
                    console.print("[red]Número fuera de rango[/red]")
                    console.input("\n[dim]Presiona Enter...[/dim]")
            except ValueError:
                console.print("[red]Número inválido[/red]")
                console.input("\n[dim]Presiona Enter...[/dim]")
        elif act.isdigit():
            n = int(act)
            if n == nav_start:
                pass
            elif n == nav_prev:
                if current.parent != current:
                    current = current.parent
            elif nav_dir_start <= n <= nav_dir_end:
                current = dirs[n - nav_dir_start]
            elif file_start <= n <= file_end:
                idx = n - file_start
                if 0 <= idx < len(files):
                    _show_file_menu(files[idx]["filepath"])


def fix_folder(folder_path, recursive=False):
    """Scan folder for audio files and fix metadata + cover via iTunes.
    
    Args:
        folder_path: str or Path to the folder containing audio files
        recursive: if True, scan subdirectories too
    """
    folder = Path(folder_path).expanduser().resolve()
    if not folder.is_dir():
        console.print(f"[red]Carpeta no encontrada: {folder_path}[/red]")
        return

    pattern = "**/*" if recursive else "*"
    files = []
    for ext in AUDIO_EXTENSIONS:
        files.extend(folder.glob(f"{pattern}{ext}"))
    if recursive:
        files = [f for f in files if f.is_file()]
    else:
        files = [f for f in files if f.parent == folder]

    if not files:
        console.print("[yellow]No se encontraron archivos de audio en la carpeta[/yellow]")
        return

    console.print(f"[cyan]Escaneando {len(files)} archivo(s)...[/cyan]\n")

    fixed = 0
    skipped = 0
    errors_count = 0

    with Progress(
        TextColumn("[progress.description]{task.description}"),
        BarColumn(bar_width=30),
        console=console,
    ) as progress:
        task = progress.add_task("[cyan]Corrigiendo...", total=len(files))

        for filepath in files:
            progress.update(task, description=f"[cyan]{filepath.name[:45]}[/cyan]")

            artist, title = _guess_artist_title(filepath)
            if not title:
                errors_count += 1
                console.print(f"  [red]✗ {filepath.name}: no se pudo identificar la cancion[/red]")
                progress.advance(task)
                continue

            result = _resolve_cover_url(artist, title)
            if not result:
                skipped += 1
                console.print(f"  [dim]~ {filepath.name}: sin carátula disponible[/dim]")
                progress.advance(task)
                continue

            try:
                _apply_metadata_fix(filepath, result)
                fixed += 1
                label = f"{result['artist']} - {result['track']}"
                console.print(f"  [green]\u2713 {label[:55]}[/green]")
            except Exception as e:
                errors_count += 1
                console.print(f"  [red]✗ {filepath.name}: {e}[/red]")

            progress.advance(task)

    progress.update(task, visible=False)
    console.print()
    summary = []
    if fixed:
        summary.append(f"[bold green]{fixed} corregido(s)[/bold green]")
    if skipped:
        summary.append(f"[dim]{skipped} sin cambios[/dim]")
    if errors_count:
        summary.append(f"[red]{errors_count} error(es)[/red]")
    if summary:
        console.print("  ".join(summary))
    else:
        console.print("[yellow]Sin resultados[/yellow]")
