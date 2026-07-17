import re
import subprocess
from pathlib import Path

from spotapi import PublicPlaylist, Podcast

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

console = Console()

SPOTIFY_RE = re.compile(r'(?:open\.spotify\.com|spotify)[/:](playlist|episode|track|album)/([a-zA-Z0-9]+)')
SPOTIFY_URI_RE = re.compile(r'^spotify:(playlist|episode|track|album):([a-zA-Z0-9]+)$')


def detect_link_type(url):
    m = SPOTIFY_RE.search(url)
    if m:
        return m.group(1), m.group(2)
    m = SPOTIFY_URI_RE.match(url.strip())
    if m:
        return m.group(1), m.group(2)
    return None, None


def extract_tracks_from_page(content):
    tracks = []
    items = content.get("items", [])
    for item in items:
        data = item.get("itemV2", {}).get("data", {})
        if not data:
            continue
        name = data.get("name", "").strip()
        artists_list = data.get("artists", {}).get("items", [])
        artist = artists_list[0].get("profile", {}).get("name", "").strip() if artists_list else ""
        if name and artist:
            tracks.append((artist, name))
    return tracks


def search_youtube(query):
    from core.utils import get_ytdlp_path
    ytdlp = get_ytdlp_path()
    cmd = [ytdlp, "--no-warnings", "--dump-json", "--no-download",
           "--playlist-items", "1", f"ytsearch:{query}"]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            return None
        data = __import__("json").loads(result.stdout.strip().split("\n")[0])
        return data.get("webpage_url") or data.get("url")
    except Exception:
        return None


def _resolve_and_print(tracks, content_label):
    console.print(f"  [green]{len(tracks)} {content_label} encontrados[/green]")
    console.print("[yellow]Buscando en YouTube...[/yellow]")

    results = []
    not_found = 0

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("[cyan]Buscando...", total=len(tracks))

        for i, (artist, title) in enumerate(tracks, 1):
            query = f"{artist} - {title}"
            progress.update(task, description=f"[cyan]{artist} - {title[:35]}[/cyan]")

            yt_url = search_youtube(query)
            if yt_url:
                results.append((f"{artist} - {title}", yt_url))
                console.print(f"  [green]\u2713[/green] {i}/{len(tracks)} {artist} - {title[:40]}")
            else:
                not_found += 1
                console.print(f"  [red]\u2717[/red] {i}/{len(tracks)} {artist} - {title[:40]} [dim](no encontrado)[/dim]")

            progress.advance(task)

    if not_found:
        console.print(f"\n[yellow]\u26a0 {not_found} track(s) no encontrados en YouTube[/yellow]")

    return results


def import_from_spotify(url):
    link_type, item_id = detect_link_type(url)
    if not link_type:
        console.print("[red]URL de Spotify invalida[/red]")
        console.print("Usa: [dim]https://open.spotify.com/playlist/...[/dim]")
        console.print("     [dim]https://open.spotify.com/episode/...[/dim]")
        console.print("     [dim]https://open.spotify.com/track/...[/dim]")
        return None, None

    if link_type == "playlist":
        return _import_playlist(item_id)
    elif link_type == "episode":
        return _import_episode(item_id)
    elif link_type == "track":
        return _import_track(item_id)
    elif link_type == "album":
        return _import_album(item_id)

    console.print(f"[red]Tipo no soportado: {link_type}[/red]")
    return None, None


def _import_playlist(playlist_id):
    with console.status("[bold yellow]Obteniendo informacion de la playlist...[/bold yellow]"):
        try:
            pp = PublicPlaylist(playlist_id)
        except Exception as e:
            console.print(f"[red]Error al conectar con Spotify: {e}[/red]")
            return None, None

    try:
        first = pp.get_playlist_info(limit=1)
        playlist_name = (first.get("data", {})
                         .get("playlistV2", {})
                         .get("name", "Spotify Playlist"))
    except Exception:
        playlist_name = "Spotify Playlist"

    with console.status(f"[bold yellow]Extrayendo tracks de: {playlist_name}...[/bold yellow]"):
        try:
            raw_tracks = []
            for content in pp.paginate_playlist():
                raw_tracks.extend(extract_tracks_from_page(content))
        except Exception as e:
            console.print(f"[red]Error al extraer tracks: {e}[/red]")
            return None, None

    if not raw_tracks:
        console.print("[red]No se encontraron tracks en la playlist[/red]")
        return None, None

    results = _resolve_and_print(raw_tracks, "tracks")
    return playlist_name, results


def _import_episode(episode_id):
    with console.status("[bold yellow]Obteniendo informacion del episodio...[/bold yellow]"):
        try:
            ep = Podcast()
            result = ep.get_episode(episode_id)
            data = result.get("data", {}).get("episodeUnionV2", {})
        except Exception as e:
            console.print(f"[red]Error al obtener episodio: {e}[/red]")
            return None, None

    episode_name = data.get("name", "").strip()
    podcast_data = data.get("podcastV2", {}).get("data", {})
    podcast_name = podcast_data.get("name", "").strip()

    if not episode_name or not podcast_name:
        console.print("[red]No se pudo obtener informacion del episodio[/red]")
        return None, None

    name = f"{podcast_name} - {episode_name}"
    console.print(f"  [green]Episodio: {name}[/green]")
    console.print("[yellow]Buscando en YouTube...[/yellow]")

    yt_url = search_youtube(name)
    if yt_url:
        console.print(f"  [green]\u2713[/green] Encontrado en YouTube")
        return name, [(name, yt_url)]
    else:
        console.print(f"  [red]\u2717[/red] No encontrado en YouTube")
        return name, []


def _import_track(track_id):
    with console.status("[bold yellow]Obteniendo informacion del track...[/bold yellow]"):
        try:
            from spotapi import PublicPlaylist
            # For single tracks we need a different approach
            # Use the same internal API pattern
            result = _fetch_track_info(track_id)
        except Exception as e:
            console.print(f"[red]Error al obtener track: {e}[/red]")
            return None, None

    if not result:
        console.print("[red]No se pudo obtener informacion del track[/red]")
        return None, None

    artist = result.get("artist", "")
    title = result.get("title", "")
    if not artist or not title:
        console.print("[red]Track invalido[/red]")
        return None, None

    name = f"{artist} - {title}"
    console.print(f"  [green]Track: {name}[/green]")
    console.print("[yellow]Buscando en YouTube...[/yellow]")

    yt_url = search_youtube(name)
    if yt_url:
        console.print(f"  [green]\u2713[/green] Encontrado en YouTube")
        return name, [(name, yt_url)]
    else:
        console.print(f"  [red]\u2717[/red] No encontrado en YouTube")
        return name, []


def _fetch_track_info(track_id):
    """Fetch single track info via spotapi."""
    from spotapi import Public
    base = Public()
    resp = base.song_info(track_id)
    data = resp.get("data", {}).get("trackUnion", {})
    if not data:
        return None
    name = data.get("name", "").strip()
    artist = ""
    first = data.get("firstArtist", {}).get("items", [])
    if first:
        artist = first[0].get("profile", {}).get("name", "").strip()
    return {"artist": artist, "title": name}


def _import_album(album_id):
    with console.status("[bold yellow]Obteniendo informacion del album...[/bold yellow]"):
        try:
            from spotapi import PublicAlbum
            album = PublicAlbum(album_id)
            info = album.get_album()
        except Exception as e:
            console.print(f"[red]Error al obtener album: {e}[/red]")
            return None, None

    album_name = (info.get("data", {})
                  .get("albumUnion", {})
                  .get("name", "Album"))

    # Extract tracks from album structure
    tracks_data = (info.get("data", {})
                   .get("albumUnion", {})
                   .get("tracks", {})
                   .get("items", []))

    raw_tracks = []
    for item in tracks_data:
        track = item.get("track", {})
        name = track.get("name", "").strip()
        artists_list = track.get("artists", {}).get("items", [])
        artist = artists_list[0].get("profile", {}).get("name", "").strip() if artists_list else ""
        if name and artist:
            raw_tracks.append((artist, name))

    if not raw_tracks:
        console.print("[red]No se encontraron tracks en el album[/red]")
        return None, None

    results = _resolve_and_print(raw_tracks, "tracks")
    return album_name, results
