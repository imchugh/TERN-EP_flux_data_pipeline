#!/bin/bash

# Script to pass command line args to the python run script that executes tasks
# Multiple sequential tasks may be queued

# Activate anaconda env
source /mnt/Software/miniconda3/bin/activate ep_cntl

# Specify python file to run
SCRIPT_DIR=$(dirname "$(readlink -f "$0")")
PARENT_DIR=$(dirname "$SCRIPT_DIR")
PY_RUN="$PARENT_DIR/run.py"

# Pass sequential task args
for task in "$@"; do
    python "$PY_RUN" "$task"
done
