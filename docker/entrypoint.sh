#!/usr/bin/env bash
set -euo pipefail

cd /app

mkdir -p database logs reports/charts .browser_profile

command_name="${1:-${APP_COMMAND:-run}}"
seed_file="${SEED_FILE:-product_codes.txt}"

case "$command_name" in
  run)
    python -m src.tasks.create_profile
    python -m src.tasks.seed_targets --file "$seed_file"
    exec python -m src.main
    ;;
  scrape)
    exec python -m src.main
    ;;
  analysis)
    exec python -m src.analysis.main
    ;;
  seed)
    exec python -m src.tasks.seed_targets --file "$seed_file"
    ;;
  profile)
    exec python -m src.tasks.create_profile
    ;;
  test)
    exec python -m pytest tests/unit -q
    ;;
  lint)
    exec python -m ruff check src tests
    ;;
  format-check)
    exec python -m ruff format --check src tests
    ;;
  bash|sh)
    if [ "$#" -gt 1 ]; then
      exec "$@"
    fi
    exec "$command_name"
    ;;
  *)
    exec "$@"
    ;;
esac
