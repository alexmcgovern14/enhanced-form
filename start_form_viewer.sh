#!/bin/bash
set -euo pipefail

PORT=8081
echo "Starting Enhanced Form viewer on http://localhost:$PORT/form_viewer.html"
python3 run_form_viewer.py

