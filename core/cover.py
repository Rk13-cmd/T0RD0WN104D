import re
import json
import subprocess
import urllib.request
import urllib.parse
from pathlib import Path

CACHE_DIR = Path(__file__).parent.parent / ".cover_cache"
CACHE_DIR.mkdir(exist_ok=True)

def _clean_title(title, artist=None):
    # Remove common patterns like "(Official Video)", "[4K]", etc.
    title = re.sub(r'\([^)]*(?:video|music|lyric|official|audio|4K|HD|1080p|60fps)[^)]*\)', '', title, flags=re.I)
    title = re.sub(r'\[[^\]]*(?:video|music|lyric|official|audio|4K|HD|1080p|60fps)[^\]]*\]', '', title, flags=re.I)
    # Remove "(Letra)", "(Lyrics)", "(Audio)", etc.
    title = re.sub(r'[\[\(][^\]\)]*(?:letra|lyric|lyrics|audio|video|oficial|official)[^\]\)]*[\]\)]', '', title, flags=re.I)
    # Clean separators: ｜ ; | - etc
    title = re.sub(r'\s*[｜|;]\s*.*$', '', title)
    # Remove "feat.", "ft.", "ft" parts
    title = re.sub(r'\s+[fF]eat\.?\s+.*$', '', title)
    title = re.sub(r'\s+[fF]t\.?\s+.*$', '', title)
    title = re.sub(r'\s+[xX×]\s+.*$', '', title)
    # Strip trailing/leading garbage
    title = title.strip().rstrip('-–. ').strip()
    title = re.sub(r'\s{2,}', ' ', title)

    # Strip "Artist - " prefix if it matches the uploader
    if artist:
        prefix = re.escape(artist.strip()) + r'\s*[-–:]\s*'
        title = re.sub(prefix, '', title, flags=re.I)

    return title.strip()


def get_clean_metadata(info):
    """Return (title, artist, album, cover_path|None) from iTunes → Deezer → YouTube."""
    artist = info.get("uploader", "")
    title = _clean_title(info.get("title", ""), artist)

    result = _resolve_cover_url(artist, title)
    if result:
        cover_path = None
        if result.get("art_url"):
            cache_key = urllib.parse.quote(f"{result['artist']}_{result['track']}")
            cover_path = _download_cover(result["art_url"], cache_key)
        return (result["track"], result["artist"], result["album"], cover_path)

    # Fallback: use cleaned YouTube data
    return (title, artist, info.get("playlist_title", "YouTube Audio"), None)

def _search_itunes(artist, title):
    query = f"{artist} {title}"
    url = f"https://itunes.apple.com/search?term={urllib.parse.quote(query)}&limit=5&media=music&entity=song"

    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read())
    except Exception:
        return _search_itunes_no_artist(title)

    if not data.get("results"):
        return _search_itunes_no_artist(title)

    result = data["results"][0]
    art_url = result.get("artworkUrl100", "")
    if art_url:
        art_url = art_url.replace("100x100", "600x600")

    return {
        "artist": result.get("artistName", artist),
        "track": result.get("trackName", title),
        "album": result.get("collectionName", ""),
        "art_url": art_url,
    }


def _search_itunes_no_artist(title):
    url = f"https://itunes.apple.com/search?term={urllib.parse.quote(title)}&limit=5&media=music&entity=song"
    try:
        with urllib.request.urlopen(url, timeout=15) as r:
            data = json.loads(r.read())
        if data.get("results"):
            result = data["results"][0]
            art_url = result.get("artworkUrl100", "")
            if art_url:
                art_url = art_url.replace("100x100", "600x600")
            return {
                "artist": result.get("artistName", ""),
                "track": result.get("trackName", title),
                "album": result.get("collectionName", ""),
                "art_url": art_url,
            }
    except Exception:
        pass
    return None


def _search_deezer(artist, title):
    """Fallback: Deezer API (no key needed).  Returns square 1000x1000 cover."""
    query = urllib.parse.quote(f"{artist} {title}")
    url = f"https://api.deezer.com/search?q={query}&limit=3&output=json"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read())
        if data.get("data"):
            best = data["data"][0]
            cover_url = best.get("album", {}).get("cover_xl") or best.get("album", {}).get("cover_big")
            if cover_url:
                return {
                    "artist": best.get("artist", {}).get("name", artist),
                    "track": best.get("title", title),
                    "album": best.get("album", {}).get("title", ""),
                    "art_url": cover_url,
                }
    except Exception:
        pass
    return None


def _search_youtube_thumbnail(artist, title):
    """Last resort: grab maxresdefault thumbnail from YouTube search."""
    query = urllib.parse.quote(f"{artist} {title}")
    try:
        result = subprocess.run(
            ["yt-dlp", "--no-warnings", "--dump-json", "--no-download",
             "--playlist-items", "1", f"ytsearch:{artist} {title}"],
            capture_output=True, text=True, timeout=20,
        )
        out = result.stdout.strip()
        if out:
            data = json.loads(out.splitlines()[0])
            vid = data.get("id")
            if vid:
                art_url = f"https://img.youtube.com/vi/{vid}/maxresdefault.jpg"
                # check it exists
                req = urllib.request.Request(art_url, method="HEAD")
                try:
                    with urllib.request.urlopen(req, timeout=10) as r:
                        if r.status == 200:
                            return {
                                "artist": data.get("uploader", artist),
                                "track": data.get("title", title),
                                "album": data.get("playlist_title", "YouTube Audio"),
                                "art_url": art_url,
                            }
                except Exception:
                    art_url = f"https://img.youtube.com/vi/{vid}/hqdefault.jpg"
                    return {
                        "artist": data.get("uploader", artist),
                        "track": data.get("title", title),
                        "album": data.get("playlist_title", "YouTube Audio"),
                        "art_url": art_url,
                    }
    except Exception:
        pass
    return None


def _resolve_cover_url(artist, title):
    """Try iTunes → Deezer → YouTube thumbnail, return first hit or None."""
    # 1) iTunes
    result = _search_itunes(artist, title)
    if result and result.get("art_url"):
        return result
    # 2) Deezer (square, high-res, no key)
    result = _search_deezer(artist, title)
    if result and result.get("art_url"):
        return result
    # 3) YouTube thumbnail
    result = _search_youtube_thumbnail(artist, title)
    if result and result.get("art_url"):
        return result
    return None

def _download_cover(art_url, cache_key):
    ext = ".jpg"
    cache_path = CACHE_DIR / f"{cache_key}{ext}"

    if cache_path.exists():
        return cache_path

    if not art_url:
        return None

    req = urllib.request.Request(art_url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            data = r.read()
        cache_path.write_bytes(data)
        return cache_path
    except Exception:
        return None

def get_cover(info):
    artist = info.get("uploader", "")
    title = _clean_title(info.get("title", ""))

    if not artist or not title:
        return None

    result = _resolve_cover_url(artist, title)
    if not result or not result.get("art_url"):
        return None

    cache_key = urllib.parse.quote(f"{result['artist']}_{result['track']}")
    cover_path = _download_cover(result["art_url"], cache_key)

    if cover_path:
        return {"path": cover_path, "artist": result["artist"], "track": result["track"], "album": result["album"]}
    return None
