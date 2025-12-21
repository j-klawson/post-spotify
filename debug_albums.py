#!/usr/bin/env python3
"""Debug script to see what albums are in the database"""

import sqlite3
import time
from dotenv import load_dotenv
import os

load_dotenv()
SQLITE_PATH = os.getenv("SQLITE_PATH", "spotify_listening.sqlite3")

conn = sqlite3.connect(SQLITE_PATH)
since = int(time.time()) - 7 * 24 * 3600

print("=== Top Albums (Last 7 Days) ===\n")
rows = conn.execute(
    """
    SELECT album_name, album_id, COUNT(*) as plays,
           GROUP_CONCAT(DISTINCT track_name) as tracks
    FROM plays
    WHERE played_at_unix >= ?
      AND album_id IS NOT NULL
    GROUP BY album_id
    ORDER BY plays DESC
    LIMIT 10
    """,
    (since,),
).fetchall()

for album_name, album_id, plays, tracks in rows:
    print(f"{plays}x {album_name}")
    print(f"   Album ID: {album_id}")
    print(f"   URL: https://open.spotify.com/album/{album_id}")
    print(f"   Tracks: {tracks[:100]}...")
    print()

print("\n=== Recent Plays with Album Info ===\n")
recent = conn.execute(
    """
    SELECT track_name, artist_name, album_name, datetime(played_at_unix, 'unixepoch')
    FROM plays
    WHERE played_at_unix >= ?
    ORDER BY played_at_unix DESC
    LIMIT 20
    """,
    (since,),
).fetchall()

for track, artist, album, played_at in recent:
    print(f"{played_at}: {track} - {artist} (Album: {album})")

conn.close()
