#!/usr/bin/env python3
"""
post_spotify.py

Post Spotify listening summary to social platforms (Bluesky, Mastodon).

- Top 3 Spotify tracks listened to in the last 7 days (each track links to Spotify)
- Top album listened to in the last 7 days
- Top playlist listened to in the last 7 days (ONLY when Spotify provides playlist context)

Supports:
  --ingest-only   Ingest listening data into SQLite but do not post
  --bluesky       Post to Bluesky only
  --mastodon      Post to Mastodon only
  (no flags)      Post to all configured platforms

Notes:
- Spotify's recently-played API is limited; ingest regularly for best results.
- Playlist stats are based strictly on Spotify play context (no inference).

Env vars (.env supported):
  SPOTIFY_CLIENT_ID
  SPOTIFY_CLIENT_SECRET
  SPOTIFY_REDIRECT_URI

For Bluesky:
  BSKY_HANDLE
  BSKY_PASSWORD

For Mastodon:
  MASTODON_INSTANCE
  MASTODON_ACCESS_TOKEN

Optional env vars:
  SPOTIFY_TOKEN_CACHE=.spotify_token_cache
  SQLITE_PATH=spotify_listening.sqlite3
  INGEST_LOOKBACK_HOURS=26
  MAX_TOP_TRACKS=3
  MAX_PLAYLISTS=1
"""

import os
import sys
import time
import argparse
import sqlite3
import datetime as dt
from abc import ABC, abstractmethod
from typing import List, Tuple, Optional, Any

from dotenv import load_dotenv
import spotipy
from spotipy.oauth2 import SpotifyOAuth

load_dotenv()

# ---------- Required Spotify ----------
SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID")
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET")
SPOTIFY_REDIRECT_URI = os.getenv("SPOTIFY_REDIRECT_URI")

# ---------- Platform Credentials ----------
BSKY_HANDLE = os.getenv("BSKY_HANDLE")
BSKY_PASSWORD = os.getenv("BSKY_PASSWORD")
MASTODON_INSTANCE = os.getenv("MASTODON_INSTANCE")
MASTODON_ACCESS_TOKEN = os.getenv("MASTODON_ACCESS_TOKEN")

# ---------- Optional ----------
SPOTIFY_TOKEN_CACHE = os.getenv("SPOTIFY_TOKEN_CACHE", ".spotify_token_cache")
SQLITE_PATH = os.getenv("SQLITE_PATH", "spotify_listening.sqlite3")

INGEST_LOOKBACK_HOURS = int(os.getenv("INGEST_LOOKBACK_HOURS", "26"))
MAX_TOP_TRACKS = int(os.getenv("MAX_TOP_TRACKS", "3"))
MAX_PLAYLISTS = int(os.getenv("MAX_PLAYLISTS", "1"))


def check_spotify_credentials() -> None:
    """Check that required Spotify credentials are set."""
    required = ["SPOTIFY_CLIENT_ID", "SPOTIFY_CLIENT_SECRET", "SPOTIFY_REDIRECT_URI"]
    missing = [v for v in required if not os.getenv(v)]
    if missing:
        print("Error: Missing required Spotify environment variables:")
        for v in missing:
            print(f"- {v}")
        sys.exit(1)


# ---------- Spotify ----------
def spotify_client() -> spotipy.Spotify:
    auth = SpotifyOAuth(
        client_id=SPOTIFY_CLIENT_ID,
        client_secret=SPOTIFY_CLIENT_SECRET,
        redirect_uri=SPOTIFY_REDIRECT_URI,
        scope="user-read-recently-played playlist-read-private playlist-read-collaborative",
        open_browser=False,
        cache_path=SPOTIFY_TOKEN_CACHE,
    )
    return spotipy.Spotify(auth_manager=auth)


# ---------- Database ----------
def db_connect(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


def db_init(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS plays (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            played_at TEXT NOT NULL,
            played_at_unix INTEGER NOT NULL,
            track_id TEXT NOT NULL,
            track_name TEXT NOT NULL,
            artist_name TEXT NOT NULL,
            album_id TEXT,
            album_name TEXT,
            context_type TEXT,
            context_uri TEXT,
            UNIQUE(played_at, track_id)
        );

        CREATE INDEX IF NOT EXISTS idx_plays_played_at_unix
            ON plays(played_at_unix);

        CREATE TABLE IF NOT EXISTS playlists (
            playlist_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            url TEXT
        );
        """
    )

    # Migration: Add album columns if they don't exist
    cur = conn.cursor()
    try:
        cur.execute("ALTER TABLE plays ADD COLUMN album_id TEXT")
    except sqlite3.OperationalError:
        pass  # Column already exists

    try:
        cur.execute("ALTER TABLE plays ADD COLUMN album_name TEXT")
    except sqlite3.OperationalError:
        pass  # Column already exists

    conn.commit()


def iso_to_unix_seconds(iso: str) -> int:
    s = iso.strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    return int(dt.datetime.fromisoformat(s).timestamp())


# ---------- Ingest ----------
def ingest_recently_played(
    sp: spotipy.Spotify,
    conn: sqlite3.Connection,
    lookback_hours: int,
) -> int:
    after_ms = int((time.time() - lookback_hours * 3600) * 1000)
    results = sp.current_user_recently_played(limit=50, after=after_ms)

    cur = conn.cursor()
    inserted = 0

    for item in results.get("items", []):
        played_at = item.get("played_at")
        track = item.get("track") or {}
        track_id = track.get("id")
        if not played_at or not track_id:
            continue

        track_name = track.get("name", "Unknown track")
        artists = track.get("artists") or []
        artist_name = artists[0].get("name", "Unknown artist") if artists else "Unknown artist"

        album = track.get("album") or {}
        album_id = album.get("id")
        album_name = album.get("name")

        context = item.get("context") or {}
        context_type = context.get("type")
        context_uri = context.get("uri")

        cur.execute(
            """
            INSERT OR IGNORE INTO plays
            (played_at, played_at_unix, track_id, track_name, artist_name, album_id, album_name, context_type, context_uri)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                played_at,
                iso_to_unix_seconds(played_at),
                track_id,
                track_name,
                artist_name,
                album_id,
                album_name,
                context_type,
                context_uri,
            ),
        )
        if cur.rowcount == 1:
            inserted += 1

    conn.commit()
    return inserted


def cache_playlist_metadata(sp: spotipy.Spotify, conn: sqlite3.Connection) -> None:
    cur = conn.cursor()
    results = sp.current_user_playlists(limit=50)

    while results:
        for pl in results.get("items", []):
            pid = pl.get("id")
            if not pid:
                continue
            name = pl.get("name") or "Unnamed playlist"
            url = (pl.get("external_urls") or {}).get("spotify") or ""
            cur.execute(
                """
                INSERT INTO playlists (playlist_id, name, url)
                VALUES (?, ?, ?)
                ON CONFLICT(playlist_id) DO UPDATE SET
                  name=excluded.name,
                  url=excluded.url
                """,
                (pid, name, url),
            )
        results = sp.next(results) if results.get("next") else None

    conn.commit()


# ---------- Queries ----------
def get_top_tracks_last_7_days(
    conn: sqlite3.Connection,
    limit: int,
) -> List[Tuple[str, str, int]]:
    """
    Returns [(track_id, "Track — Artist", count), ...]

    Rule:
      - If any track repeats (max count > 1):
          sort by count DESC, then last_played DESC
      - Else:
          return the most recently played unique tracks (chronological recency)
          (count will be 1 for all)
    """
    since = int(time.time()) - 7 * 24 * 3600

    rows = conn.execute(
        """
        SELECT
          track_id,
          track_name,
          artist_name,
          COUNT(*) AS c,
          MAX(played_at_unix) AS last_played
        FROM plays
        WHERE played_at_unix >= ?
        GROUP BY track_id
        """,
        (since,),
    ).fetchall()

    if not rows:
        return []

    max_count = max(int(r[3]) for r in rows)

    if max_count > 1:
        # Sort by repeats, then recency
        rows_sorted = sorted(
            rows,
            key=lambda r: (int(r[3]), int(r[4])),
            reverse=True,
        )[:limit]

        return [(r[0], f"{r[1]} — {r[2]}", int(r[3])) for r in rows_sorted]

    # Fallback: nothing repeats -> show most recent tracks by last_played
    rows_sorted = sorted(rows, key=lambda r: int(r[4]), reverse=True)[:limit]
    return [(r[0], f"{r[1]} — {r[2]}", 1) for r in rows_sorted]


def get_top_album_last_7_days(conn: sqlite3.Connection) -> Optional[Tuple[str, str, str, int]]:
    """Returns (album_id, album_name, artist_name, play_count) or None"""
    since = int(time.time()) - 7 * 24 * 3600
    row = conn.execute(
        """
        SELECT album_id, album_name, artist_name, COUNT(*) as c
        FROM plays
        WHERE played_at_unix >= ?
          AND album_id IS NOT NULL
        GROUP BY album_id
        ORDER BY c DESC
        LIMIT 1
        """,
        (since,),
    ).fetchone()

    if row:
        return (row[0], row[1], row[2], int(row[3]))
    return None


def parse_playlist_id(uri: Optional[str]) -> Optional[str]:
    if uri and uri.startswith("spotify:playlist:"):
        return uri.split(":")[-1]
    return None


def get_top_playlist_last_7_days(
    conn: sqlite3.Connection, sp: spotipy.Spotify
) -> Optional[Tuple[str, str, int]]:
    """Returns (playlist_name, playlist_url, play_count) or None"""
    since = int(time.time()) - 7 * 24 * 3600
    rows = conn.execute(
        """
        SELECT context_uri, COUNT(*) as c
        FROM plays
        WHERE played_at_unix >= ?
          AND context_type = 'playlist'
          AND context_uri IS NOT NULL
        GROUP BY context_uri
        ORDER BY c DESC
        LIMIT 10
        """,
        (since,),
    ).fetchall()

    if not rows:
        return None

    for row in rows:
        pid = parse_playlist_id(row[0])
        if not pid:
            continue

        meta = conn.execute(
            """
            SELECT name, COALESCE(url,'')
            FROM playlists
            WHERE playlist_id = ?
            """,
            (pid,),
        ).fetchone()

        if meta:
            return (meta[0], meta[1], int(row[1]))

        # Fetch from Spotify API if not cached (e.g., Discover Weekly, Daily Mix)
        try:
            playlist_data = sp.playlist(pid, fields="name,external_urls")
            name = playlist_data.get("name", "Unknown Playlist")
            url = (playlist_data.get("external_urls") or {}).get("spotify", "")
            # Cache for future use
            conn.execute(
                """
                INSERT INTO playlists (playlist_id, name, url)
                VALUES (?, ?, ?)
                ON CONFLICT(playlist_id) DO UPDATE SET name=excluded.name, url=excluded.url
                """,
                (pid, name, url),
            )
            conn.commit()
            return (name, url, int(row[1]))
        except spotipy.SpotifyException:
            # Playlist not accessible (404, private, etc.), try next one
            continue

    return None


# ---------- Abstract Poster Base Class ----------
class BasePoster(ABC):
    """Abstract base class for social media posters."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable name of the platform."""
        pass

    @abstractmethod
    def is_configured(self) -> bool:
        """Check if the platform credentials are configured."""
        pass

    @abstractmethod
    def build_content(
        self,
        tracks: List[Tuple[str, str, int]],
        album: Optional[Tuple[str, str, str, int]],
        playlist: Optional[Tuple[str, str, int]],
    ) -> Any:
        """Build platform-specific content."""
        pass

    @abstractmethod
    def post(self, content: Any) -> None:
        """Post content to the platform."""
        pass

    def post_summary(
        self,
        tracks: List[Tuple[str, str, int]],
        album: Optional[Tuple[str, str, str, int]],
        playlist: Optional[Tuple[str, str, int]],
    ) -> None:
        """Build and post the summary."""
        content = self.build_content(tracks, album, playlist)
        self.post(content)
        print(f"Posted to {self.name}")


# ---------- Bluesky Poster ----------
class BlueskyPoster(BasePoster):
    """Posts to Bluesky using AT Protocol."""

    @property
    def name(self) -> str:
        return "Bluesky"

    def is_configured(self) -> bool:
        return bool(BSKY_HANDLE and BSKY_PASSWORD)

    def build_content(
        self,
        tracks: List[Tuple[str, str, int]],
        album: Optional[Tuple[str, str, str, int]],
        playlist: Optional[Tuple[str, str, int]],
    ):
        from atproto import client_utils

        b = client_utils.TextBuilder()
        b.text("Top 🎵 This week:\n\n")

        # Top tracks
        if tracks:
            for track_id, label, n in tracks:
                track_url = f"https://open.spotify.com/track/{track_id}"
                b.link(label, track_url)
                if n > 1:
                    b.text(f" (x{n})")
                b.text("\n")

        # Top album
        if album:
            album_id, album_name, artist_name, count = album
            b.text("\n📀 ")
            album_url = f"https://open.spotify.com/album/{album_id}"
            b.link(f"{album_name} — {artist_name}", album_url)

        # Top playlist
        if playlist:
            name, url, count = playlist
            b.text("\n📂 ")
            if url:
                b.link(name, url)
            else:
                b.text(name)

        b.text("\n\n")
        b.tag("#NowPlaying", "NowPlaying")
        b.text(" ")
        b.tag("#Music", "Music")

        return b

    def post(self, content) -> None:
        from atproto import Client

        client = Client()
        client.login(BSKY_HANDLE, BSKY_PASSWORD)
        client.send_post(content)


# ---------- Mastodon Poster ----------
class MastodonPoster(BasePoster):
    """Posts to Mastodon."""

    @property
    def name(self) -> str:
        return "Mastodon"

    def is_configured(self) -> bool:
        return bool(MASTODON_INSTANCE and MASTODON_ACCESS_TOKEN)

    def build_content(
        self,
        tracks: List[Tuple[str, str, int]],
        album: Optional[Tuple[str, str, str, int]],
        playlist: Optional[Tuple[str, str, int]],
    ) -> str:
        """Build plain text content for Mastodon (URLs auto-linkified)."""
        lines = ["Top 🎵 This week:", ""]

        # Top tracks
        if tracks:
            for track_id, label, n in tracks:
                track_url = f"https://open.spotify.com/track/{track_id}"
                line = f"{label} {track_url}"
                if n > 1:
                    line += f" (x{n})"
                lines.append(line)

        # Top album
        if album:
            album_id, album_name, artist_name, count = album
            album_url = f"https://open.spotify.com/album/{album_id}"
            lines.append("")
            lines.append(f"📀 {album_name} — {artist_name} {album_url}")

        # Top playlist
        if playlist:
            name, url, count = playlist
            lines.append("")
            if url:
                lines.append(f"📂 {name} {url}")
            else:
                lines.append(f"📂 {name}")

        lines.append("")
        lines.append("#NowPlaying #Music #Spotify")

        return "\n".join(lines)

    def post(self, content: str) -> None:
        from mastodon import Mastodon

        client = Mastodon(
            access_token=MASTODON_ACCESS_TOKEN,
            api_base_url=MASTODON_INSTANCE,
        )
        client.status_post(content)


# ---------- Poster Registry ----------
def get_all_posters() -> List[BasePoster]:
    """Return all available poster implementations."""
    return [BlueskyPoster(), MastodonPoster()]


def get_configured_posters(requested: Optional[List[str]] = None) -> List[BasePoster]:
    """
    Get posters to use based on configuration and CLI flags.

    Args:
        requested: List of platform names requested via CLI flags.
                   If None or empty, returns all configured platforms.
    """
    all_posters = get_all_posters()

    if requested:
        # Filter to only requested platforms
        posters = [p for p in all_posters if p.name.lower() in [r.lower() for r in requested]]
        # Check that requested platforms are configured
        for p in posters:
            if not p.is_configured():
                print(f"Error: {p.name} requested but not configured.")
                print(f"Please set the required environment variables for {p.name}.")
                sys.exit(1)
        return posters
    else:
        # Return all configured platforms
        return [p for p in all_posters if p.is_configured()]


# ---------- Main ----------
def main() -> int:
    parser = argparse.ArgumentParser(
        description="Post weekly Spotify summary to social platforms"
    )
    parser.add_argument(
        "--ingest-only",
        action="store_true",
        help="Ingest listening history into SQLite but do not post",
    )
    parser.add_argument(
        "--bluesky",
        action="store_true",
        help="Post to Bluesky",
    )
    parser.add_argument(
        "--mastodon",
        action="store_true",
        help="Post to Mastodon",
    )
    args = parser.parse_args()

    # Check Spotify credentials
    check_spotify_credentials()

    sp = spotify_client()
    conn = db_connect(SQLITE_PATH)
    db_init(conn)

    inserted = ingest_recently_played(sp, conn, INGEST_LOOKBACK_HOURS)
    cache_playlist_metadata(sp, conn)

    if args.ingest_only:
        print(f"Ingest complete: {inserted} new plays added.")
        return 0

    # Determine which platforms to post to
    requested_platforms = []
    if args.bluesky:
        requested_platforms.append("bluesky")
    if args.mastodon:
        requested_platforms.append("mastodon")

    posters = get_configured_posters(requested_platforms if requested_platforms else None)

    if not posters:
        print("Error: No platforms configured.")
        print("Please configure at least one platform in your .env file:")
        print("  - Bluesky: BSKY_HANDLE and BSKY_PASSWORD")
        print("  - Mastodon: MASTODON_INSTANCE and MASTODON_ACCESS_TOKEN")
        return 1

    # Get data
    tracks = get_top_tracks_last_7_days(conn, MAX_TOP_TRACKS)
    album = get_top_album_last_7_days(conn)
    playlist = get_top_playlist_last_7_days(conn, sp)

    # Post to each platform
    for poster in posters:
        try:
            poster.post_summary(tracks, album, playlist)
        except Exception as e:
            print(f"Error posting to {poster.name}: {e}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
