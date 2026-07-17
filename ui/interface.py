import os
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.align import Align
from rich import box

from core.utils import FORMATS, VIDEO_FORMATS, format_duration

console = Console()


def prompt_ask(prompt_text, default=""):
    """Replacement for Prompt.ask that avoids ^M echo in Termux."""
    console.print(prompt_text, end=" ")
    try:
        val = input()
    except (EOFError, KeyboardInterrupt):
        return default
    if not val and default != "":
        return str(default)
    return val if val else default


def press_enter():
    """Wait for Enter key press, avoiding Rich input issues."""
    console.print("\n[dim]Presiona Enter para continuar...[/dim]", end="")
    input()


def confirm_ask(prompt_text, default=True):
    """Yes/No confirmation avoiding Rich input issues."""
    suffix = " [Y/n]" if default else " [y/N]"
    console.print(f"{prompt_text}{suffix}", end=" ")
    try:
        val = input().strip().lower()
    except (EOFError, KeyboardInterrupt):
        return default
    if not val:
        return default
    return val in ("y", "yes", "s", "si")

def clear():
    os.system('clear')
    print('\033[3J', end='')

def show_section_header(title):
    console.print()
    console.print(Panel(
        Align.center(f"[bold white]{title}[/bold white]"),
        border_style="bright_red",
        box=box.HEAVY,
        padding=(1, 2),
    ))
    console.print()


def show_banner():
    clear()

    initials_bin = "01010011 01001100"

    colored_title = (
        "[bold white]T[/bold white]"
        "[bold bright_red]0[/bold bright_red]"
        "[bold white]RD[/bold white]"
        "[bold bright_red]0[/bold bright_red]"
        "[bold white]WNL[/bold white]"
        "[bold bright_red]0[/bold bright_red]"
        "[bold blue]4[/bold blue]"
        "[bold white]D[/bold white]"
    )
    separator = "[bright_red]" + "\u2500" * 45 + "[/bright_red]"

    content = (
        f"{colored_title}   [dim bright_red]{initials_bin}[/dim bright_red]\n"
        f"{separator}\n"
        f"[dim white]Descarga m\u00fasica desde YouTube[/dim white]\n"
        f"[bright_white]By CHMODX[/bright_white]"
    )

    banner = Panel(
        Align.center(content),
        border_style="bright_red",
        box=box.HEAVY,
        padding=(2, 6),
        subtitle="[dim]V.RK13.1.1[/dim]",
    )
    console.print(banner)
    console.print()

def show_menu():
    table = Table(box=box.SIMPLE, show_header=False, padding=(0, 0), collapse_padding=True)
    table.add_column("Key", style="bright_red", width=5, justify="right")
    table.add_column("Action", style="white")
    table.add_row("[1]", "\U0001f3a7 Spotify")
    table.add_row("[2]", "\U0001f50d Buscar en YouTube")
    table.add_row("[3]", "\U0001f3b5 Una Canci\u00f3n")
    table.add_row("[4]", "\U0001f4cb Lista Audio")
    table.add_row("[5]", "\U0001f517 Varios Audios")
    table.add_row("[6]", "\U0001f3ac Un Video")
    table.add_row("[7]", "\U0001f4fa Lista Videos")
    table.add_row("[8]", "\U0001f517 Varios Videos")
    table.add_row("[9]", "\U0001f4d6 Ver Registro")
    table.add_row("[10]", "\U0001f6e0\ufe0f T00L5RK13")
    table.add_row("[11]", "\u2699\ufe0f Ajustes App")
    table.add_row("[12]", "\U0001f6aa Salir App")
    console.print(table)

def show_info_panel(info):
    dur = format_duration(info.get("duration", 0))
    upload_date = info.get("upload_date", "")
    if upload_date and len(upload_date) == 8:
        upload_date = f"{upload_date[6:8]}/{upload_date[4:6]}/{upload_date[:4]}"

    grid = Table.grid(padding=(0, 1))
    grid.add_column(style="bold yellow", justify="right")
    grid.add_column(style="white")
    grid.add_row("Titulo:", info.get("title", "?")[:60])
    grid.add_row("Canal:", info.get("uploader", "?"))
    grid.add_row("Duracion:", dur)
    grid.add_row("Fecha:", upload_date or "?")
    grid.add_row("Vistas:", f"{info.get('view_count', 0):,}")
    if info.get("like_count"):
        grid.add_row("Likes:", f"{info['like_count']:,}")
    if info.get("playlist_count"):
        grid.add_row("Playlist:", f"{info['playlist']} ({info['playlist_count']} videos)")

    panel = Panel(Align.center(grid), title="[bold white]Informaci\u00f3n[/bold white]", border_style="bright_red", box=box.ROUNDED)
    console.print(panel)

def show_formats_table():
    table = Table(box=box.ROUNDED, header_style="bold white")
    table.add_column("#", style="dim", width=3)
    table.add_column("Formato", style="yellow")
    table.add_column("Extension", style="green")
    table.add_column("Calidad", style="white")
    for key, fmt in FORMATS.items():
        cal = fmt["bitrate"] if fmt["bitrate"] else ("mejor" if fmt["ext"] != "wav" else "max")
        table.add_row(key, fmt["name"], fmt["ext"], cal)
    console.print(Panel(
        Align.center(table),
        title="[bold white]Formatos disponibles[/bold white]",
        border_style="bright_red",
        box=box.ROUNDED,
    ))

def show_video_formats_table():
    table = Table(box=box.ROUNDED, header_style="bold white")
    table.add_column("#", style="dim", width=3)
    table.add_column("Formato", style="yellow")
    table.add_column("Extension", style="green")
    table.add_column("Calidad", style="white")
    for key, fmt in VIDEO_FORMATS.items():
        cal = fmt["quality"] if fmt["quality"] else "mejor"
        table.add_row(key, fmt["name"], fmt["ext"], cal)
    console.print(Panel(
        Align.center(table),
        title="[bold white]Formatos de video disponibles[/bold white]",
        border_style="bright_red",
        box=box.ROUNDED,
    ))


def show_playlist_table(playlist_title, entries):
    table = Table(
        box=box.ROUNDED,
        header_style="bold white",
        show_lines=False,
    )
    table.add_column("#", style="dim", width=4, justify="right")
    table.add_column("Cancion", style="white", width=50)
    table.add_column("Duracion", style="cyan", width=10, justify="right")

    for i, entry in enumerate(entries, 1):
        title = (entry.get("title") or "?").strip()
        dur = entry.get("duration")
        dur_str = format_duration(dur) if dur else "?"
        table.add_row(str(i), title[:48], dur_str)

    total = sum(e.get("duration", 0) or 0 for e in entries)
    total_str = format_duration(total)
    console.print(Panel(
        table,
        title=f"[bold white]{playlist_title}[/bold white]",
        border_style="bright_red",
        box=box.ROUNDED,
        subtitle=f"[dim]{len(entries)} canciones — {total_str}[/dim]",
    ))
    console.print()


def show_search_results(results):
    table = Table(
        box=box.ROUNDED,
        header_style="bold white",
        show_lines=False,
    )
    table.add_column("#", style="dim", width=4, justify="right")
    table.add_column("Titulo", style="white", width=50)
    table.add_column("Canal", style="cyan", width=20)
    table.add_column("Duracion", style="green", width=10, justify="right")

    for i, r in enumerate(results, 1):
        title = (r.get("title") or "?").strip()
        channel = (r.get("channel") or r.get("uploader") or "?").strip()
        dur = r.get("duration")
        dur_str = format_duration(dur) if dur else "?"
        table.add_row(str(i), title[:48], channel[:18], dur_str)

    console.print(Panel(
        table,
        title="[bold white]Resultados de busqueda[/bold white]",
        border_style="bright_red",
        box=box.ROUNDED,
        subtitle=f"[dim]{len(results)} resultados[/dim]",
    ))
    console.print()


def show_urls_table(folder_name, urls):
    table = Table(
        box=box.ROUNDED,
        header_style="bold white",
        show_lines=False,
    )
    table.add_column("#", style="dim", width=4, justify="right")
    table.add_column("URL", style="white", width=70)

    for i, url in enumerate(urls, 1):
        table.add_row(str(i), url[:68])

    console.print(Panel(
        table,
        title=f"[bold white]{folder_name}[/bold white]",
        border_style="bright_red",
        box=box.ROUNDED,
        subtitle=f"[dim]{len(urls)} canciones[/dim]",
    ))
    console.print()


def config_menu(download_dir):
    from core.metadata_fixer import show_storage_bar
    console.print(Panel(
        "[bold white]Configuraci\u00f3n[/bold white]",
        border_style="bright_red",
        box=box.ROUNDED,
    ))
    console.print(f"[yellow]Directorio actual:[/yellow] [cyan]{download_dir}[/cyan]")
    current = str(download_dir)
    console.print("[bold yellow]Almacenamiento disponible:[/bold yellow]")
    show_storage_bar()

    new_dir = prompt_ask("Directorio de descargas", default=current)
    if new_dir != current:
        path = Path(new_dir) if 'Path' in dir() else __import__('pathlib').Path(new_dir)
        console.print(f"[green]Directorio cambiado a: {path}[/green]")
        return path
    console.print("[dim]Sin cambios[/dim]")
    return download_dir
