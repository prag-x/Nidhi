#!/bin/sh
set -e
echo "Applying database migrations…"
python -m app.cli migrate
if [ "${NIDHI_SEED_DEMO:-false}" = "true" ]; then
  echo "Loading demo data (only if the database is empty)…"
  python -m app.cli seed --if-empty --samples /data/samples
fi
exec "$@"
