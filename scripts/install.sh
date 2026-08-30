#!/usr/bin/env bash
#
# Idempotent Cloud Agent install script for the SMC strategy bot.
# Safe to run repeatedly: it refreshes the virtualenv and dependencies without
# rewriting the lockfile or leaving background processes behind.
set -euo pipefail

cd "$(dirname "$0")/.."

# Ubuntu ships venv support in a separate package; install it only if missing.
if ! python3 -c "import ensurepip" >/dev/null 2>&1; then
  echo "python3 venv support missing; installing python3-venv"
  sudo apt-get update -qq
  sudo apt-get install -y -qq python3-venv
fi

python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt
# Editable install puts the src/ package on the path and registers the
# `smc-bot` console script.
.venv/bin/pip install -e .

echo "Install complete. Run a backtest with: .venv/bin/smc-bot --help"
