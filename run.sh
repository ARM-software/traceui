#!/bin/bash
#
# Try to never change this file, as this would break it as it updates itself!
#

# Run from the script directory. Allows running from any directory.
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd -- "$SCRIPT_DIR"

if ! git diff --quiet || ! git diff --cached --quiet; then
  echo "Differences in checked out code - not running update!"
else
  echo "Updating..."
  git pull --rebase --quiet
  echo "... update done."
fi

. "$SCRIPT_DIR/update-artifacts.sh"

LOG_LEVEL=""
ARGS=()
while [[ $# -gt 0 ]]; do
  case "$1" in
  --loglevel)
    LOG_LEVEL="$2"
    shift 2
    ;;
  --loglevel=*)
    LOG_LEVEL="${1#*=}"
    shift
    ;;
  *)
    ARGS+=("$1")
    shift
    ;;
  esac
done

if [[ -n "$LOG_LEVEL" ]]; then
  export TRACEUI_LOG_LEVEL="$LOG_LEVEL"
fi

python "$SCRIPT_DIR/traceui.py" "${ARGS[@]}"
