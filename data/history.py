import json
from pathlib import Path
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import box

console = Console()

HISTORY_FILE = Path(__file__).parent.parent / ".history.json"

def load():
    if HISTORY_FILE.exists():
        try:
            return json.loads(HISTORY_FILE.read_text())
        except:
            return []
    return []

def save(entry):
    history = load()
    history.insert(0, entry)
    if len(history) > 50:
        history = history[:50]
    HISTORY_FILE.write_text(json.dumps(history, indent=2, ensure_ascii=False))

def show():
    history = load()
    if not history:
        console.print("[dim]No hay descargas previas[/dim]")
        return
    table = Table(title="Historial de descargas", box=box.ROUNDED)
    table.add_column("#", style="dim", width=3)
    table.add_column("Titulo", style="cyan")
    table.add_column("Formato", style="yellow")
    table.add_column("Fecha", style="green")
    for i, entry in enumerate(history[:15], 1):
        fecha = entry.get("fecha", "")[:16]
        table.add_row(str(i), entry.get("titulo", "?")[:45], entry.get("formato", "?"), fecha)
    console.print(Panel(
        table,
        title="[bold white]Historial de descargas[/bold white]",
        border_style="bright_red",
        box=box.ROUNDED,
    ))
