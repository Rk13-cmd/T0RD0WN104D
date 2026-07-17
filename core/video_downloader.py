import os
import time
from pathlib import Path
from datetime import datetime

from rich.console import Console
from rich.align import Align
from rich.table import Table
from rich.panel import Panel
from rich import box

from core.utils import get_ytdlp_path, VIDEO_FORMATS, extract_info, extract_playlist_info
from ui.interface import show_info_panel, confirm_ask
from data import history
from core.downloader import _run_ytdlp, _attempt_download

console = Console()
BASE_DIR = Path(__file__).parent.parent
DOWNLOAD_DIR = BASE_DIR / "downloads"


def _build_video_cmd(ytdlp, fmt, template, url):
    return [ytdlp, "--no-warnings", "--newline",
            "--embed-thumbnail",
            "--embed-metadata",
            "-f", fmt["quality"],
            "-o", template, url]


def single(url, fmt_key, output_dir=None):
    fmt = VIDEO_FORMATS.get(fmt_key)
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
    cmd = _build_video_cmd(ytdlp, fmt, template, url)

    before = set(out_dir.iterdir()) if out_dir.exists() else set()
    ok, filepath, error_msgs = _attempt_download(cmd, out_dir, fmt["ext"], before)

    if not ok:
        for err in error_msgs:
            console.print(f"[red]  {err}[/red]")
        console.print("[yellow]  [!] Reintentando (misma calidad)...[/yellow]")
        time.sleep(1)
        ok, filepath, error_msgs = _attempt_download(cmd, out_dir, fmt["ext"], before)

        if not ok:
            for err in error_msgs:
                console.print(f"[red]  {err}[/red]")
            console.print("\n[bold red]✗ Error durante la descarga[/bold red]")
            return False

    console.print(f"\n[bold green]✓ Guardado:[/bold green] {filepath.name}")

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
    cmd = _build_video_cmd(ytdlp, fmt, template, url)

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
    from ui.interface import show_playlist_table

    fmt = VIDEO_FORMATS.get(fmt_key)
    if not fmt:
        console.print("[red]Formato invalido[/red]")
        return

    out_dir = Path(output_dir) if output_dir else DOWNLOAD_DIR
    out_dir.mkdir(exist_ok=True)

    with console.status("[bold yellow]Obteniendo informacion de la lista...[/bold yellow]"):
        playlist_title, entries = extract_playlist_info(url, limit)

    if not entries:
        console.print("[red]No se pudieron obtener los videos de la lista[/red]")
        return

    playlist_dir = out_dir / (playlist_title or "Videos")
    playlist_dir.mkdir(exist_ok=True)

    show_playlist_table(playlist_title or "Lista de Videos", entries)

    if not confirm_ask(f"\n  Descargar [cyan]{len(entries)}[/cyan] videos?"):
        console.print("[yellow]Cancelado[/yellow]")
        return

    successful = 0
    failed = 0

    for i, entry in enumerate(entries, 1):
        video_url = f"https://youtube.com/watch?v={entry['id']}"
        entry_title = (entry.get("title") or "?").strip()

        ok, filepath = _download_track(video_url, fmt, playlist_dir, i, len(entries))

        if ok and filepath:
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

        if i < len(entries):
            time.sleep(0.5)

    summary = Table.grid(padding=(0, 2))
    summary.add_column(style="bold", justify="right")
    summary.add_column(style="white")
    summary.add_row("Total:", str(len(entries)))
    summary.add_row("Completados:", f"[green]{successful}[/green]")
    if failed:
        summary.add_row("Fallidos:", f"[red]{failed}[/red]")
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
        console.print(f"\n[bold yellow]⚠ {failed} video(s) fallaron[/bold yellow]")


def batch(urls, fmt_key, folder_name, output_dir=None, titles=None):
    from ui.interface import show_urls_table

    fmt = VIDEO_FORMATS.get(fmt_key)
    if not fmt:
        console.print("[red]Formato invalido[/red]")
        return

    out_dir = Path(output_dir) if output_dir else DOWNLOAD_DIR
    out_dir.mkdir(exist_ok=True)
    batch_dir = out_dir / folder_name
    batch_dir.mkdir(exist_ok=True)

    show_urls_table(folder_name, urls)

    if not confirm_ask(f"\n  Descargar [cyan]{len(urls)}[/cyan] videos en '[bold]{folder_name}[/bold]'?"):
        console.print("[yellow]Cancelado[/yellow]")
        return

    successful = 0
    failed = 0

    for i, url in enumerate(urls, 1):
        track_title = (titles[i - 1] if titles and i - 1 < len(titles) else url.strip())[:60]

        ok, filepath = _download_track(url, fmt, batch_dir, i, len(urls))

        if ok and filepath:
            successful += 1
            console.print(f"[bold green]  \u2713 {i}/{len(urls)} {track_title[:50]}[/bold green]")

            info = extract_info(url)
            meta = info or {"title": track_title, "uploader": ""}
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
    summary.add_row("Completados:", f"[green]{successful}[/green]")
    if failed:
        summary.add_row("Fallidos:", f"[red]{failed}[/red]")
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
        console.print(f"\n[bold yellow]⚠ {failed} video(s) fallaron[/bold yellow]")
