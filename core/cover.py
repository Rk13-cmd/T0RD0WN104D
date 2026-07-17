import re
import json
import urllib.request
import urllib.parse
from pathlib import Path

CACHE_DIR = Path(__file__).parent.parent / ".cover_cache"
CACHE_DIR.mkdir(exist_ok=True)

_STOPWORDS = frozenset({
    "el", "la", "los", "las", "lo", "de", "del", "en", "un", "una", "unos",
    "unas", "y", "e", "o", "a", "con", "por", "para", "que", "es", "no",
    "se", "su", "le", "me", "te", "nos", "os", "al", "este", "esta", "estos",
    "estas", "como", "más", "muy", "sin", "entre", "desde", "hasta", "pero",
    "si", "tu", "mi", "ya", "solo", "cuando", "donde", "quien", "todo",
    "the", "a", "an", "and", "of", "to", "in", "it", "is", "on", "at",
    "for", "with", "feat", "ft",
})


def _clean_title(title, artist=None):
    remove = re.compile(
        r'[\[\(][^\]\)]*(?:video|music|lyric|lyrics|official|oficial|'
        r'audio|4K|HD|1080p|60fps|letra|letras|sub[ -]?espa[ñn]ol|'
        r'video[ -]?oficial|official[ -]?video|lyric[ -]?video|'
        r'audio[ -]?oficial|cover|remix|live|en[ -]?vivo|'
        r'versión|version|acústica|acoustic|instrumental|'
        r'prod[ -]?by|visualizer|visualizador)[^\]\)]*[\]\)]',
        re.I,
    )
    title = remove.sub('', title)
    title = re.sub(r'\s*[｜|;]\s*.*$', '', title)
    title = re.sub(r'\s+[fF]eat\.?\s+.*$', ' ft', title)
    title = re.sub(r'\s+[fF]t\.?\s+.*$', ' ft', title)
    title = re.sub(r'\s+[xX×]\s+.*$', '', title)
    title = title.strip().rstrip('-–.:; ').strip()
    title = re.sub(r'\s{2,}', ' ', title)
    if artist:
        prefix = re.escape(artist.strip()) + r'\s*[-–:]\s*'
        title = re.sub(prefix, '', title, flags=re.I)
    return title.strip()


def _extract_keywords(text, max_words=3):
    """Keep significant words (≥3 chars, no stopwords)."""
    words = re.findall(r"[A-Za-zÁáÉéÍíÓóÚúÜüÑñ]+", text)
    significant = [w for w in words if w.lower() not in _STOPWORDS and len(w) >= 3]
    return significant[:max_words]


def _search_itunes_raw(term):
    """Low-level iTunes lookup. Returns list of results or None."""
    url = f"https://itunes.apple.com/search?term={urllib.parse.quote(term)}&limit=5&media=music&entity=song"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read())
        return data.get("results")
    except Exception:
        return None


def _pick_match(results, artist, title):
    """From a list of iTunes results, pick the best match based on artist
    proximity, or the first one that has artwork."""
    if not results:
        return None
    best = None
    best_score = -1
    a_lower = artist.strip().lower() if artist else ""
    t_lower = title.strip().lower() if title else ""
    for res in results:
        art_url = (res.get("artworkUrl100") or "").replace("100x100", "600x600")
        if not art_url:
            continue
        r_artist = (res.get("artistName") or "").lower()
        r_track = (res.get("trackName") or "").lower()
        score = 0
        if a_lower and a_lower in r_artist:
            score += 10
            if r_artist == a_lower:
                score += 5
        if t_lower and (t_lower in r_track or r_track.startswith(t_lower)):
            score += 3
            if r_track == t_lower:
                score += 3
        if score > best_score:
            best_score = score
            best = res
    if not best and results:
        best = results[0]
    return best


def _search_itunes_multistage(artist, title):
    """Multi-stage iTunes search — prioritises same-artist matches.
    Order: exact → artist-only → title → keywords.
    Always returns a square iTunes cover or None."""
    stages = []
    stages.append(f"{artist} {title}")
    if artist:
        stages.append(artist)
    if artist:
        stages.append(title)
    keywords = _extract_keywords(title, 3)
    if keywords:
        stages.append(" ".join(keywords))
    if keywords and artist:
        stages.append(f"{artist} {' '.join(keywords[:2])}")

    seen_art = set()
    for q in stages:
        results = _search_itunes_raw(q)
        if not results:
            continue
        match = _pick_match(results, artist, title)
        if not match:
            continue
        art_url = (match.get("artworkUrl100") or "").replace("100x100", "600x600")
        if art_url and art_url not in seen_art:
            seen_art.add(art_url)
            return {
                "artist": match.get("artistName", artist),
                "track": match.get("trackName", title),
                "album": match.get("collectionName", ""),
                "art_url": art_url,
            }
    return None


def _search_deezer(artist, title):
    """Deezer API (no key).  Returns square 1000×1000 cover."""
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


def get_clean_metadata(info):
    """Return (title, artist, album, cover_path|None) from iTunes multi-stage → Deezer."""
    artist = info.get("uploader", "")
    title = _clean_title(info.get("title", ""), artist)
    result = _resolve_cover_url(artist, title)
    if result:
        cover_path = None
        if result.get("art_url"):
            cache_key = urllib.parse.quote(f"{result['artist']}_{result['track']}")
            cover_path = _download_cover(result["art_url"], cache_key)
        return (result["track"], result["artist"], result["album"], cover_path)
    return (title, artist, info.get("playlist_title", "YouTube Audio"), None)


def _resolve_cover_url(artist, title):
    """iTunes multi-stage → Deezer.  Always returns a square cover or None."""
    result = _search_itunes_multistage(artist, title)
    if result and result.get("art_url"):
        return result
    result = _search_deezer(artist, title)
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
