import re
import json
import urllib.request
import urllib.parse
from pathlib import Path

CACHE_DIR = Path(__file__).parent.parent / ".cover_cache"
CACHE_DIR.mkdir(exist_ok=True)

def _clean_title(title, artist=None):
    # Remove common patterns like "(Official Video)", "[4K]", etc.
    title = re.sub(r'\([^)]*(?:video|music|lyric|official|audio|4K|HD|1080p|60fps)[^)]*\)', '', title, flags=re.I)
    title = re.sub(r'\[[^\]]*(?:video|music|lyric|official|audio|4K|HD|1080p|60fps)[^\]]*\]', '', title, flags=re.I)
    # Remove "feat.", "ft.", "ft" parts
    title = re.sub(r'\s+[fF]eat\.?\s+.*$', '', title)
    title = re.sub(r'\s+[fF]t\.?\s+.*$', '', title)
    title = re.sub(r'\s+[xX×]\s+.*$', '', title)
    # Strip trailing/leading garbage
    title = title.strip().rstrip('-– ').strip()

    # Strip "Artist - " prefix if it matches the uploader
    if artist:
        prefix = re.escape(artist.strip()) + r'\s*[-–:]\s*'
        title = re.sub(prefix, '', title, flags=re.I)

    return title.strip()


def get_clean_metadata(info):
    """Return (title, artist, album, cover_path|None) from iTunes, or cleaned YouTube data."""
    artist = info.get("uploader", "")
    title = _clean_title(info.get("title", ""), artist)

    result = _search_itunes(artist, title)
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
        return None

    if not data.get("results"):
        # Try without artist
        url2 = f"https://itunes.apple.com/search?term={urllib.parse.quote(title)}&limit=5&media=music&entity=song"
        try:
            with urllib.request.urlopen(url2, timeout=15) as r:
                data = json.loads(r.read())
        except Exception:
            return None

    if not data.get("results"):
        return None

    result = data["results"][0]
    # Get artwork at max resolution
    art_url = result.get("artworkUrl100", "")
    if art_url:
        art_url = art_url.replace("100x100", "600x600")

    return {
        "artist": result.get("artistName", artist),
        "track": result.get("trackName", title),
        "album": result.get("collectionName", ""),
        "art_url": art_url,
    }

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

    result = _search_itunes(artist, title)
    if not result or not result.get("art_url"):
        return None

    cache_key = urllib.parse.quote(f"{result['artist']}_{result['track']}")
    cover_path = _download_cover(result["art_url"], cache_key)

    if cover_path:
        return {"path": cover_path, "artist": result["artist"], "track": result["track"], "album": result["album"]}
    return None
