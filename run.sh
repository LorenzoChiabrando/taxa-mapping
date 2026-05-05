#!/usr/bin/env bash
# run.sh  taxa-mapping local runner
# Usage:
#   ./run.sh --input input/my_taxa.csv
#   ./run.sh -i input/my_taxa.csv -n simulation_name --report
#   ./run.sh -i input/my_taxa.csv --report --plots
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SOURCE="$SCRIPT_DIR/source"
VENV="$SOURCE/venv"

#  Setup: create venv on first run
if [ ! -d "$VENV" ]; then
    echo "[setup] Creating virtual environment..."
    python3 -m venv "$VENV"
    "$VENV/bin/pip" install --upgrade pip -q
fi

#  Always sync dependencies
"$VENV/bin/pip" install -q -r "$SOURCE/requirements.txt"

cd "$SCRIPT_DIR"
exec "$VENV/bin/python3" "$SOURCE/run.py" "$@"
