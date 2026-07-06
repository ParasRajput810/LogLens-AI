#!/usr/bin/env bash
set -euo pipefail

DEST="benchmarks/BGL_2k.log"
URL="https://raw.githubusercontent.com/logpai/loghub/master/BGL/BGL_2k.log"

mkdir -p benchmarks
if [ -f "$DEST" ]; then
  echo "Dataset already present: $DEST"
else
  echo "↓ Downloading BGL sample..."
  curl -sSL "$URL" -o "$DEST"
  echo "Saved to $DEST ($(wc -l < "$DEST") lines)"
fi

echo "Run: loglens benchmark $DEST --format bgl --grid --supervised"