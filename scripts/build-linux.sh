#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
test "$(uname -s)" = Linux || { echo 'Build on native Linux'; exit 1; }
"${PYTHON:-.venv/bin/python}" scripts/build_desktop.py
