# Claude Code Development Notes

This project was developed with assistance from Claude Code.

## Development Process

The script evolved through several iterations:
1. Started as a daily summary posting top 5 tracks
2. Converted to weekly summary covering 7 days
3. Refined to show top 3 tracks, top album, and top playlist
4. Optimized post format to stay within 300 character limit

## Key Design Decisions

- **SQLite storage**: Allows building historical data since Spotify's API is limited
- **Album tracking**: Added to database schema to support top album feature
- **Compact formatting**: Minimal text, emoji-based sections, conditional play counts
- **Single playlist**: Changed from multiple playlists to just the top one for brevity

## Code Structure

- `ingest_recently_played()`: Fetches and stores Spotify listening data
- `get_top_tracks_last_7_days()`: Aggregates most-played tracks with smart sorting
- `get_top_album_last_7_days()`: Finds most-played album
- `get_top_playlist_last_7_days()`: Identifies top playlist from context data
- `build_post_content()`: Formats content for Bluesky with proper facets
