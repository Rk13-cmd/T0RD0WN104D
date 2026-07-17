#!/usr/bin/env python3
import sys
from pathlib import Path

from rich.console import Console
from rich.prompt import Prompt, Confirm

from ui.interface import show_banner, show_menu, show_section_header, show_formats_table, show_video_formats_table, show_urls_table, show_search_results, config_menu, clear
from core.downloader import single as download_single, playlist as download_playlist, batch as download_batch
from core.video_downloader import single as video_single, playlist as video_playlist, batch as video_batch
from core.spotify import import_from_spotify
from core.utils import FORMATS, search_youtube
from core.metadata_fixer import fix_folder, interactive_browser
from core.tools_rk13 import tools_rk13_menu
from data import history

console = Console()
BASE_DIR = Path(__file__).parent
DOWNLOAD_DIR = BASE_DIR / "downloads"
DOWNLOAD_DIR.mkdir(exist_ok=True)

def is_playlist_url(url):
    return "playlist" in url.lower() or "list=" in url.lower()

def is_spotify_url(url):
    return "open.spotify.com" in url.lower() or "spotify:" in url.lower()

def handle_menu():
    download_dir = DOWNLOAD_DIR
    while True:
        show_banner()
        show_menu()
        choice = Prompt.ask("  [bright_red]3L3G1R 0PC10N[/bright_red] [bright_red]\u28ff[/bright_red]", default="3")

        # --- EXIT ---
        if choice == "12":
            console.print("[yellow]Hasta luego![/yellow]")
            break

        # --- HISTORY ---
        if choice == "9":
            clear()
            history.show()
            console.input("\n[dim]Presiona Enter para continuar...[/dim]")
            continue

        # --- T00L5RK13 ---
        if choice == "10":
            tools_rk13_menu(DOWNLOAD_DIR)
            continue

        # --- CONFIG ---
        if choice == "11":
            clear()
            download_dir = config_menu(download_dir)
            console.input("\n[dim]Presiona Enter para continuar...[/dim]")
            continue

        # ===== OPTION 1: SPOTIFY =====
        if choice == "1":
            clear()
            show_section_header("PEGA EL LINK DE SPOTIFY")
            spotify_url = Prompt.ask("  [bright_red]URL de Spotify[/bright_red]")
            if not spotify_url:
                console.print("[red]URL requerida[/red]")
                continue

            clear()
            show_section_header("IMPORTANDO DESDE SPOTIFY")
            item_name, results = import_from_spotify(spotify_url)

            if results is None:
                console.print("[red]No se pudo procesar el link de Spotify[/red]")
                continue

            if not results:
                console.print("[yellow]No se encontraron coincidencias en YouTube[/yellow]")
                continue

            only_urls = [url for _, url in results]
            label = item_name or "Spotify"

            clear()
            show_section_header(f"RESULTADO: {label[:50]}")
            show_urls_table(label, only_urls)

            if not Confirm.ask(f"\n  Descargar [cyan]{len(results)}[/cyan] {'cancion' if len(results) == 1 else 'canciones'}?"):
                console.print("[yellow]Cancelado[/yellow]")
                continue

            clear()
            show_section_header("SELECCIONE FORMATO")
            show_formats_table()
            fmt_key = Prompt.ask("  [bright_red]3L3G1R 0PC10N[/bright_red] [bright_red]\u28ff[/bright_red]", default="3")

            only_titles = [t for t, _ in results]
            clear()
            download_batch(only_urls, fmt_key, label, download_dir, titles=only_titles)

            if not Confirm.ask("\n  Importar otra playlist?"):
                console.print("[yellow]Hasta luego![/yellow]")
                break
            continue

        # ===== OPTION 2: BUSCAR EN YOUTUBE =====
        if choice == "2":
            clear()
            show_section_header("BUSCAR EN YOUTUBE")
            query = Prompt.ask("  [bright_red]Que quieres buscar?[/bright_red]")
            if not query:
                console.print("[red]Busqueda vacia[/red]")
                continue

            with console.status("[bold yellow]Buscando...[/bold yellow]"):
                results = search_youtube(query)

            if not results:
                console.print("[red]Sin resultados[/red]")
                continue

            show_search_results(results)
            pick = Prompt.ask("  [bright_red]Numero a descargar[/bright_red] (ej: 1, 1-3, * = todos)", default="1")

            selected = []
            if pick.strip() == "*":
                selected = results
            elif "-" in pick:
                parts = pick.split("-")
                try:
                    start, end = int(parts[0]), int(parts[1])
                    for i in range(start, min(end, len(results)) + 1):
                        selected.append(results[i - 1])
                except ValueError:
                    console.print("[red]Rango invalido[/red]")
                    continue
            else:
                try:
                    idx = int(pick)
                    if 1 <= idx <= len(results):
                        selected.append(results[idx - 1])
                    else:
                        console.print("[red]Numero invalido[/red]")
                        continue
                except ValueError:
                    console.print("[red]Entrada invalida[/red]")
                    continue

            if not selected:
                console.print("[red]Nada seleccionado[/red]")
                continue

            single_mode = len(selected) == 1

            clear()
            if single_mode:
                show_section_header("INFORMACION")
                url = selected[0]["url"]
                success = download_single(url, "3", None)
                if not success and Confirm.ask("  Reintentar con otro formato?"):
                    show_formats_table()
                    fmt_key = Prompt.ask("  [bright_red]3L3G1R 0PC10N[/bright_red] [bright_red]\u28ff[/bright_red]", default="1")
                    download_single(url, fmt_key, None)
            else:
                show_section_header("SELECCIONE FORMATO")
                show_formats_table()
                fmt_key = Prompt.ask("  [bright_red]3L3G1R 0PC10N[/bright_red] [bright_red]\u28ff[/bright_red]", default="3")
                only_urls = [r["url"] for r in selected]
                only_titles = [r["title"] for r in selected]
                clear()
                download_batch(only_urls, fmt_key, "Busqueda YouTube", download_dir, titles=only_titles)

            if not Confirm.ask("\n  Buscar otra cosa?"):
                console.print("[yellow]Hasta luego![/yellow]")
                break
            continue

        # ===== OPTION 3: AUDIO SINGLE =====
        if choice == "3":
            clear()
            show_section_header("INGRESE EL LINK")
            url = Prompt.ask("  [bright_red]URL[/bright_red]")
            if is_spotify_url(url):
                console.print("[yellow]\u2192 Usa la opcion [bold]1[/bold] (Spotify) para links de Spotify[/yellow]")
                continue
            if not url:
                console.print("[red]URL requerida[/red]")
                continue

            clear()
            show_section_header("SELECCIONE FORMATO")
            show_formats_table()
            fmt_key = Prompt.ask("  [bright_red]3L3G1R 0PC10N[/bright_red] [bright_red]\u28ff[/bright_red]", default="3")
            custom_dir = Prompt.ask("  [bright_red]Directorio destino[/bright_red] (Enter para default)", default="")
            out_dir = custom_dir.strip() or None

            clear()
            show_section_header("INFORMACION DE LA CANCION")
            success = download_single(url, fmt_key, out_dir)
            if not success and Confirm.ask("  Reintentar con otro formato?"):
                show_formats_table()
                fmt_key = Prompt.ask("  [bright_red]3L3G1R 0PC10N[/bright_red] [bright_red]\u28ff[/bright_red]", default="1")
                download_single(url, fmt_key, out_dir)

            if not Confirm.ask("\n  Descargar otro?"):
                console.print("[yellow]Hasta luego![/yellow]")
                break

        # ===== OPTION 4: AUDIO PLAYLIST =====
        if choice == "4":
            clear()
            show_section_header("INGRESE EL LINK DE LA LISTA")
            url = Prompt.ask("  [bright_red]URL[/bright_red]")
            if is_spotify_url(url):
                console.print("[yellow]\u2192 Usa la opcion [bold]1[/bold] (Spotify) para links de Spotify[/yellow]")
                continue
            if not url:
                console.print("[red]URL requerida[/red]")
                continue

            clear()
            show_section_header("SELECCIONE FORMATO")
            show_formats_table()
            fmt_key = Prompt.ask("  [bright_red]3L3G1R 0PC10N[/bright_red] [bright_red]\u28ff[/bright_red]", default="3")
            custom_dir = Prompt.ask("  [bright_red]Directorio destino[/bright_red] (Enter para default)", default="")
            out_dir = custom_dir.strip() or None

            limit_input = Prompt.ask("  [bright_red]Cantidad de canciones[/bright_red] (Enter = todas)", default="")
            limit = int(limit_input) if limit_input.strip().isdigit() else None

            clear()
            show_section_header("DESCARGANDO LISTA")
            download_playlist(url, fmt_key, limit, out_dir)

            if not Confirm.ask("\n  Descargar otro?"):
                console.print("[yellow]Hasta luego![/yellow]")
                break

        # ===== OPTION 5: AUDIO BATCH =====
        if choice == "5":
            clear()
            show_section_header("INGRESE LOS LINKS")
            folder_name = Prompt.ask("  [bright_red]Nombre de la carpeta[/bright_red]").strip()
            if not folder_name:
                folder_name = "Rafaga"

            urls = []
            i = 1
            while True:
                inp = Prompt.ask(f"  [bright_red]Link {i}[/bright_red]").strip()
                if inp.lower() == "y":
                    if not urls:
                        console.print("[red]Ingresa al menos un link[/red]")
                        continue
                    break
                if inp:
                    urls.append(inp)
                    i += 1

            clear()
            show_section_header("SELECCIONE FORMATO")
            show_formats_table()
            fmt_key = Prompt.ask("  [bright_red]3L3G1R 0PC10N[/bright_red] [bright_red]\u28ff[/bright_red]", default="3")

            clear()
            download_batch(urls, fmt_key, folder_name, download_dir)

            if not Confirm.ask("\n  Descargar otro lote?"):
                console.print("[yellow]Hasta luego![/yellow]")
                break
            continue

        # ===== OPTION 6: VIDEO SINGLE =====
        if choice == "6":
            clear()
            show_section_header("INGRESE EL LINK")
            url = Prompt.ask("  [bright_red]URL[/bright_red]")
            if is_spotify_url(url):
                console.print("[yellow]\u2192 Usa la opcion [bold]1[/bold] (Spotify) para links de Spotify[/yellow]")
                continue
            if not url:
                console.print("[red]URL requerida[/red]")
                continue

            clear()
            show_section_header("SELECCIONE FORMATO")
            show_video_formats_table()
            fmt_key = Prompt.ask("  [bright_red]3L3G1R 0PC10N[/bright_red] [bright_red]\u28ff[/bright_red]", default="1")
            custom_dir = Prompt.ask("  [bright_red]Directorio destino[/bright_red] (Enter para default)", default="")
            out_dir = custom_dir.strip() or None

            clear()
            show_section_header("INFORMACION DEL VIDEO")
            success = video_single(url, fmt_key, out_dir)
            if not success and Confirm.ask("  Reintentar con otra calidad?"):
                show_video_formats_table()
                fmt_key = Prompt.ask("  [bright_red]3L3G1R 0PC10N[/bright_red] [bright_red]\u28ff[/bright_red]", default="1")
                video_single(url, fmt_key, out_dir)

            if not Confirm.ask("\n  Descargar otro?"):
                console.print("[yellow]Hasta luego![/yellow]")
                break

        # ===== OPTION 7: VIDEO PLAYLIST =====
        if choice == "7":
            clear()
            show_section_header("INGRESE EL LINK DE LA LISTA")
            url = Prompt.ask("  [bright_red]URL[/bright_red]")
            if is_spotify_url(url):
                console.print("[yellow]\u2192 Usa la opcion [bold]1[/bold] (Spotify) para links de Spotify[/yellow]")
                continue
            if not url:
                console.print("[red]URL requerida[/red]")
                continue

            clear()
            show_section_header("SELECCIONE FORMATO")
            show_video_formats_table()
            fmt_key = Prompt.ask("  [bright_red]3L3G1R 0PC10N[/bright_red] [bright_red]\u28ff[/bright_red]", default="1")
            custom_dir = Prompt.ask("  [bright_red]Directorio destino[/bright_red] (Enter para default)", default="")
            out_dir = custom_dir.strip() or None

            limit_input = Prompt.ask("  [bright_red]Cantidad de videos[/bright_red] (Enter = todos)", default="")
            limit = int(limit_input) if limit_input.strip().isdigit() else None

            clear()
            show_section_header("DESCARGANDO LISTA")
            video_playlist(url, fmt_key, limit, out_dir)

            if not Confirm.ask("\n  Descargar otro?"):
                console.print("[yellow]Hasta luego![/yellow]")
                break

        # ===== OPTION 8: VIDEO BATCH =====
        if choice == "8":
            clear()
            show_section_header("INGRESE LOS LINKS")
            folder_name = Prompt.ask("  [bright_red]Nombre de la carpeta[/bright_red]").strip()
            if not folder_name:
                folder_name = "Videos"

            urls = []
            i = 1
            while True:
                inp = Prompt.ask(f"  [bright_red]Link {i}[/bright_red]").strip()
                if inp.lower() == "y":
                    if not urls:
                        console.print("[red]Ingresa al menos un link[/red]")
                        continue
                    break
                if inp:
                    urls.append(inp)
                    i += 1

            clear()
            show_section_header("SELECCIONE FORMATO")
            show_video_formats_table()
            fmt_key = Prompt.ask("  [bright_red]3L3G1R 0PC10N[/bright_red] [bright_red]\u28ff[/bright_red]", default="1")

            clear()
            video_batch(urls, fmt_key, folder_name, download_dir)

            if not Confirm.ask("\n  Descargar otro lote?"):
                console.print("[yellow]Hasta luego![/yellow]")
                break
            continue

def main():
    try:
        handle_menu()
    except KeyboardInterrupt:
        clear()
        console.print("[yellow]Cancelado por el usuario[/yellow]")
        sys.exit(0)

if __name__ == "__main__":
    main()
