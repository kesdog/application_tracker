#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
test "$(uname -s)" = Darwin || { echo 'Build on native macOS'; exit 1; }
"${PYTHON:-.venv/bin/python}" scripts/build_desktop.py
