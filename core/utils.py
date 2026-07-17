import subprocess
import json
from pathlib import Path

from rich.console import Console

console = Console()

VENV_DIR = Path(__file__).parent.parent / "venv"

def get_ytdlp_path():
    p = VENV_DIR / "bin" / "yt-dlp"
    return str(p) if p.exists() else "yt-dlp"

def extract_info(url):
    ytdlp = get_ytdlp_path()
    cmd = [ytdlp, "--no-warnings", "--dump-json", "--no-download", url]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            if result.stderr.strip():
                console.print(f"[red]  yt-dlp error: {result.stderr.strip()}[/red]")
            return None
        data = json.loads(result.stdout.strip().split("\n")[0])
        return data
    except subprocess.TimeoutExpired:
        console.print("[red]  Tiempo de espera agotado al obtener información[/red]")
        return None
    except json.JSONDecodeError as e:
        console.print(f"[red]  Error al parsear respuesta de yt-dlp: {e}[/red]")
        return None
    except Exception as e:
        console.print(f"[red]  Error inesperado: {e}[/red]")
        return None

def extract_playlist_info(url, limit=None):
    ytdlp = get_ytdlp_path()
    cmd = [ytdlp, "--no-warnings", "--flat-playlist", "--dump-single-json", "--no-download", url]
    if limit:
        cmd.insert(1, f"--playlist-items=1:{limit}")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if result.returncode != 0:
            if result.stderr.strip():
                console.print(f"[red]  yt-dlp error: {result.stderr.strip()}[/red]")
            return None, None
        data = json.loads(result.stdout)
        entries = data.get("entries", [])
        if not entries:
            console.print("[red]  La playlist no contiene entradas o es privada[/red]")
            return None, None
        return data.get("title", "Playlist"), entries
    except subprocess.TimeoutExpired:
        console.print("[red]  Tiempo de espera agotado al obtener la playlist[/red]")
        return None, None
    except json.JSONDecodeError as e:
        console.print(f"[red]  Error al parsear playlist: {e}[/red]")
        return None, None
    except Exception as e:
        console.print(f"[red]  Error inesperado: {e}[/red]")
        return None, None

def format_duration(seconds):
    try:
        s = int(float(seconds))
        h, r = divmod(s, 3600)
        m, s = divmod(r, 60)
        if h:
            return f"{h}h {m:02d}m {s:02d}s"
        return f"{m}m {s:02d}s"
    except:
        return str(seconds)


def search_youtube(query, limit=10):
    """Search YouTube and return list of results with title, url, duration, channel."""
    ytdlp = get_ytdlp_path()
    cmd = [ytdlp, "--no-warnings", "--dump-json", "--no-download",
           "--flat-playlist", f"ytsearch{limit}:{query}"]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            return None
        lines = [l for l in result.stdout.strip().split("\n") if l]
        data = []
        for line in lines:
            try:
                item = json.loads(line)
                data.append({
                    "title": item.get("title", "?"),
                    "url": item.get("url") or item.get("webpage_url", ""),
                    "duration": item.get("duration"),
                    "channel": item.get("channel") or item.get("uploader", "?"),
                    "id": item.get("id", ""),
                })
            except json.JSONDecodeError:
                continue
        return data
    except subprocess.TimeoutExpired:
        console.print("[red]  Tiempo de espera agotado en la busqueda[/red]")
        return None
    except Exception:
        return None


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
