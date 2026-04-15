#!/bin/sh

set -eu

echo "Project: github-backup"
echo "Author:  Frazzer951"
echo "Base:    Python 3.13-slim"
echo "Target:  Unraid"
echo ""

APP_ROOT=/home/docker/github-backup
CONFIG_DIR=${CONFIG_DIR:-$APP_ROOT/config}
CONFIG_PATH=${CONFIG_PATH:-$CONFIG_DIR/config.json}

mkdir -p "$CONFIG_DIR"

if [ ! -f "$CONFIG_PATH" ]; then
    cp "$APP_ROOT/config.json.example" "$CONFIG_PATH"
fi

exec python3 -m github_backup "$CONFIG_PATH" --loop
