# Post Spotify

A Python script that posts your weekly Spotify listening stats to Bluesky and Mastodon.

## Features

- Posts top 3 tracks from the last 7 days
- Shows your most-played album
- Displays your top playlist
- All with clickable Spotify links
- Supports multiple platforms: Bluesky and Mastodon

## Setup

1. Install dependencies:
```bash
pip install spotipy python-dotenv atproto Mastodon.py
```

2. Create a `.env` file with your credentials:
```env
# Spotify (required)
SPOTIFY_CLIENT_ID=your_client_id
SPOTIFY_CLIENT_SECRET=your_client_secret
SPOTIFY_REDIRECT_URI=http://localhost:8888/callback

# Bluesky (optional)
BSKY_HANDLE=your.handle.bsky.social
BSKY_PASSWORD=your_app_password

# Mastodon (optional)
MASTODON_INSTANCE=https://mastodon.social
MASTODON_ACCESS_TOKEN=your_access_token
```

3. Get Spotify API credentials at [Spotify Developer Dashboard](https://developer.spotify.com/dashboard)

4. For Bluesky: Generate an app password in your account settings

5. For Mastodon: Create an application at Preferences -> Development -> New Application

## Usage

Post to all configured platforms:
```bash
python post_spotify.py
```

Post to specific platform(s):
```bash
python post_spotify.py --bluesky
python post_spotify.py --mastodon
python post_spotify.py --bluesky --mastodon
```

Just ingest data without posting:
```bash
python post_spotify.py --ingest-only
```

## How it works

The script uses Spotify's API to fetch your recent listening history and stores it in a local SQLite database. It then analyzes the last 7 days of data and posts a summary to your configured platforms.

For best results, run with `--ingest-only` regularly (e.g., via cron) since Spotify's recently-played API only returns the last ~50 tracks.

## Automated Scheduling with Cron

To automatically collect listening data and post weekly summaries, set up cron jobs:

1. Open your crontab:
```bash
crontab -e
```

2. Add these entries (adjust paths as needed):

```cron
# Ingest listening data every 6 hours
0 */6 * * * cd /path/to/post-spotify && ./run.sh --ingest-only

# Post weekly summary every Sunday at 6 PM
0 18 * * 0 cd /path/to/post-spotify && ./run.sh
```

**Note**: Make sure `run.sh` is executable (`chmod +x run.sh`) and update the paths to match your installation directory.

### Cron Schedule Examples

- `0 */6 * * *` - Every 6 hours
- `0 */4 * * *` - Every 4 hours (more frequent data collection)
- `0 18 * * 0` - Every Sunday at 6:00 PM
- `0 9 * * 1` - Every Monday at 9:00 AM
- `0 20 * * 5` - Every Friday at 8:00 PM

## License

MIT
