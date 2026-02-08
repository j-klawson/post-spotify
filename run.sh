#!/usr/bin/env bash
set -euo pipefail

cd /home/lawsonk/repos/post-spotify

# Activate virtualenv
source .venv/bin/activate

# Load env vars
set -a
source .env
set +a

./post_spotify.py "$@"

