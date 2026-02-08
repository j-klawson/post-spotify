# Claude Code Development Notes

This project was developed with assistance from Claude Code.

## Development Process

The script evolved through several iterations:
1. Started as a daily summary posting top 5 tracks
2. Converted to weekly summary covering 7 days
3. Refined to show top 3 tracks, top album, and top playlist
4. Optimized post format to stay within 300 character limit
5. Refactored to support multiple platforms (Bluesky, Mastodon)

## Key Design Decisions

- **SQLite storage**: Allows building historical data since Spotify's API is limited
- **Album tracking**: Added to database schema to support top album feature
- **Compact formatting**: Minimal text, emoji-based sections, conditional play counts
- **Single playlist**: Changed from multiple playlists to just the top one for brevity
- **Playlist fallback**: Spotify-generated playlists (Daily Mix, Discover Weekly) use ephemeral IDs that expire; the code tries up to 10 playlists to find one that's still accessible
- **Abstract poster pattern**: `BasePoster` class allows easy addition of new platforms

## Architecture

```
post_spotify.py
├── BasePoster (ABC)
│   ├── BlueskyPoster - Uses atproto TextBuilder for rich text
│   └── MastodonPoster - Uses plain text with auto-linkified URLs
├── Spotify integration (spotipy)
├── SQLite storage
└── CLI with platform selection flags
```

## Code Structure

- `ingest_recently_played()`: Fetches and stores Spotify listening data
- `get_top_tracks_last_7_days()`: Aggregates most-played tracks with smart sorting
- `get_top_album_last_7_days()`: Finds most-played album with artist
- `get_top_playlist_last_7_days()`: Identifies top playlist from context data
- `BasePoster`: Abstract class for social media platforms
- `BlueskyPoster.build_content()`: Formats content for Bluesky with proper facets
- `MastodonPoster.build_content()`: Formats plain text for Mastodon

## CLI Usage

```bash
./run.sh                      # Post to all configured platforms
./run.sh --bluesky            # Post to Bluesky only
./run.sh --mastodon           # Post to Mastodon only
./run.sh --bluesky --mastodon # Post to both explicitly
./run.sh --ingest-only        # Ingest data without posting
```

## Adding New Platforms

To add a new platform:
1. Create a new class inheriting from `BasePoster`
2. Implement `name`, `is_configured()`, `build_content()`, and `post()`
3. Add to `get_all_posters()` registry
4. Add CLI flag in `main()`
5. Add environment variables to `.env.example`
