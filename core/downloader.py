import os
import re
import time
import subprocess
from pathlib import Path
from datetime import datetime

from rich.console import Console
from rich.align import Align
from rich.progress import Progress, BarColumn, TextColumn, DownloadColumn, TransferSpeedColumn, TimeRemainingColumn

from core.utils import get_ytdlp_path, FORMATS, extract_info, extract_playlist_info
from core.cover import get_clean_metadata
from ui.interface import show_info_panel
from data import history

console = Console()
BASE_DIR = Path(__file__).parent.parent
DOWNLOAD_DIR = BASE_DIR / "downloads"


def _build_cmd(ytdlp, fmt, template, url):
    if fmt["ext"] == "mp4":
        return [ytdlp, "--no-warnings", "--newline",
                "-f", "bestvideo+bestaudio/best",
                "--merge-output-format", "mp4",
                "-o", template, url]
    audio_q = fmt["bitrate"] if fmt["bitrate"] else "0"
    return [ytdlp, "--no-warnings", "--newline",
            "-f", "bestaudio/best",
            "--extract-audio", "--audio-format", fmt["ext"],
            "--audio-quality", audio_q,
            "--embed-thumbnail",
            "--embed-metadata",
            "--parse-metadata", "%(uploader)s:artist",
            "--parse-metadata", "%(playlist_title|YouTube Audio)s:album",
            "--parse-metadata", "%(upload_date>%Y-%m-%d)s:date",
            "-o", template, url]


def _apply_metadata(filepath, info, ext):
    if ext not in ("mp3", "m4a"):
        return

    clean_title, clean_artist, clean_album, cover_path = get_clean_metadata(info)

    from mutagen.mp4 import MP4, MP4Cover
    from mutagen.mp3 import MP3
    from mutagen.id3 import ID3, APIC, TPE1, TALB, TIT2, TDRC

    try:
        if ext == "m4a":
            audio = MP4(str(filepath))
            audio["\xa9nam"] = clean_title
            audio["\xa9ART"] = clean_artist
            audio["\xa9alb"] = clean_album
            if cover_path:
                with open(cover_path, "rb") as f:
                    audio["covr"] = [MP4Cover(f.read(), MP4Cover.FORMAT_JPEG)]
            audio.save()

        elif ext == "mp3":
            audio = MP3(str(filepath))
            if audio.tags is None:
                audio.tags = ID3()
            audio.tags["TIT2"] = TIT2(encoding=3, text=clean_title)
            audio.tags["TPE1"] = TPE1(encoding=3, text=clean_artist)
            audio.tags["TALB"] = TALB(encoding=3, text=clean_album)
            if cover_path:
                with open(cover_path, "rb") as f:
                    audio.tags.delall("APIC")
                    audio.tags.add(APIC(encoding=3, mime="image/jpeg", type=3, desc="Cover", data=f.read()))
            audio.save()

        if not cover_path:
            console.print(f"[green]  ✓ Metadatos limpiados: {clean_artist} - {clean_title}[/green]")
    except Exception as e:
        console.print(f"[yellow]  ⚠ No se pudieron aplicar metadatos: {e}[/yellow]")


def _run_ytdlp(cmd, prefix=""):
    """Execute yt-dlp and stream output to a progress bar.
    Returns (returncode, filepath_or_None, error_messages).
    Detects the output filepath from yt-dlp's own output lines."""
    error_msgs = []
    filepath = None

    with Progress(
        TextColumn("[cyan]{task.description}"),
        BarColumn(bar_width=30),
        DownloadColumn(),
        TransferSpeedColumn(),
        TimeRemainingColumn(),
        console=console,
    ) as progress:
        task = progress.add_task(f"[bold white]{prefix}Descargando...", total=100)
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)

        for line in process.stdout or []:
            line = line.strip()
            if not line:
                continue

            if "ERROR" in line:
                error_msgs.append(line)
            elif "WARNING" in line:
                error_msgs.append(line)

            if "[download]" in line:
                m = re.search(r'(\d+\.?\d*)%', line)
                if m:
                    pct = min(float(m.group(1)), 100)
                    progress.update(task, completed=pct, description=f"[bold bright_red]{prefix}Descargando...")
                dest_m = re.search(r'Destination:\s*(.+)', line)
                if dest_m:
                    filepath = Path(dest_m.group(1).strip())
            elif "[ExtractAudio]" in line:
                progress.update(task, description=f"[dim white]{prefix}Extrayendo audio...")
                dest_m = re.search(r'Destination:\s*(.+)', line)
                if dest_m:
                    filepath = Path(dest_m.group(1).strip())
            elif "[Metadata]" in line:
                progress.update(task, description=f"[dim white]{prefix}Imagen y metadata incorporada...")
            elif "[EmbedThumbnail]" in line:
                progress.update(task, description=f"[dim white]{prefix}Imagen y metadata incorporada...")
            elif "[Merger]" in line:
                dest_m = re.search(r'into\s+"(.+)"', line)
                if dest_m:
                    filepath = Path(dest_m.group(1).strip())

        process.wait()

    return process.returncode, filepath, error_msgs


def _attempt_download(cmd, out_dir, ext, before_files=None):
    """Run _run_ytdlp and locate the output file.
    Returns (success, filepath, error_messages)."""
    retcode, filepath, error_msgs = _run_ytdlp(cmd)

    if retcode == 0 and filepath and filepath.exists():
        return True, filepath, error_msgs

    if before_files is None:
        before_files = set()

    # Fallback: find by extension (only new files)
    files = set(out_dir.glob(f"*.{ext}")) - before_files
    if files:
        return True, max(files, key=os.path.getctime), error_msgs

    # Fallback: any new file
    files = set(out_dir.glob("*")) - before_files
    if files:
        return True, max(files, key=os.path.getctime), error_msgs

    return False, None, error_msgs


def single(url, fmt_key, output_dir=None):
    fmt = FORMATS.get(fmt_key)
    if not fmt:
        console.print("[red]Formato invalido[/red]")
        return False

    out_dir = Path(output_dir) if output_dir else DOWNLOAD_DIR
    out_dir.mkdir(exist_ok=True)

    info = extract_info(url)
    if info:
        show_info_panel(info)
    else:
        console.print("[yellow]Obteniendo informacion...[/yellow]")

    ytdlp = get_ytdlp_path()
    template = str(out_dir / "%(title)s.%(ext)s")
    cmd = _build_cmd(ytdlp, fmt, template, url)

    prefix = ""
    before = set(out_dir.iterdir()) if out_dir.exists() else set()
    ok, filepath, error_msgs = _attempt_download(cmd, out_dir, fmt["ext"], before)

    if not ok:
        for err in error_msgs:
            console.print(f"[red]  {err}[/red]")
        console.print("[yellow]  [!] Reintentando (mismo formato)...[/yellow]")
        time.sleep(1)
        ok, filepath, error_msgs = _attempt_download(cmd, out_dir, fmt["ext"], before)

        if not ok:
            for err in error_msgs:
                console.print(f"[red]  {err}[/red]")
            console.print("\n[bold red]✗ Error durante la descarga[/bold red]")
            return False

    console.print(f"\n[bold green]✓ Guardado:[/bold green] {filepath.name}")

    _apply_metadata(filepath, info or {}, fmt["ext"])

    if info:
        history.save({
            "titulo": info.get("title", "?"),
            "url": url,
            "formato": fmt["name"],
            "fecha": datetime.now().isoformat(),
        })
    return True


def _download_track(url, fmt, out_dir, index, total):
    ytdlp = get_ytdlp_path()
    template = str(out_dir / "%(title)s.%(ext)s")
    cmd = _build_cmd(ytdlp, fmt, template, url)

    prefix = f"[{index}/{total}] "
    before = set(out_dir.iterdir()) if out_dir.exists() else set()
    ok, filepath, error_msgs = _attempt_download(cmd, out_dir, fmt["ext"], before)

    if not ok:
        for err in error_msgs:
            console.print(f"[red]  {err}[/red]")
        console.print(f"[yellow]  [!] Reintentando [{index}/{total}]...[/yellow]")
        time.sleep(1)
        ok, filepath, error_msgs = _attempt_download(cmd, out_dir, fmt["ext"], before)

        if not ok:
            for err in error_msgs:
                console.print(f"[red]  {err}[/red]")
            return False, None

    return True, filepath


def playlist(url, fmt_key, limit=None, output_dir=None):
    from rich.table import Table
    from rich.panel import Panel
    from rich import box
    from ui.interface import show_playlist_table

    fmt = FORMATS.get(fmt_key)
    if not fmt:
        console.print("[red]Formato invalido[/red]")
        return

    out_dir = Path(output_dir) if output_dir else DOWNLOAD_DIR
    out_dir.mkdir(exist_ok=True)

    with console.status("[bold yellow]Obteniendo informacion de la playlist...[/bold yellow]"):
        playlist_title, entries = extract_playlist_info(url, limit)

    if not entries:
        console.print("[red]No se pudieron obtener los videos de la playlist[/red]")
        return

    playlist_dir = out_dir / (playlist_title or "Playlist")
    playlist_dir.mkdir(exist_ok=True)

    show_playlist_table(playlist_title or "Playlist", entries)

    from rich.prompt import Confirm
    if not Confirm.ask(f"\n  Descargar [cyan]{len(entries)}[/cyan] canciones?"):
        console.print("[yellow]Cancelado[/yellow]")
        return

    successful = 0
    failed = 0
    results = []

    for i, entry in enumerate(entries, 1):
        video_url = f"https://youtube.com/watch?v={entry['id']}"
        entry_title = (entry.get("title") or "?").strip()

        ok, filepath = _download_track(video_url, fmt, playlist_dir, i, len(entries))

        if ok and filepath:
            info = {
                "title": entry.get("title", ""),
                "uploader": entry.get("uploader") or entry.get("channel", "") or "",
                "playlist_title": playlist_title,
            }
            _apply_metadata(filepath, info, fmt["ext"])
            successful += 1
            console.print(f"[bold green]  ✓ {i}/{len(entries)} {entry_title[:50]}[/bold green]")

            history.save({
                "titulo": entry_title,
                "url": video_url,
                "formato": fmt["name"],
                "fecha": datetime.now().isoformat(),
            })
        else:
            failed += 1
            console.print(f"[bold red]  ✗ {i}/{len(entries)} {entry_title[:50]}[/bold red]")

        # Small delay between tracks to avoid rate limiting
        if i < len(entries):
            time.sleep(0.5)

    # Summary
    summary = Table.grid(padding=(0, 2))
    summary.add_column(style="bold", justify="right")
    summary.add_column(style="white")
    summary.add_row("Total:", str(len(entries)))
    summary.add_row("Completadas:", f"[green]{successful}[/green]")
    if failed:
        summary.add_row("Fallidas:", f"[red]{failed}[/red]")
    summary.add_row("Ubicacion:", str(playlist_dir))

    panel = Panel(
        Align.center(summary),
        title="[bold white]Resumen de descarga[/bold white]",
        border_style="bright_red",
        box=box.ROUNDED,
    )
    console.print()
    console.print(panel)

    if failed:
        console.print(f"\n[bold yellow]⚠ {failed} cancion(es) fallaron[/bold yellow]")


def batch(urls, fmt_key, folder_name, output_dir=None, titles=None):
    from rich.table import Table
    from rich.panel import Panel
    from rich import box
    from ui.interface import show_urls_table

    fmt = FORMATS.get(fmt_key)
    if not fmt:
        console.print("[red]Formato invalido[/red]")
        return

    out_dir = Path(output_dir) if output_dir else DOWNLOAD_DIR
    out_dir.mkdir(exist_ok=True)
    batch_dir = out_dir / folder_name
    batch_dir.mkdir(exist_ok=True)

    show_urls_table(folder_name, urls)

    from rich.prompt import Confirm
    if not Confirm.ask(f"\n  Descargar [cyan]{len(urls)}[/cyan] canciones en '[bold]{folder_name}[/bold]'?"):
        console.print("[yellow]Cancelado[/yellow]")
        return

    successful = 0
    failed = 0

    for i, url in enumerate(urls, 1):
        track_title = (titles[i - 1] if titles and i - 1 < len(titles) else url.strip())[:60]

        ok, filepath = _download_track(url, fmt, batch_dir, i, len(urls))

        if ok and filepath:
            info = extract_info(url)
            meta = info or {"title": track_title, "uploader": "", "playlist_title": folder_name}
            _apply_metadata(filepath, meta, fmt["ext"])
            successful += 1
            console.print(f"[bold green]  \u2713 {i}/{len(urls)} {track_title[:50]}[/bold green]")

            history.save({
                "titulo": meta.get("title", track_title),
                "url": url,
                "formato": fmt["name"],
                "fecha": datetime.now().isoformat(),
            })
        else:
            failed += 1
            console.print(f"[bold red]  \u2717 {i}/{len(urls)} {track_title[:50]}[/bold red]")

        if i < len(urls):
            time.sleep(0.5)

    summary = Table.grid(padding=(0, 2))
    summary.add_column(style="bold", justify="right")
    summary.add_column(style="white")
    summary.add_row("Total:", str(len(urls)))
    summary.add_row("Completadas:", f"[green]{successful}[/green]")
    if failed:
        summary.add_row("Fallidas:", f"[red]{failed}[/red]")
    summary.add_row("Ubicacion:", str(batch_dir))

    panel = Panel(
        Align.center(summary),
        title="[bold white]Resumen de descarga[/bold white]",
        border_style="bright_red",
        box=box.ROUNDED,
    )
    console.print()
    console.print(panel)

    if failed:
        console.print(f"\n[bold yellow]⚠ {failed} cancion(es) fallaron[/bold yellow]")
