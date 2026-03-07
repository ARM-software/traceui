#!/bin/bash
#
# Try to never change this file, as this would break it as it updates itself!
#

if [[ $(git diff --quiet) ]]; then
  echo "Differences in checked out code - not running update!"
else
  echo "Updating..."
  git pull --rebase --quiet
  echo "... update done."
fi

. ./update-artifacts.sh

LOG_LEVEL=""
ARGS=()
while [[ $# -gt 0 ]]; do
  case "$1" in
  --log-level)
    LOG_LEVEL="$2"
    shift 2
    ;;
  --log-level=*)
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

python traceui.py "${ARGS[@]}"
