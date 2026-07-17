import re
import os
import json
import hashlib
import shutil
import subprocess
import urllib.parse
from pathlib import Path

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.align import Align
from rich import box
from rich.progress import (
    Progress, TextColumn, BarColumn, SpinnerColumn, TimeElapsedColumn,
)
from rich.prompt import Confirm

from core.cover import _resolve_cover_url, _download_cover
from core.metadata_fixer import (
    _read_tags, _write_tags, _guess_artist_title, check_file_status,
    scan_for_browser, AUDIO_EXTENSIONS, detect_storage_roots,
    _pick_storage_root,
)
from ui.interface import show_section_header, prompt_ask

console = Console()

FORMATS = {
    "mp3":  {"codec": "libmp3lame", "ext": ".mp3",  "bitrates": {"Normal": "128k", "Alta": "192k", "Máxima": "320k"}, "default": "Alta"},
    "m4a":  {"codec": "aac",        "ext": ".m4a",  "bitrates": {"Normal": "128k", "Alta": "192k", "Máxima": "256k"}, "default": "Alta"},
    "opus": {"codec": "libopus",    "ext": ".opus", "bitrates": {"Normal": "96k",  "Alta": "128k", "Máxima": "160k"}, "default": "Alta"},
    "ogg":  {"codec": "libvorbis",  "ext": ".ogg",  "bitrates": {"Normal": "128k", "Alta": "192k", "Máxima": "256k"}, "default": "Alta"},
    "flac": {"codec": "flac",       "ext": ".flac", "bitrates": {}, "default": None},
}

FORMAT_NAMES = {
    "mp3": "MP3", "m4a": "AAC (M4A)", "opus": "Opus",
    "ogg": "OGG Vorbis", "flac": "FLAC",
}

# ── Common helpers ─────────────────────────────────────────────────────────────

def _clear():
    os.system("clear")
    print("\033[3J", end="")


def _browse_folder(title, default_path):
    """Interactive folder navigator.  User browses the filesystem and
    selects a folder.  Returns the selected Path, or None if cancelled."""
    roots = detect_storage_roots()
    start = Path(default_path).expanduser().resolve()

    if not start.is_dir():
        if roots:
            start = _pick_storage_root(roots)
        else:
            return None
    elif len(roots) > 1:
        _clear()
        show_section_header(title)
        console.print(f"  Ruta: [cyan]{start}[/cyan]")
        console.print(f"  [0] Usar esta   [1-{len(roots)}] Elegir otra raíz\n")
        choice = prompt_ask("  [bright_red]>[/bright_red]", default="0")
        try:
            n = int(choice)
            if 1 <= n <= len(roots):
                start = roots[n - 1][1]
        except ValueError:
            pass

    current = start

    while True:
        only_dirs = sorted(
            [d for d in current.iterdir() if d.is_dir()],
            key=lambda x: x.name.lower(),
        )

        _clear()
        show_section_header(title)
        console.print(f"  [dim]Ruta: {current}[/dim]\n")

        # Directory listing
        console.print("[bold yellow]CARPETAS:[/bold yellow]")
        tbl = Table(box=box.SIMPLE, show_header=False, padding=(0, 2))
        tbl.add_column("#", style="bright_red", width=4, justify="right")
        tbl.add_column("Carpeta", style="cyan")
        tbl.add_row("[1]", "📂 ..  (subir)")
        for i, d in enumerate(only_dirs, 2):
            tbl.add_row(f"[{i}]", f"📂 {d.name}")
        tbl.add_row()
        console.print(tbl)
        console.print()

        console.print("[bold]Acciones:[/bold]")
        console.print("  \\[s] Seleccionar esta carpeta")
        console.print("  \\[q] Cancelar")
        console.print()

        act = prompt_ask("  [bright_red]>[/bright_red]").strip().lower()

        if act == "s":
            return current

        if act == "q":
            return None

        if act == "b":
            if current.parent != current:
                current = current.parent
            continue

        if act.isdigit():
            n = int(act)
            if n == 1:
                if current.parent != current:
                    current = current.parent
            elif 2 <= n <= 1 + len(only_dirs):
                current = only_dirs[n - 2]


def _scan_recursive(folder):
    """Return flat list of all audio files under folder."""
    folder = Path(folder)
    files = []
    for ext in AUDIO_EXTENSIONS:
        files.extend(folder.rglob(f"*{ext}"))
    return sorted([f for f in files if f.is_file()], key=lambda x: x.name.lower())


def _count_by_ext(files):
    """Return {ext: count} for a list of files."""
    counts = {}
    for f in files:
        e = f.suffix.lower()
        counts[e] = counts.get(e, 0) + 1
    return counts


# ═══════════════════════════════════════════════════════════════════════════════
#  MENÚ PRINCIPAL
# ═══════════════════════════════════════════════════════════════════════════════

def tools_rk13_menu(download_dir):
    """Entry point for T00L5RK13 suite."""
    while True:
        _clear()
        show_section_header("🛠 T00L5RK13")
        console.print("  [dim]Suite de herramientas de audio profesional[/dim]\n")

        tbl = Table(box=box.SIMPLE, show_header=False, padding=(0, 2))
        tbl.add_column("#", style="bright_red", width=4, justify="right")
        tbl.add_column("Herramienta", style="white")
        tbl.add_row("[1]", "📁  Corregir Metadatos")
        tbl.add_row("[2]", "🔧  Convertir Formato de Audio")
        tbl.add_row("[3]", "🗂   Organizar / Deduplicar")
        tbl.add_row("[4]", "🔙  Volver")
        console.print(tbl)
        console.print()

        choice = prompt_ask("  [bright_red]>[/bright_red]", default="4").strip()

        if choice == "1":
            from core.metadata_fixer import interactive_browser
            interactive_browser(download_dir)
        elif choice == "2":
            _converter_menu(download_dir)
        elif choice == "3":
            _deduplicator_menu(download_dir)
        elif choice == "4":
            break

    _clear()


# ═══════════════════════════════════════════════════════════════════════════════
#  TOOL 2: CONVERTIDOR DE FORMATO
# ═══════════════════════════════════════════════════════════════════════════════

def _ffmpeg_available():
    return shutil.which("ffmpeg") is not None


def _convert_file(src, dst, codec, bitrate):
    """Run ffmpeg to convert src → dst. Return True on success."""
    cmd = ["ffmpeg", "-i", str(src), "-c:a", codec, "-vn", "-y"]
    if bitrate:
        cmd.extend(["-b:a", bitrate])
    cmd.append(str(dst))
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        return r.returncode == 0
    except Exception:
        return False


def _resolve_dest_folder(source, ext_key):
    """Determine destination folder, handling existing folders."""
    base = source.parent / f"{source.name}_{ext_key}"
    if not base.exists():
        return base
    console.print(f"[yellow]Ya existe: {base}[/yellow]")
    console.print("  [1] Sobrescribir (vaciar carpeta)")
    console.print("  [2] Crear con sufijo numérico")
    console.print("  [3] Cancelar")
    act = prompt_ask("  [bright_red]>[/bright_red]", default="3")
    if act == "1":
        shutil.rmtree(base)
        base.mkdir(parents=True)
        return base
    elif act == "2":
        for i in range(2, 100):
            alt = source.parent / f"{source.name}_{ext_key}_{i}"
            if not alt.exists():
                return alt
    return None


def _converter_menu(download_dir):
    if not _ffmpeg_available():
        console.print(
            "[red]ffmpeg no está instalado.[/red]\n"
            "  Instalalo con: [bold]pkg install ffmpeg[/bold]\n"
            "  o: [bold]apt install ffmpeg[/bold]"
        )
        console.input("\n[dim]Presiona Enter...[/dim]")
        return

    source = _browse_folder("🔧 CONVERTIR FORMATO", download_dir)
    if not source:
        return

    # Scan
    with console.status("[bold yellow]Escaneando archivos de audio...[/bold yellow]"):
        all_files = _scan_recursive(source)

    if not all_files:
        console.print("[red]No se encontraron archivos de audio[/red]")
        console.input("\n[dim]Presiona Enter...[/dim]")
        return

    # Summary
    counts = _count_by_ext(all_files)
    _clear()
    show_section_header("🔧 CONVERTIR FORMATO")
    console.print(f"  Origen: [cyan]{source}[/cyan]\n")

    tbl = Table(box=box.SIMPLE, show_header=False, padding=(0, 2))
    tbl.add_column("Formato", style="yellow")
    tbl.add_column("Cantidad", style="white")
    for ext in AUDIO_EXTENSIONS:
        n = counts.get(ext, 0)
        if n:
            tbl.add_row(f"  {ext.lstrip('.')}", str(n))
    tbl.add_row("", "")
    tbl.add_row("[bold]Total[/bold]", f"[bold]{len(all_files)}[/bold]")
    console.print(Panel(tbl, title="Archivos encontrados", border_style="bright_red"))
    console.print()

    # Choose target format
    console.print("[bold yellow]Seleccionar formato de destino:[/bold yellow]")
    fmt_tbl = Table(box=box.SIMPLE, show_header=False, padding=(0, 2))
    fmt_tbl.add_column("#", style="bright_red", width=4, justify="right")
    fmt_tbl.add_column("Formato", style="cyan")
    fmt_tbl.add_column("Codec", style="dim")
    keys = list(FORMATS.keys())
    for i, k in enumerate(keys, 1):
        fmt_tbl.add_row(f"[{i}]", FORMAT_NAMES[k], FORMATS[k]["codec"])
    console.print(fmt_tbl)
    console.print()

    c = prompt_ask("  [bright_red]Formato destino[/bright_red]", default="2")
    try:
        target = keys[int(c) - 1]
    except (ValueError, IndexError):
        return

    # Files to convert (excluding already in target format)
    target_ext = FORMATS[target]["ext"]
    to_convert = [f for f in all_files if f.suffix.lower() != target_ext]
    if not to_convert:
        console.print("[yellow]Todos los archivos ya están en el formato destino[/yellow]")
        console.input("\n[dim]Presiona Enter...[/dim]")
        return

    # Quality
    bitrate = None
    info = FORMATS[target]
    if info["bitrates"]:
        _clear()
        show_section_header("🔧 CALIDAD")
        console.print(f"  Formato: [cyan]{FORMAT_NAMES[target]}[/cyan]\n")
        qt = Table(box=box.SIMPLE, show_header=False, padding=(0, 2))
        qt.add_column("#", style="bright_red", width=4, justify="right")
        qt.add_column("Calidad", style="cyan")
        qt.add_column("Bitrate", style="dim")
        qkeys = list(info["bitrates"].keys())
        for i, k in enumerate(qkeys, 1):
            m = "  ◀ recomendado" if k == info["default"] else ""
            qt.add_row(f"[{i}]", k, f"{info['bitrates'][k]}{m}")
        console.print(qt)
        console.print()
        qc = prompt_ask("  [bright_red]Calidad[/bright_red]",
                        default=str(qkeys.index(info["default"]) + 1))
        try:
            bitrate = info["bitrates"][qkeys[int(qc) - 1]]
        except (ValueError, IndexError):
            bitrate = info["bitrates"][info["default"]]

    # Confirm
    dest = _resolve_dest_folder(source, target)
    if not dest:
        console.print("[yellow]Cancelado[/yellow]")
        return

    _clear()
    show_section_header("🔧 CONFIRMAR")

    ct = Table(box=box.SIMPLE, show_header=False, padding=(0, 2))
    ct.add_column("", style="yellow")
    ct.add_column("", style="white")
    ct.add_row("Origen:", str(source))
    ct.add_row("Archivos:", str(len(to_convert)))
    ct.add_row("Destino:", FORMAT_NAMES[target])
    ct.add_row("Calidad:", bitrate or "Lossless")
    ct.add_row("Carpeta:", str(dest))
    ct.add_row("Metadata:", "iTunes + carátula (automático)")
    console.print(Panel(ct, title="Resumen", border_style="bright_red"))
    console.print()

    if not Confirm.ask("  ¿Iniciar conversión?", default=True):
        return

    dest.mkdir(parents=True, exist_ok=True)
    converted = errors = skipped = 0

    with Progress(
        TextColumn("[progress.description]{task.description}"),
        BarColumn(bar_width=30),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("[cyan]Convirtiendo...", total=len(to_convert))

        for src in to_convert:
            rel = src.relative_to(source)
            dst = dest / rel.with_suffix(target_ext)
            dst.parent.mkdir(parents=True, exist_ok=True)

            progress.update(task, description=f"[cyan]{src.name[:42]}[/cyan]")

            if not _convert_file(src, dst, info["codec"], bitrate):
                errors += 1
                console.print(f"  [red]✗ Error: {src.name}[/red]")
                progress.advance(task)
                continue

            # Apply iTunes metadata + cover
            artist, title = _guess_artist_title(dst)
            if not title:
                skipped += 1
                console.print(f"  [dim]~ {dst.name}: convertido, no identificado[/dim]")
                progress.advance(task)
                continue

            meta = _resolve_cover_url(artist, title)
            if not meta:
                skipped += 1
                console.print(f"  [dim]~ {dst.name}: convertido, sin carátula[/dim]")
                progress.advance(task)
                continue

            cover_path = None
            if meta.get("art_url"):
                key = urllib.parse.quote(f"{meta['artist']}_{meta['track']}")
                cover_path = _download_cover(meta["art_url"], key)

            try:
                _write_tags(dst, meta["artist"], meta["track"],
                           meta.get("album", ""), cover_path)
                converted += 1
                label = f"{meta['artist']} - {meta['track']}"
                console.print(f"  [green]✓ {label[:55]}[/green]")
            except Exception as e:
                errors += 1
                console.print(f"  [red]✗ {dst.name}: {e}[/red]")

            progress.advance(task)

    progress.update(task, visible=False)

    # Results
    _clear()
    show_section_header("🔧 CONVERSIÓN COMPLETADA")

    rt = Table(box=box.SIMPLE, show_header=False, padding=(0, 2))
    rt.add_row("Completos:", f"[bold green]{converted}[/bold green]")
    if skipped:
        rt.add_row("Sin metadata:", f"[dim]{skipped}[/dim]")
    if errors:
        rt.add_row("Errores:", f"[red]{errors}[/red]")
    rt.add_row("Destino:", f"[cyan]{dest}[/cyan]")
    console.print(Panel(rt, title="Resultado", border_style="bright_red"))
    console.print()

    if converted and Confirm.ask("  ¿Eliminar carpeta original?", default=False):
        try:
            shutil.rmtree(source)
            console.print(f"[green]✓ Original eliminado: {source}[/green]")
        except Exception as e:
            console.print(f"[red]✗ {e}[/red]")

    console.input("\n[dim]Presiona Enter para continuar...[/dim]")


# ═══════════════════════════════════════════════════════════════════════════════
#  TOOL 3: ORGANIZADOR / DEDUPLICADOR
# ═══════════════════════════════════════════════════════════════════════════════

def _normalize_name(name):
    name = Path(name).stem.lower()
    name = re.sub(r'[^\w\s]', "", name)
    return re.sub(r'\s+', " ", name).strip()


def _get_hash(path):
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _get_bitrate(path):
    try:
        e = path.suffix.lower()
        if e == ".mp3":
            from mutagen.mp3 import MP3
            return MP3(str(path)).info.bitrate or -1
        if e == ".m4a":
            from mutagen.mp4 import MP4
            return MP4(str(path)).info.bitrate or -1
        if e in (".opus", ".ogg"):
            from mutagen.oggvorbis import OggVorbis
            return OggVorbis(str(path)).info.bitrate or -1
        if e == ".flac":
            from mutagen.flac import FLAC
            a = FLAC(str(path))
            return (a.info.sample_rate or 0) * (a.info.bits_per_sample or 0)
    except Exception:
        pass
    return -1


def _group_duplicates(files, method):
    """Group duplicate files. method: 'name' | 'metadata' | 'hash'."""
    groups = []
    seen = {}

    if method == "hash":
        with Progress(
            TextColumn("[progress.description]{task.description}"),
            BarColumn(bar_width=30),
            console=console,
        ) as p:
            t = p.add_task("[yellow]Calculando hashes...", total=len(files))
            for f in files:
                p.update(t, description=f"[yellow]{f.name[:40]}[/yellow]")
                h = _get_hash(f)
                seen.setdefault(h, []).append(f)
                p.advance(t)
    elif method == "metadata":
        for f in files:
            info = _read_tags(f)
            a = info.get("artist", "").strip().lower()
            t = info.get("title", "").strip().lower()
            if a and t:
                key = f"{a} ||| {t}"
            else:
                key = f"__name__ ||| {_normalize_name(f.name)}"
            seen.setdefault(key, []).append(f)
    else:
        for f in files:
            key = _normalize_name(f.name)
            seen.setdefault(key, []).append(f)

    for k, g in seen.items():
        if len(g) > 1:
            groups.append(g)
    return groups


def _show_dup_group(group, num):
    console.print(f"\n[bold yellow]Grupo {num}:[/bold yellow]")
    t = Table(box=box.SIMPLE, show_header=True, padding=(0, 1))
    t.add_column("#", style="dim", width=3)
    t.add_column("Archivo", style="white", width=36)
    t.add_column("Tamaño", style="cyan", width=9)
    t.add_column("Bitrate", style="green", width=9)

    for i, f in enumerate(group, 1):
        size = f.stat().st_size
        sz = f"{size/1024/1024:.1f}MB" if size > 1024**2 else f"{size/1024:.0f}KB"
        br = _get_bitrate(f)
        br_str = f"{br//1000}k" if br > 0 else "?"
        t.add_row(f"[{i}]", f.name[:34], sz, br_str)
    console.print(t)


def _deduplicator_menu(download_dir):
    source = _browse_folder("🗂  ORGANIZAR / DEDUPLICAR", download_dir)
    if not source:
        return

    with console.status("[bold yellow]Escaneando archivos...[/bold yellow]"):
        files = _scan_recursive(source)

    if not files:
        console.print("[yellow]No hay archivos de audio[/yellow]")
        console.input("\n[dim]Presiona Enter...[/dim]")
        return

    _clear()
    show_section_header("🗂  DETECCIÓN")
    console.print(f"  Archivos: [cyan]{len(files)}[/cyan]\n")

    mt = Table(box=box.SIMPLE, show_header=False, padding=(0, 2))
    mt.add_column("#", style="bright_red", width=4, justify="right")
    mt.add_column("Método", style="cyan")
    mt.add_column("Velocidad", style="green")
    mt.add_column("Precisión", style="yellow")
    mt.add_row("[1]", "Por nombre de archivo", "🔥 Rápida", "Media")
    mt.add_row("[2]", "Por metadata (artista + tema)", "⚡ Normal", "Alta")
    mt.add_row("[3]", "Por hash MD5 (contenido)", "🐢 Lenta", "Exacta")
    console.print(mt)
    console.print()

    m = prompt_ask("  [bright_red]Método[/bright_red]", default="2")
    method_map = {"1": "name", "2": "metadata", "3": "hash"}
    method = method_map.get(m, "metadata")

    with console.status("[bold yellow]Buscando duplicados...[/bold yellow]"):
        groups = _group_duplicates(files, method)

    if not groups:
        console.print("[green]✓ No se encontraron duplicados[/green]")
        console.input("\n[dim]Presiona Enter...[/dim]")
        return

    _clear()
    show_section_header("🗂  DUPLICADOS")
    console.print(f"  [red]{len(groups)} grupo(s) de duplicados[/red]\n")

    for i, g in enumerate(groups, 1):
        _show_dup_group(g, i)

    console.print()
    console.print("[bold yellow]Acción:[/bold yellow]")
    console.print("  [a] Conservar el de mejor calidad (bitrate más alto)")
    console.print("  [b] Conservar el más pequeño (ahorrar espacio)")
    console.print("  [c] Conservar formato específico (ej: m4a)")
    console.print("  [d] Elegir manualmente cada grupo")
    console.print("  [x] Salir sin cambios")
    console.print()

    act = prompt_ask("  [bright_red]>[/bright_red]", default="x").strip().lower()
    if act == "x":
        return

    removed = kept = 0

    if act == "a":
        for g in groups:
            best = max(g, key=lambda x: _get_bitrate(x))
            kept += 1
            for f in g:
                if f != best:
                    f.unlink(missing_ok=True)
                    removed += 1

    elif act == "b":
        for g in groups:
            smallest = min(g, key=lambda x: x.stat().st_size)
            kept += 1
            for f in g:
                if f != smallest:
                    f.unlink(missing_ok=True)
                    removed += 1

    elif act == "c":
        fmt = prompt_ask("  Conservar formato", default="m4a").strip().lower()
        ext = f".{fmt}" if not fmt.startswith(".") else fmt
        for g in groups:
            match = [f for f in g if f.suffix.lower() == ext]
            if match:
                keep = match[0]
                kept += 1
                for f in g:
                    if f != keep:
                        f.unlink(missing_ok=True)
                        removed += 1
            else:
                console.print(f"  [dim]Sin .{fmt} en grupo, se conservan todos[/dim]")

    elif act == "d":
        for g in groups:
            idx = prompt_ask(f"  Conservar # (1-{len(g)})", default="1")
            try:
                keep = g[int(idx) - 1]
                kept += 1
                for f in g:
                    if f != keep:
                        f.unlink(missing_ok=True)
                        removed += 1
            except (ValueError, IndexError):
                pass

    console.print()
    console.print(f"[green]✓ {kept} conservado(s), {removed} eliminado(s)[/green]")
    console.input("\n[dim]Presiona Enter para continuar...[/dim]")
